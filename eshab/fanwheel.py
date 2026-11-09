"""The fan wheel's state and window (drawn by eshab/qml/windows/Wheel.qml).

The drag monitor tells it when to open, where the pointer is and when the
gesture ends; the OLE drop arrives through the window's DropArea. All three
wheels share one form, a fan of cards; they differ in content (format names,
tool icons, action icons in fixed places), in the legend under the orb and
in the deck dots naming each wheel's keys.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, QUrl, Property, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent

from . import fan, i18n, settings

log = logging.getLogger("eshab")

QML = Path(__file__).resolve().parent / "qml" / "windows" / "Wheel.qml"
LEAVE_MS = 260
SWITCH_MS = 110
NUDGE_MS = (120, 320, 650)  # when to move the pointer 1 px if the files are still unknown

MODE_TITLES = {"conversion": "wheel.convert", "tools": "wheel.tools", "actions": "wheel.actions"}
MODE_KEYS = {"conversion": "conversionWheelDragModifierMask", "tools": "toolsWheelDragModifierMask",
             "actions": "actionsWheelDragModifierMask"}


def _move_pointer(dx: int) -> None:
    """A real (input-queue) mouse move, which the drag loop reacts to; moving
    the cursor with SetCursorPos does not make Windows look again."""
    import ctypes
    from ctypes import wintypes

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

    event = INPUT(0, MOUSEINPUT(dx, 0, 0, 0x0001, 0, 0))     # INPUT_MOUSE, MOUSEEVENTF_MOVE
    try:
        ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    except Exception:
        log.debug("Could not nudge the pointer", exc_info=True)


def _keys_label(mask: str) -> str:
    return "+".join(settings.MODIFIER_LABELS.get(part, part.title())
                    for part in settings.MODIFIER_ORDER if part in settings.parse_mask(mask))


class FanWheel(QObject):
    activated = Signal(list, str, str)       # files, key, mode
    closed = Signal()

    changed = Signal()
    selectionChanged = Signal()
    phaseChanged = Signal()

    def __init__(self, engine, images, items_for, parent=None):
        super().__init__(parent)
        self._images = images
        self._items_for = items_for          # (files, mode) -> list of card dicts
        self._files: list[str] = []
        self._mode = "conversion"
        self._layout = fan.layout(0)
        self._cards: list[dict] = []
        self._selected = -1
        self._phase = "hidden"
        self._keyboard = False
        self._pinned = False
        self._frost = ""
        self._frost_serial = 0
        self._label = ""
        self._origin = QPoint()
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._finish_leaving)
        self._component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML)))
        self.window = self._component.createWithInitialProperties({"wheel": self})
        if self.window is None:
            raise RuntimeError("; ".join(e.toString() for e in self._component.errors()))

    # -- properties for QML ---------------------------------------------------

    @Property("QVariantList", notify=changed)
    def cards(self):
        return self._cards

    @Property(int, notify=selectionChanged)
    def selected(self):
        return self._selected

    @Property(str, notify=phaseChanged)
    def phase(self):
        return self._phase

    @Property(str, notify=changed)
    def frost(self):
        return self._frost

    @Property(str, notify=changed)
    def preview(self):
        if not self._files:
            return ""
        return "image://eshab/thumb/" + quote(self._files[0], safe="")

    @Property(int, notify=changed)
    def fileCount(self):
        return len(self._files)

    @Property(bool, notify=changed)
    def opensDown(self):
        return self._layout.opens_down

    @Property(bool, notify=changed)
    def keyboard(self):
        return self._keyboard

    @Property(bool, notify=changed)
    def pinned(self):
        return self._pinned or self._keyboard

    @Property(str, notify=selectionChanged)
    def label(self):
        return self._label

    @Property("QVariantList", notify=changed)
    def modes(self):
        result = []
        for mode in ("conversion", "tools", "actions"):
            keys = _keys_label(settings.get(MODE_KEYS[mode], ""))
            if keys:
                result.append({"mode": mode, "keys": keys, "active": mode == self._mode})
        return result

    # -- driven by the monitor --------------------------------------------------

    def show_at(self, pos: QPoint, files, mode: str, pinned: bool = False, keyboard: bool = False) -> None:
        self._leave_timer.stop()
        self._origin = QPoint(pos)
        self._mode = mode
        self._pinned = pinned
        self._keyboard = keyboard
        self._files = [str(Path(f)) for f in (files or [])]
        side = int(fan.SIDE)
        rect = QRect(pos.x() - side // 2, pos.y() - side // 2, side, side)
        if self._phase == "hidden":
            self._capture(rect)
        self._relayout(pos)
        self._set_selected(-1)
        self.window.setFlag(Qt.WindowType.WindowDoesNotAcceptFocus, not keyboard)
        self.window.setPosition(rect.topLeft())
        self._set_phase("open")
        self.window.show()
        if keyboard:
            self.window.requestActivate()
        elif not self._files:
            # Windows names the dragged files only when the pointer moves
            # over the wheel; held still, it would stay on "reading" with no
            # cards. Nudge it once the window is up, then once more.
            for delay in NUDGE_MS:
                QTimer.singleShot(delay, self._nudge)

    def _nudge(self) -> None:
        if self._phase != "open" or self._files or self._keyboard:
            return
        _move_pointer(1)
        _move_pointer(-1)

    def add_files(self, files) -> None:
        """More files for the open wheel (Explorer's menu, one launch per file)."""
        merged = list(self._files)
        for file in files:
            path = str(Path(file))
            if path not in merged:
                merged.append(path)
        if merged != self._files and self.is_open():
            self._files = merged
            self._relayout(self._origin)

    def pointer_global(self, pos: QPoint) -> None:
        local = pos - self.window.position()
        self.pointer(local.x(), local.y())

    def switch(self, mode: str) -> None:
        if mode == self._mode or self._phase not in ("open", "switching"):
            return
        self._mode = mode
        self._set_selected(-1)
        self._set_phase("switching")
        QTimer.singleShot(SWITCH_MS, self._finish_switch)

    def dismiss(self) -> None:
        if self._phase in ("hidden", "leaving"):
            return
        self._set_selected(-1)
        self._leave()

    def origin(self) -> QPoint:
        """Where the gesture happened (the wheel's centre)."""
        return QPoint(self._origin)

    def is_open(self) -> bool:
        return self._phase in ("open", "switching")

    def contains(self, pos: QPoint) -> bool:
        return self.is_open() and QRect(self.window.position(), self.window.size()).contains(pos)

    # -- driven by QML -----------------------------------------------------------

    @Slot(float, float)
    def pointer(self, x: float, y: float) -> None:
        if self._phase == "open":
            self._set_selected(fan.pick(self._layout, x, y))

    @Slot()
    def leave(self) -> None:
        if self._phase == "open" and not self.pinned:
            self._set_selected(-1)

    @Slot("QVariantList")
    def enter(self, urls) -> None:
        files = [QUrl(u).toLocalFile() if not isinstance(u, QUrl) else u.toLocalFile() for u in urls]
        # Same spelling as the monitor's paths (backslashes), or the
        # comparison below would see a different selection.
        files = [str(Path(f)) for f in files if f]
        if not files:
            return
        known = self._files
        if known and len(files) < len(known) and set(files) <= set(known):
            files = known          # Explorer collapsed a Shift-drag selection; keep the snapshot
        if files != self._files:
            self._files = files
            self._relayout(self._origin)

    @Slot(result=bool)
    def drop(self) -> bool:
        if self._phase != "open" or self._selected < 0:
            self.dismiss()
            return False
        self._activate(self._selected)
        return True

    @Slot(float, float)
    def click(self, x: float, y: float) -> None:
        index = fan.pick(self._layout, x, y)
        if index >= 0:
            self._activate(index)
        else:
            self.escape()

    @Slot(int)
    def step(self, delta: int) -> None:
        if self._phase == "open":
            self._set_selected(fan.step_selection(self._layout, self._selected, delta))

    @Slot()
    def confirm(self) -> None:
        if self._phase == "open" and self._selected >= 0:
            self._activate(self._selected)

    @Slot()
    def escape(self) -> None:
        self.dismiss()
        self.closed.emit()

    # -- internals ---------------------------------------------------------------

    def _capture(self, rect: QRect) -> None:
        from .images import frost_under

        try:
            image = frost_under(rect)
        except Exception:
            log.exception("Could not capture the wheel backdrop")
            return
        self._frost_serial += 1
        key = str(self._frost_serial)
        self._images.put_frost(key, image)
        self._frost = "image://eshab/frost/" + key

    def _relayout(self, pos: QPoint) -> None:
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 10_000, 10_000)
        free = (pos.x() - area.left(), pos.y() - area.top(), area.right() - pos.x(), area.bottom() - pos.y())
        items = list(self._items_for(self._files, self._mode))[: fan.MAX_CARDS] if self._files else []
        self._layout = fan.layout(len(items), free)
        self._cards = [dict(item, x=card.x, y=card.y) for item, card in zip(items, self._layout.cards)]
        self.changed.emit()
        self._update_label()

    def _finish_switch(self) -> None:
        if self._phase != "switching":
            return
        self._relayout(self._origin)
        self._set_phase("open")

    def _activate(self, index: int) -> None:
        card = self._cards[index]
        files = list(self._files)
        log.info("Wheel activated: mode=%s, key=%s, files=%d", self._mode, card["key"], len(files))
        self._set_selected(index)
        self._leave()
        self.activated.emit(files, card["key"], self._mode)

    def _leave(self) -> None:
        self._set_phase("leaving")
        self._leave_timer.start(LEAVE_MS)

    def _finish_leaving(self) -> None:
        self.window.hide()
        self._set_phase("hidden")
        self._set_selected(-1)
        self._cards = []
        self._files = []
        self._keyboard = False
        self._pinned = False
        self.changed.emit()

    def _set_selected(self, index: int) -> None:
        if index != self._selected:
            self._selected = index
            self._update_label()

    def _update_label(self) -> None:
        if 0 <= self._selected < len(self._cards):
            card = self._cards[self._selected]
            if self._mode == "conversion":
                self._label = i18n.tr("wheel.to_format", target=card["text"])
            else:
                self._label = card["label"]
        elif not self._cards and self._files:
            self._label = i18n.tr("wheel.nothing")
        elif not self._files:
            self._label = i18n.tr("wheel.reading")
        else:
            self._label = i18n.tr(MODE_TITLES.get(self._mode, "wheel.convert"))
        self.selectionChanged.emit()

    def _set_phase(self, phase: str) -> None:
        if phase != self._phase:
            self._phase = phase
            self.phaseChanged.emit()
