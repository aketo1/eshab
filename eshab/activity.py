"""The activity island at the top centre of the screen: what Eshab is doing.

A job starts where the file was dropped: a drop flies from there to the top
of the screen and the island forms around it (windows/Drop.qml,
windows/Island.qml). Compact, it shows the mark filling, the job and its
percentage; it never takes focus and lets every click through, so the tabs
and title bars under it keep working. Rest the pointer on it for a third of
a second and it opens: each job with its progress and a cancel button,
finished ones with Show and Open. A finished job shows its tick for two
seconds and the island leaves; a failure stays as a small red dot until the
island has been opened once.

The shelf lives here too: files parked from the wheel's «الرف المؤقت» stay in
a small capsule (their count and a peek of them) until they are dragged out
or cleared. Resting the pointer opens it like the jobs, each file a tile to
drag anywhere; dragging copies, so the original never moves by accident.

Recent files: every result Eshab makes is remembered (the last twelve, kept
on disk). They show as tiles under the jobs whenever the island is open, and
«آخر الملفات» in the tray menu opens the island just for them: click a tile
to open the file, drag it anywhere to copy it.

Nothing appears over full-screen apps and games; jobs are still tracked and
show when the island may appear again.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import json
from urllib.parse import quote

from PySide6.QtCore import QMimeData, QObject, QPoint, QProcess, QRect, QTimer, QUrl, Property, Qt, Signal, Slot
from PySide6.QtGui import QCursor, QDesktopServices, QDrag, QGuiApplication, QImage, QPixmap, QRegion
from PySide6.QtQml import QQmlComponent

from . import context, i18n, paths

log = logging.getLogger("eshab")

WINDOWS = Path(__file__).resolve().parent / "qml" / "windows"
WINDOW_W, WINDOW_H = 460, 720
TOP_GAP = 8
COMPACT_W, COMPACT_H = 260, 38
SHELF_COMPACT_W = 176            # only parked files: a smaller capsule
EXPANDED_W = 400
ROW_H, EXPANDED_PAD = 58, 14
MAX_ROWS = 5
SHELF_HEAD_H = 34
TILE_W, TILE_H, TILE_GAP = 86, 92, 4
TILES_PER_ROW = 4
SHELF_ROWS = 2                   # more files scroll inside the shelf
MAX_SHELF = 60
DWELL_S = 0.30          # resting this long on the island opens it
LEAVE_S = 0.25          # leaving the open island this long closes it
DONE_HOLD_S = 2.0
NOTE_HOLD_S = 2.0
FLIGHT_MS = 480
MAX_RECENT = 12
RECENT_HOLD_S = 8.0              # opened from the tray: wait this long for the pointer to arrive


class ActivityIsland(QObject):
    changed = Signal()
    cancelRequested = Signal(str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._cards: list[dict] = []
        self._shelf: list[dict] = []
        self._recent: list[dict] = self._load_recent()
        self._recent_shown = False        # opened from the tray menu for the recent files
        self._hold_until = 0.0
        self._dragging = False
        self._state = "hidden"            # hidden | compact | expanded
        self._hover_since: float | None = None
        self._away_since: float | None = None
        self._screen = QRect()
        self._flight = {"from": QPoint(), "to": QPoint(), "serial": 0}
        self._pointer = QTimer(self)
        self._pointer.setInterval(30)
        self._pointer.timeout.connect(self._track_pointer)
        self._sweeper = QTimer(self)
        self._sweeper.setInterval(250)
        self._sweeper.timeout.connect(self._sweep)
        self._components = []
        self.window = self._create(engine, "Island.qml")
        self.drop = self._create(engine, "Drop.qml")

    def _create(self, engine, name: str):
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(WINDOWS / name)))
        window = component.createWithInitialProperties({"island": self})
        if window is None:
            raise RuntimeError("; ".join(e.toString() for e in component.errors()))
        self._components.append(component)
        return window

    # -- QML --------------------------------------------------------------------

    @Property("QVariantList", notify=changed)
    def cards(self):
        return [dict(c, until=0) for c in self._cards[:MAX_ROWS]]

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property("QVariantMap", notify=changed)
    def headline(self):
        card = self._headline()
        return dict(card, until=0) if card else {}

    @Property(int, notify=changed)
    def others(self):
        return max(0, sum(1 for c in self._cards if c["state"] == "working") - 1)

    @Property("QVariantList", notify=changed)
    def shelf(self):
        return list(self._shelf)

    @Property(int, notify=changed)
    def shelfHeight(self):
        """The shelf's part of the open island (0 when nothing is parked)."""
        if not self._shelf:
            return 0
        rows = min(SHELF_ROWS, -(-len(self._shelf) // TILES_PER_ROW))
        return SHELF_HEAD_H + rows * (TILE_H + TILE_GAP)

    @Property("QVariantList", notify=changed)
    def recent(self):
        return [f for f in self._recent if Path(f["path"]).exists()]

    @Property(int, notify=changed)
    def recentHeight(self):
        """The recent strip's part of the open island (0 when there is none):
        one row beside jobs or parked files, two when opened just for them."""
        count = len(self.recent)
        if not count:
            return 0
        most = 2 if not self._cards and not self._shelf else 1
        rows = min(most, -(-count // TILES_PER_ROW))
        return SHELF_HEAD_H + rows * (TILE_H + TILE_GAP)

    @Property(int, notify=changed)
    def islandWidth(self):
        if self._state == "expanded":
            return EXPANDED_W
        return COMPACT_W if self._cards else SHELF_COMPACT_W

    @Property(int, notify=changed)
    def islandHeight(self):
        if self._state == "expanded":
            rows = min(len(self._cards), MAX_ROWS)
            shown = [part for part in (ROW_H * rows, self.shelfHeight, self.recentHeight) if part]
            return EXPANDED_PAD * 2 + sum(shown) + 8 * max(0, len(shown) - 1)
        return COMPACT_H

    @Property(int, notify=changed)
    def flightSerial(self):
        return self._flight["serial"]

    @Property(QPoint, notify=changed)
    def flightFrom(self):
        return self._flight["from"]

    @Property(QPoint, notify=changed)
    def flightTo(self):
        return self._flight["to"]

    @Slot()
    def landed(self) -> None:
        """The flying drop reached the top: the island forms around it."""
        self._update()

    @Slot(str)
    def reveal(self, job_id: str) -> None:
        card = self._find(job_id)
        if card and card.get("output"):
            QProcess.startDetached("explorer.exe", ["/select,", str(Path(card["output"]))])
            self.dismiss(job_id)

    @Slot(str)
    def open(self, job_id: str) -> None:
        card = self._find(job_id)
        if card and card.get("output"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(card["output"]))
            self.dismiss(job_id)

    @Slot(str)
    def cancel(self, job_id: str) -> None:
        self.cancelRequested.emit(job_id)

    @Slot(str)
    def dismiss(self, job_id: str) -> None:
        self._cards = [c for c in self._cards if c["id"] != job_id]
        self._update()

    # -- recent files ---------------------------------------------------------------

    @Slot(str)
    def openRecent(self, path: str) -> None:
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot()
    def clearRecent(self) -> None:
        self._recent = []
        self._save_recent()
        self._update()

    def show_recent(self, anchor: QPoint) -> None:
        """«آخر الملفات» from the tray menu: open the island for them."""
        if not self.recent:
            self.note(i18n.tr("recent.none"))
            return
        self._place(anchor)
        self._recent_shown = True
        self._hold_until = time.monotonic() + RECENT_HOLD_S
        self._set_state("expanded")
        self.changed.emit()

    def _remember(self, output: str) -> None:
        path = Path(output)
        if not output or not path.exists():
            return
        entry = self._recent_entry(path)
        self._recent = [entry] + [f for f in self._recent if f["path"] != entry["path"]][: MAX_RECENT - 1]
        self._save_recent()

    @staticmethod
    def _recent_entry(path: Path) -> dict:
        return {"path": str(path), "name": path.name, "folder": path.is_dir(),
                "url": "image://eshab/thumb/" + quote(str(path), safe="")}

    @staticmethod
    def _recent_file() -> Path:
        return paths.data_dir() / "recent.json"

    def _load_recent(self) -> list[dict]:
        try:
            stored = json.loads(self._recent_file().read_text("utf-8"))
        except (OSError, ValueError):
            return []
        items = stored if isinstance(stored, list) else []
        return [self._recent_entry(Path(item)) for item in items
                if isinstance(item, str) and Path(item).exists()][:MAX_RECENT]

    def _save_recent(self) -> None:
        try:
            self._recent_file().write_text(json.dumps([f["path"] for f in self._recent], ensure_ascii=False),
                                           "utf-8")
        except OSError:
            log.warning("Could not save the recent files", exc_info=True)

    # -- the shelf ----------------------------------------------------------------

    @Slot(str)
    def unshelve(self, path: str) -> None:
        self._shelf = [f for f in self._shelf if f["path"] != path]
        self._update()

    @Slot()
    def clearShelf(self) -> None:
        self._shelf = []
        self._update()

    @Slot(str)
    def revealShelved(self, path: str) -> None:
        if Path(path).exists():
            QProcess.startDetached("explorer.exe", ["/select,", str(Path(path))])

    @Slot(str)
    def dragOut(self, paths_json: str) -> None:
        """Drag parked files out of the island (a copy: the originals stay where they are)."""
        try:
            wanted = [str(p) for p in json.loads(paths_json)]
        except (TypeError, ValueError):
            return
        files = [Path(p) for p in wanted if Path(p).exists()]
        gone = [p for p in wanted if not Path(p).exists()]
        if gone:
            self._shelf = [f for f in self._shelf if f["path"] not in gone]
            self._update()
        if not files:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in files])
        drag = QDrag(self)
        drag.setMimeData(mime)
        picture = self._drag_picture(files[0], len(files))
        if picture is not None:
            drag.setPixmap(picture)
            drag.setHotSpot(QPoint(picture.width() // 2, picture.height() // 2))
        self._dragging = True
        try:
            drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
        finally:
            self._dragging = False

    @staticmethod
    def _drag_picture(path: Path, count: int) -> QPixmap | None:
        try:
            from .images import _thumbnail
            from PySide6.QtCore import QSize

            image = _thumbnail(path, QSize(64, 64))
            if image.isNull():
                return None
            image = image.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if count > 1:
                from PySide6.QtGui import QColor, QFont, QPainter

                canvas = QImage(image.width() + 14, image.height() + 14, QImage.Format.Format_ARGB32_Premultiplied)
                canvas.fill(Qt.GlobalColor.transparent)
                painter = QPainter(canvas)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.drawImage(0, 14, image)
                painter.setBrush(QColor("#F2A33A"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(canvas.width() - 26, 0, 26, 26)
                painter.setPen(QColor("#3D2204"))
                font = QFont("Segoe UI")
                font.setPixelSize(13)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(QRect(canvas.width() - 26, 0, 26, 26), Qt.AlignmentFlag.AlignCenter, str(count))
                painter.end()
                image = canvas
            return QPixmap.fromImage(image)
        except Exception:
            log.exception("No picture for the drag")
            return None

    # -- from the app -------------------------------------------------------------

    def start(self, job_id: str, title: str, detail: str, anchor: QPoint) -> None:
        self._cards.insert(0, {"id": job_id, "title": title, "detail": detail, "progress": -1.0,
                               "state": "working", "output": "", "until": float("inf"), "seen": False})
        self._place(anchor)
        if self._state == "hidden" and self._may_show():
            self._fly(anchor)       # the island forms when the drop lands
        else:
            self._update()

    def note(self, title: str, detail: str = "") -> None:
        """A one-off confirmation (path copied, files moved…): a tick, then gone."""
        job_id = f"note-{time.monotonic_ns()}"
        self._cards.insert(0, {"id": job_id, "title": title, "detail": detail, "progress": 1.0,
                               "state": "done", "output": "", "until": time.monotonic() + NOTE_HOLD_S,
                               "seen": False})
        if self._screen.isNull():
            self._place(QCursor.pos())
        self._update()

    def progress(self, job_id: str, value: float) -> None:
        card = self._find(job_id)
        if card is not None:
            card["progress"] = float(value)
            self.changed.emit()

    def status(self, job_id: str, text: str) -> None:
        card = self._find(job_id)
        if card is not None and card["state"] == "working" and text:
            card["detail"] = text
            self.changed.emit()

    def finish(self, job_id: str, output: str, state: str = "done", detail: str | None = None) -> None:
        card = self._find(job_id)
        if card is None:
            return
        card.update(state=state, output=output, progress=1.0)
        if state == "done" and output:
            self._remember(output)
        if detail is not None:
            card["detail"] = detail
        elif output:
            card["detail"] = Path(output).name
        card["until"] = float("inf") if state == "error" else time.monotonic() + DONE_HOLD_S
        self._update()

    def shelve(self, files) -> int:
        """Park files on the shelf; returns how many are on it now."""
        known = {f["path"] for f in self._shelf}
        added = 0
        for file in files:
            path = Path(file)
            if not path.exists() or str(path) in known or len(self._shelf) >= MAX_SHELF:
                continue
            known.add(str(path))
            self._shelf.append({"path": str(path), "name": path.name, "folder": path.is_dir(),
                                "url": "image://eshab/thumb/" + quote(str(path), safe="")})
            added += 1
        if added:
            anchor = QCursor.pos()
            if self._state == "hidden" and self._may_show():
                self._place(anchor)
                self._fly(anchor)       # the files fly up to the island
            else:
                if self._screen.isNull():
                    self._place(anchor)
                self._update()
        return len(self._shelf)

    def busy(self) -> bool:
        return bool(self._cards or self._shelf or self._recent_shown)

    # -- pure state (tested directly) ---------------------------------------------

    def _headline(self) -> dict | None:
        for wanted in ("working", "error", "done"):
            for card in self._cards:
                if card["state"] == wanted and not (wanted == "error" and card["seen"]):
                    return card
        return self._cards[0] if self._cards else None

    def _expire(self, now: float) -> bool:
        """Drop finished cards whose time is up; seen errors go when it closes."""
        kept = [c for c in self._cards
                if c["until"] > now and not (c["state"] == "error" and c["seen"] and self._state != "expanded")]
        changed = len(kept) != len(self._cards)
        self._cards = kept
        return changed

    def _hover(self, inside: bool, now: float) -> str | None:
        """Dwell logic: returns the state to switch to, if any."""
        if self._state == "compact":
            if not inside:
                self._hover_since = None
                return None
            if self._hover_since is None:
                self._hover_since = now
            return "expanded" if now - self._hover_since >= DWELL_S else None
        if self._state == "expanded":
            if inside:
                self._away_since = None
                self._hold_until = 0.0
                return None
            if now < self._hold_until:
                return None
            if self._away_since is None:
                self._away_since = now
            return "compact" if now - self._away_since >= LEAVE_S else None
        return None

    # -- window -------------------------------------------------------------------

    def _may_show(self) -> bool:
        try:
            return context.wheel_allowed()
        except Exception:
            return True

    def _place(self, anchor: QPoint) -> None:
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        self._screen = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)

    def _origin(self) -> QPoint:
        return QPoint(self._screen.center().x() - WINDOW_W // 2, self._screen.top())

    def _island_rect(self, margin: int = 0) -> QRect:
        width, height = self.islandWidth, self.islandHeight
        local = QRect((WINDOW_W - width) // 2, TOP_GAP, width, height)
        return local.adjusted(-margin, -margin, margin, margin)

    def _fly(self, anchor: QPoint) -> None:
        self._flight = {"from": QPoint(anchor), "serial": self._flight["serial"] + 1,
                        "to": QPoint(self._screen.center().x(), self._screen.top() + TOP_GAP + COMPACT_H // 2)}
        self.changed.emit()
        QTimer.singleShot(FLIGHT_MS + 40, self.landed)

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._hover_since = self._away_since = None
        if state == "expanded":
            for card in self._cards:
                card["seen"] = True
        self.changed.emit()
        self._apply_window()

    def _apply_window(self) -> None:
        window = self.window
        if self._state == "hidden":
            self._pointer.stop()
            self._sweeper.stop()
            QTimer.singleShot(280, lambda: self._state == "hidden" and window.hide())
            return
        window.setPosition(self._origin())
        # Compact, the island lets every click through to what is under it;
        # it only takes the pointer once it has been opened on purpose.
        window.setFlag(Qt.WindowType.WindowTransparentForInput, self._state != "expanded")
        window.setFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        window.setMask(QRegion(self._island_rect(margin=16)))
        if not window.isVisible():
            window.show()
        self._pointer.start()
        self._sweeper.start()

    def _update(self) -> None:
        self._expire(time.monotonic())
        if self._recent_shown and self._state != "expanded":
            self._recent_shown = False      # the recent files were seen; the island may go
        if not self._cards and not self._shelf and not self._recent_shown:
            self._set_state("hidden")
        elif not self._may_show():
            self._set_state("hidden")
            self._sweeper.start()      # look again later
        elif self._state == "hidden":
            self._set_state("compact")
        else:
            self._apply_window()
        self.changed.emit()

    def _track_pointer(self) -> None:
        if self._dragging:
            return              # a file is being dragged out: the island holds still
        pos = QCursor.pos() - self.window.position()
        inside = self._island_rect(margin=6 if self._state == "compact" else 14).contains(pos)
        target = self._hover(inside, time.monotonic())
        if target is not None:
            self._set_state(target)
            if target == "compact":
                self._update()

    def _sweep(self) -> None:
        if self._state == "expanded":
            return
        if self._expire(time.monotonic()) or (self._state == "hidden" and (self._cards or self._shelf)):
            self._update()

    def _find(self, job_id: str) -> dict | None:
        return next((c for c in self._cards if c["id"] == job_id), None)


def title_for(mode: str, key: str) -> str:
    if mode == "conversion":
        return i18n.tr("wheel.to_format", target=i18n.tr("conv." + key))
    return i18n.tr("tool." + key)
