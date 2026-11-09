"""The home window: what Eshab is, played as a live demo of the gesture.

It opens on first launch and from the tray icon.  The stage replays the real
gesture with the real wheel (:class:`~eshab.wheel.WheelScene`): a file is
dragged, Shift lights up, drops split off the orb, the lens slides to PDF,
the file is released and the liquid pill fills and turns into a check.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import glass, i18n, paths, theme
from .wheel import FanItem, WheelScene

LOOP_S = 7.2
DEMO_TARGET = 4          # index of "PDF" in DEMO_ITEMS
DEMO_ITEMS = ["JPG", "WEBP", "AVIF", "HEIC", "PDF", "DOCX"]


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: QPointF, b: QPointF, t: float) -> QPointF:
    return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)


class _Canvas(QWidget):
    """A widget-shaped host for the scene (it needs width/height/dpr)."""

    def __init__(self, stage: "DemoStage", size: QSize):
        super().__init__(stage)
        self._size = size
        self.hide()

    def width(self) -> int:  # noqa: D401 - the scene's coordinate space
        return self._size.width()

    def height(self) -> int:
        return self._size.height()

    def update(self) -> None:  # the stage repaints on its own clock
        pass


class DemoStage(QWidget):
    """Plays the gesture in a loop."""

    SCALE = 0.56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(540, 270)
        self.dark = theme.is_dark()
        self._canvas = _Canvas(self, QSize(500, 500))
        self.scene = WheelScene(self._canvas)
        self.scene.animator.stop()
        self.scene.animator.kick = lambda: None  # the stage steps the springs
        self._preview = self._demo_preview()
        self.scene.modes = ["conversion", "tools"]
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0.0
        self._t = 0.0
        self._state = ""
        self._backdrop_image: QImage | None = None
        self._stage_backdrop: QImage | None = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(14)
        self._timer.timeout.connect(self._tick)
        self.step = 0

    @staticmethod
    def _demo_preview() -> QPixmap:
        image = QImage(96, 72, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sky = QLinearGradient(0, 0, 0, 72)
        sky.setColorAt(0.0, QColor("#AFC3D6"))
        sky.setColorAt(1.0, QColor("#E9EEF3"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sky)
        p.drawRoundedRect(QRectF(0, 0, 96, 72), 8, 8)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawEllipse(QPointF(70, 20), 9, 9)
        hill = QPainterPath(QPointF(0, 72))
        hill.lineTo(0, 52)
        hill.quadTo(30, 30, 56, 50)
        hill.quadTo(78, 38, 96, 48)
        hill.lineTo(96, 72)
        p.setBrush(QColor("#4B5563"))
        p.drawPath(hill)
        p.end()
        return QPixmap.fromImage(image)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.dark = theme.is_dark()
        self.scene.dark = self.dark
        self._backdrop_image = None
        self._clock.restart()
        self._last = 0.0
        self._state = ""
        self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    # -- stage background (it is also what the glass refracts) -------------

    @staticmethod
    def _wallpaper() -> QImage:
        """The Windows wallpaper, or a quiet neutral gradient."""
        import os

        candidates = []
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper")
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                value, _ = winreg.QueryValueEx(key, "WallPaper")
                if value:
                    candidates.insert(0, Path(value))
        except OSError:
            pass
        for candidate in candidates:
            try:
                if candidate.is_file():
                    image = QImage()
                    if image.loadFromData(candidate.read_bytes()):
                        return image
            except OSError:
                continue
        return QImage()

    def _background(self) -> QImage:
        size = self.size()
        if self._backdrop_image is not None and self._backdrop_image.size() == size:
            return self._backdrop_image
        image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        wallpaper = self._wallpaper()
        if not wallpaper.isNull():
            scaled = wallpaper.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
            p.drawImage(QPointF((size.width() - scaled.width()) / 2, (size.height() - scaled.height()) / 2), scaled)
        else:
            base = QLinearGradient(0, 0, size.width(), size.height())
            base.setColorAt(0.0, QColor("#3A3A40") if self.dark else QColor("#D9DCE3"))
            base.setColorAt(1.0, QColor("#141416") if self.dark else QColor("#F4F5F8"))
            p.fillRect(image.rect(), base)
        p.end()
        self._backdrop_image = image
        crop = image.copy(self._scene_rect().toRect())
        self.scene.backdrop.use_image(crop, (500.0 * self.SCALE, 500.0 * self.SCALE))
        self._stage_backdrop = image
        return image

    def _scene_rect(self) -> QRectF:
        side = 500.0 * self.SCALE
        center = self._wheel_center()
        return QRectF(center.x() - side / 2, center.y() - side / 2, side, side)

    def _wheel_center(self) -> QPointF:
        return QPointF(self.width() * 0.5, self.height() * 0.5 + 6)

    # -- timeline --------------------------------------------------------

    def _tick(self) -> None:
        now = self._clock.elapsed() / 1000.0
        dt = min(0.05, max(0.0, now - self._last))
        self._last = now
        self._t = now % LOOP_S
        steps = max(1, int(dt / (1.0 / 240.0)))
        for _ in range(steps):
            for spring in self.scene.animator._springs:
                spring.step(dt / steps)
        self.scene._tick(dt)
        self._script(self._t)
        self.update()

    def _enter(self, state: str) -> bool:
        if self._state == state:
            return False
        self._state = state
        return True

    def _script(self, t: float) -> None:
        scene = self.scene
        if t < 1.0:
            if self._enter("drag"):
                scene.clear()
                scene.files = ["demo.png"]
                scene.preview = self._preview
                scene._preview_path = "demo.png"
                self.step = 0
        elif t < 1.7:
            if self._enter("shift"):
                scene.set_items([FanItem(k.lower(), k) for k in DEMO_ITEMS], animate=True)
                scene.appear()
                self.step = 1
        elif t < 2.2:
            if self._enter("toward-webp"):
                scene.set_hover(1)
                self.step = 2
        elif t < 3.5:
            if self._enter("toward-pdf"):
                scene.set_hover(DEMO_TARGET)
        elif t < 6.4:
            if self._enter("drop"):
                scene.depart(chosen=DEMO_TARGET)
        else:
            self._enter("rest")

    def _cursor(self, t: float) -> QPointF:
        center = self._wheel_center()
        start = QPointF(self.width() * 0.16, self.height() * 0.78)
        if t < 1.0:
            return _lerp(start, center, _ease(t / 1.0))
        if t < 1.7:
            return center
        webp = self._target_point(1)
        pdf = self._target_point(DEMO_TARGET)
        if t < 2.2:
            return _lerp(center, _lerp(center, webp, 0.55), _ease((t - 1.7) / 0.5))
        if t < 3.5:
            return _lerp(_lerp(center, webp, 0.55), _lerp(center, pdf, 0.6), _ease((t - 2.2) / 0.9))
        return _lerp(center, pdf, 0.6)

    def _target_point(self, index: int) -> QPointF:
        count = len(DEMO_ITEMS)
        angle = math.radians(-90.0 + index * 360.0 / count)
        ring = 152.0 * self.SCALE
        center = self._wheel_center()
        return QPointF(center.x() + math.cos(angle) * ring, center.y() + math.sin(angle) * ring)

    # -- painting --------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 22, 22)
        p.setClipPath(clip)
        p.drawImage(0, 0, self._background())
        t = self._t
        rect = self._scene_rect()
        p.save()
        p.translate(rect.topLeft())
        p.scale(self.SCALE, self.SCALE)
        self.scene.paint(p, catch_drops=False)
        p.restore()
        self._paint_keycap(p, t)
        cursor = self._cursor(t)
        if t < 1.9:
            self._paint_ghost(p, cursor, 1.0 if t < 1.0 else max(0.0, 1.0 - (t - 1.0) / 0.9) * 0.4 + 0.6)
        if 3.5 <= t < 6.6:
            self._paint_pill(p, t - 3.5)
        if t < 3.6:
            self._paint_pointer(p, cursor)
        p.setClipping(False)
        t_ = glass.tokens(self.dark)
        pen = QPen(t_.rim_soft, 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)
        p.end()

    def _paint_keycap(self, p: QPainter, t: float) -> None:
        pressed = 1.0 <= t < 1.75
        glow = 1.0 if pressed else 0.0
        rect = QRectF(18, self.height() - 52, 78, 34)
        if i18n.is_rtl():
            rect.moveRight(self.width() - 18)
        glass.soft_shadow(p, rect, 10, 10, QColor(0, 0, 0, 70), QPointF(0, 4 if not pressed else 1))
        path = QPainterPath()
        path.addRoundedRect(rect.translated(0, 3 if pressed else 0), 10, 10)
        glass.paint_glass(p, path, self.dark, None, lift=glow)
        p.setFont(glass.font(13, QFont.Weight.Bold, label=True))
        ink = QColor("#111114") if pressed else QColor("#FFFFFF")
        glass.text(p, path.boundingRect(), int(Qt.AlignmentFlag.AlignCenter), "⇧ Shift", ink)

    def _paint_ghost(self, p: QPainter, cursor: QPointF, opacity: float) -> None:
        rect = QRectF(cursor.x() - 22, cursor.y() - 26, 44, 52)
        p.save()
        p.setOpacity(opacity)
        glass.soft_shadow(p, rect, 8, 8, QColor(0, 0, 0, 80), QPointF(0, 4))
        page = QPainterPath()
        page.addRoundedRect(rect, 8, 8)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#FFFFFF"))
        gradient.setColorAt(1.0, QColor("#EDEDF0"))
        p.fillPath(page, gradient)
        art = rect.adjusted(6, 6, -6, -18)
        sky = QLinearGradient(art.topLeft(), art.bottomLeft())
        sky.setColorAt(0.0, QColor("#AFC3D6"))
        sky.setColorAt(1.0, QColor("#E9EEF3"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sky)
        p.drawRoundedRect(art, 4, 4)
        p.setPen(QColor("#3A3A3C"))
        p.setFont(glass.font(9, QFont.Weight.Bold, label=True))
        p.drawText(QRectF(rect.left(), rect.bottom() - 17, rect.width(), 14), int(Qt.AlignmentFlag.AlignCenter), "PNG")
        p.restore()

    def _paint_pointer(self, p: QPainter, at: QPointF) -> None:
        path = QPainterPath(at)
        for dx, dy in ((0, 17), (4.2, 13.2), (7.2, 19.6), (10, 18.4), (7.1, 12.2), (12.4, 12.2)):
            path.lineTo(at.x() + dx, at.y() + dy)
        path.closeSubpath()
        p.save()
        p.setPen(QPen(QColor("#FFFFFF"), 1.4))
        p.setBrush(QColor("#111018"))
        p.drawPath(path)
        p.restore()

    def _paint_pill(self, p: QPainter, t: float) -> None:
        appear = _ease(t / 0.3) * (1.0 - _ease((t - 2.7) / 0.4))
        if appear <= 0.01:
            return
        fill = _ease((t - 0.25) / 1.1)
        done = _ease((t - 1.35) / 0.3)
        width, height = 250.0, 50.0
        rect = QRectF(self.width() / 2 - width / 2, self.height() - height - 18, width, height)
        p.save()
        p.setOpacity(appear)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        glass.soft_shadow(p, rect, 18, 14, QColor(0, 0, 0, 80), QPointF(0, 6))
        glass.paint_glass(p, path, self.dark, None, lift=0.2)
        p.save()
        p.setClipPath(path)
        rtl = i18n.is_rtl()
        level = rect.width() * fill
        liquid = QRectF(rect.right() - level, rect.top(), level, rect.height()) if rtl else \
            QRectF(rect.left(), rect.top(), level, rect.height())
        p.fillRect(liquid, QColor(255, 255, 255, 70))
        p.restore()
        orb = QPointF(rect.right() - 25 if rtl else rect.left() + 25, rect.center().y())
        glass.paint_glass(p, glass.circle(orb, 15), self.dark, None, lift=0.6)
        pen = QPen(QColor("#FFFFFF"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if done > 0.05:
            tick = QPainterPath(QPointF(orb.x() - 6, orb.y()))
            tick.lineTo(orb.x() - 1.5, orb.y() + 4.5)
            tick.lineTo(orb.x() + 6.5, orb.y() - 4.5)
            p.drawPath(tick)
        else:
            p.drawArc(QRectF(orb.x() - 6, orb.y() - 6, 12, 12), int(-t * 900 * 16) % (360 * 16), 250 * 16)
        p.setFont(glass.font(13, QFont.Weight.DemiBold))
        text = i18n.tr("progress.saved_beside") if done > 0.5 else i18n.tr("wheel.to_format", target="PDF")
        area = rect.adjusted(14, 0, -48, 0) if rtl else rect.adjusted(48, 0, -14, 0)
        glass.text(p, area, int((Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
                                | Qt.AlignmentFlag.AlignVCenter), text, QColor("#FFFFFF"))
        p.restore()


class _Step(QWidget):
    """One numbered step; lights up while the demo plays it."""

    def __init__(self, number: int, text: str, parent=None):
        super().__init__(parent)
        self.number = number
        self.text = text
        self.active = False
        self.setFixedHeight(40)

    def set_active(self, flag: bool) -> None:
        if flag != self.active:
            self.active = flag
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(520, 40)

    def paintEvent(self, event) -> None:
        dark = theme.is_dark()
        t = glass.tokens(dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        glass.paint_glass(p, path, dark, None, specular=0.4, lift=0.5 if self.active else 0.0)
        rtl = i18n.is_rtl()
        badge_c = QPointF(rect.right() - 22 if rtl else rect.left() + 22, rect.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        if self.active:
            p.setBrush(QColor("#FFFFFF") if dark else QColor("#1C1C1E"))
            p.drawEllipse(badge_c, 14, 14)
        else:
            glass.paint_glass(p, glass.circle(badge_c, 14), dark, None, specular=0.5)
        p.setPen((QColor("#111114") if dark else QColor("#FFFFFF")) if self.active else t.ink)
        p.setFont(glass.font(13, QFont.Weight.Bold, label=True))
        p.drawText(QRectF(badge_c.x() - 14, badge_c.y() - 14, 28, 28), int(Qt.AlignmentFlag.AlignCenter),
                   str(self.number))
        p.setPen(t.ink if self.active else t.ink_dim)
        p.setFont(glass.font(14, QFont.Weight.DemiBold if self.active else QFont.Weight.Normal))
        area = rect.adjusted(14, 0, -46, 0) if rtl else rect.adjusted(46, 0, -14, 0)
        p.drawText(area, int((Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
                             | Qt.AlignmentFlag.AlignVCenter), self.text)
        p.end()


class HomeWindow(QWidget):
    """Welcome + home: the demo, three steps and a few shortcuts."""

    def __init__(self, controller=None):
        super().__init__(None)
        self.controller = controller
        self.setWindowTitle(i18n.tr("app.name"))
        self.setWindowIcon(QPixmap(str(paths.icon_png())))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setProperty("glassWindow", True)
        self.setLayoutDirection(theme.direction())
        self.setFixedSize(620, 660)
        self._acrylic = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 16, 26, 16)
        layout.setSpacing(8)

        title = QLabel(i18n.tr("welcome.title"))
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel(i18n.tr("welcome.subtitle"))
        subtitle.setStyleSheet("font-size: 15px;")
        subtitle.setProperty("muted", True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.stage = DemoStage(self)
        layout.addWidget(self.stage, 1)

        self.steps = [_Step(i + 1, i18n.tr(f"welcome.step{i + 1}"), self) for i in range(3)]
        for step in self.steps:
            layout.addWidget(step)

        alt = QLabel(i18n.tr("welcome.alt"))
        alt.setProperty("muted", True)
        alt.setWordWrap(True)
        layout.addWidget(alt)

        row = QHBoxLayout()
        row.setSpacing(10)
        edit = QPushButton(i18n.tr("tray.edit_pdf"))
        edit.clicked.connect(self._edit_pdf)
        settings_btn = QPushButton(i18n.tr("tray.settings"))
        settings_btn.clicked.connect(self._settings)
        start = QPushButton(i18n.tr("welcome.start"))
        start.setProperty("accent", True)
        start.setMinimumWidth(120)
        start.clicked.connect(self.close)
        for button in (edit, settings_btn):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button)
        row.addStretch(1)
        start.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(start)
        layout.addLayout(row)

        running = QLabel(i18n.tr("welcome.running"))
        running.setProperty("muted", True)
        running.setStyleSheet("font-size: 12px;")
        layout.addWidget(running)

        self._sync = QTimer(self)
        self._sync.setInterval(60)
        self._sync.timeout.connect(self._sync_steps)

    def present(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._acrylic = theme.glass_window(self)
        self._sync.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync.stop()

    def _sync_steps(self) -> None:
        for index, step in enumerate(self.steps):
            step.set_active(index == self.stage.step)

    def _edit_pdf(self) -> None:
        if self.controller is not None:
            self.controller.open_pdf()

    def _settings(self) -> None:
        if self.controller is not None:
            self.controller.open_settings()

    def paintEvent(self, event) -> None:
        dark = theme.is_dark()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._acrylic:
            p.fillRect(self.rect(), theme.window_tint(dark))
        else:
            p.fillRect(self.rect(), QColor(theme.palette(dark)["window"]))
        p.end()
