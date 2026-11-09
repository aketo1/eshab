"""The liquid wheel: drops of glass around the dragged file.

How it behaves
--------------
* It opens centred on the pointer while a file is being dragged and a
  shortcut is held.  The file sits in a glass *orb* in the middle and the
  targets split off it as drops, each one pulling a liquid neck that snaps.
* Selection is **directional**: once the pointer leaves the orb, the drop in
  that direction is chosen, whatever the distance.  There are no gaps to
  miss.  The orb itself is the cancel zone, and the cursor says so.
* The chosen drop brightens and swells, a clear liquid bridge reaches out
  to it from the orb, and a clear glass lens slides along the ring and
  magnifies it.
* Releasing the file emits :attr:`LiquidWheel.activated` immediately; the
  wheel then plays a short farewell without blocking anything.

Rendering lives in :class:`WheelScene` so the welcome window can play the
very same wheel as a live demo.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import QFileInfo, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal, QRunnable, QThreadPool, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QFileIconProvider, QWidget

from . import glass, i18n, paths as app_paths, settings, theme
from .icons import icon_for, paint_icon  # noqa: F401 (icon_for is a re-export)

log = logging.getLogger("eshab")


class _PreviewSignals(QObject):
    ready = Signal(str, QImage)


class _PreviewTask(QRunnable):
    """Decode away from the GUI; QPixmap is created only after delivery."""

    def __init__(self, path, signals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self):
        image = QImage()
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                size.scale(96, 96, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
            image = reader.read()
            if image.isNull() and Path(self.path).suffix.lower() in {".heic", ".heif", ".avif"}:
                from PIL import Image, ImageOps
                import pillow_heif
                pillow_heif.register_heif_opener()
                with Image.open(self.path) as source:
                    source.thumbnail((96, 96))
                    source = ImageOps.exif_transpose(source).convert("RGBA")
                    data = source.tobytes()
                    image = QImage(data, source.width, source.height, source.width * 4, QImage.Format.Format_RGBA8888).copy()
        except Exception:
            log.debug("No asynchronous preview for %s", self.path, exc_info=True)
        self.signals.ready.emit(self.path, image)

# -- geometry ---------------------------------------------------------------
EXTENT = 250.0            # half the window side
ORB_R = 44.0
DEAD_ZONE = ORB_R + 8.0   # inside: cancel; outside: the drop in that direction
DROP_R = 34.0
TOOL_DROP_R = 42.0
RING = 152.0
RING_MAX = 196.0
LENS_SCALE = 1.52         # lens radius / drop radius
LENS_MAG = 1.16
PILL_H = 32.0
CHIP_H = 26.0

# Kept for callers that size things from the old wheel.
R_OUT = RING + DROP_R
R_IN = DEAD_ZONE


@dataclass
class FanItem:
    """One target: ``kind`` is ``"conversion"`` or ``"tool"``."""

    key: str
    label: str
    icon: str = ""
    kind: str = "conversion"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _polar(center: QPointF, degrees: float, radius: float) -> QPointF:
    radians = math.radians(degrees)
    return QPointF(center.x() + math.cos(radians) * radius, center.y() + math.sin(radians) * radius)


def mode_label(mode: str) -> str:
    return i18n.tr({"tools": "wheel.tools", "actions": "wheel.actions"}.get(mode, "wheel.convert"))


def file_preview(path: str, size: int = 96) -> QPixmap:
    """A thumbnail for images and PDFs, else the Windows shell icon."""
    pixmap = QPixmap()
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        if reader.canRead():
            source = reader.size()
            if source.isValid():
                source.scale(size, size, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(source)
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
        if pixmap.isNull() and path.lower().endswith(".pdf"):
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(path)
            try:
                page = document[0]
                scale = size / max(page.get_width(), page.get_height())
                image = page.render(scale=scale).to_pil()
                data = image.convert("RGBA").tobytes("raw", "RGBA")
                qimage = QImage(data, image.width, image.height, image.width * 4,
                                QImage.Format.Format_RGBA8888).copy()
                pixmap = QPixmap.fromImage(qimage)
            finally:
                document.close()
    except Exception:
        log.debug("No preview for %s", path, exc_info=True)
    if pixmap.isNull():
        pixmap = QFileIconProvider().icon(QFileInfo(path)).pixmap(QSize(64, 64))
    return pixmap


class WheelScene(QObject):
    """State, motion and painting of one wheel (window or demo)."""

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        self.widget = widget
        self.items: list[FanItem] = []
        self.mode = "conversion"
        self.modes: list[str] = ["conversion", "tools"]
        self.dark = theme.is_dark()
        self.backdrop = glass.Backdrop()
        self.files: list[str] = []
        self.preview = QPixmap()
        self.hover = -1
        self.waiting = False
        self.message = ""
        self._preview_path = ""
        self._phase = 0.0
        self._layer: QImage | None = None
        self._drop_cache = {}
        self._layer_key = None
        self._preview_signals = _PreviewSignals()
        self._preview_signals.ready.connect(self._preview_ready, Qt.ConnectionType.QueuedConnection)
        self._preview_cache = {}

        self.orb = glass.Spring(0.0, 300.0, 21.0)
        self.fade = glass.Spring(0.0, 260.0, 30.0)
        self.lens = glass.Spring(0.0, 380.0, 26.0)
        self.lens_angle = glass.Spring(-90.0, 300.0, 27.0)
        self.reach = glass.Spring(0.0, 210.0, 19.0)
        self.flash = glass.Spring(0.0, 240.0, 26.0)
        self.label_swap = glass.Spring(1.0, 520.0, 40.0)
        self.births: list[glass.Spring] = []
        self.hovers: list[glass.Spring] = []
        self.animator = glass.Animator(widget, self._tick)
        self.animator.track(self.orb, self.fade, self.lens, self.lens_angle, self.reach,
                            self.flash, self.label_swap)

    # -- content --------------------------------------------------------

    def set_items(self, items: Sequence[FanItem], animate: bool = True) -> None:
        self.items = list(items)
        self._drop_cache.clear()
        self._layer_key = None
        self.animator.forget(*self.births, *self.hovers)
        self.births = [glass.Spring(0.0, 250.0, 17.5) for _ in self.items]
        self.hovers = [glass.Spring(0.0, 520.0, 34.0) for _ in self.items]
        self.animator.track(*self.births, *self.hovers)
        self.hover = -1
        self.lens.snap(0.0)
        self.reach.snap(0.0)
        if animate:
            for index, spring in enumerate(self.births):
                spring.to(1.0, delay=0.03 + index * 0.024)
        else:
            for spring in self.births:
                spring.snap(1.0)
        self.animator.kick()

    def set_files(self, files: Sequence[str] | None) -> None:
        self.files = [str(path) for path in (files or [])]
        first = self.files[0] if self.files else ""
        if first != self._preview_path:
            self._preview_path = first
            self.preview = QPixmap()
            if first:
                # Thumbnails can take a moment (video, big photos): the drops
                # bloom first and the preview fades in right after.
                QTimer.singleShot(0, lambda path=first: self._load_preview(path))
        self.widget.update()

    def _load_preview(self, path: str) -> None:
        if path != self._preview_path:
            return
        try:
            stat = Path(path).stat()
            key = (path, stat.st_mtime_ns, stat.st_size)
        except OSError:
            return
        cached = self._preview_cache.get(key)
        if cached is not None:
            self.preview = cached
            self.widget.update()
            return
        QThreadPool.globalInstance().start(_PreviewTask(path, self._preview_signals))

    @Slot(str, QImage)
    def _preview_ready(self, path, image):
        if path != self._preview_path or image.isNull():
            return
        self.preview = QPixmap.fromImage(image)
        try:
            stat = Path(path).stat()
            if len(self._preview_cache) >= 12:
                self._preview_cache.pop(next(iter(self._preview_cache)))
            self._preview_cache[(path, stat.st_mtime_ns, stat.st_size)] = self.preview
        except OSError:
            pass
        self.widget.update()

    def appear(self) -> None:
        self.dark = theme.is_dark()
        self.fade.snap(0.0).to(1.0)
        self.orb.snap(0.0).to(1.0)
        self.flash.snap(0.0)
        for index, spring in enumerate(self.births):
            spring.snap(0.0).to(1.0, delay=0.03 + index * 0.024)
        self.animator.kick()

    def depart(self, chosen: int = -1) -> None:
        """Pull everything back into the orb; *chosen* flashes first."""
        self.fade.to(0.0, delay=0.12 if chosen >= 0 else 0.0)
        self.orb.to(0.55)
        for index, spring in enumerate(self.births):
            if index != chosen:
                spring.to(0.0)
        if chosen >= 0:
            self.flash.snap(0.0).to(1.0)
        self.lens.to(0.0)
        self.reach.to(0.0)
        self.animator.kick()

    def clear(self) -> None:
        self.items = []
        self.animator.forget(*self.births, *self.hovers)
        self.births, self.hovers = [], []
        self.files = []
        self._preview_path = ""
        self.preview = QPixmap()
        self.hover = -1
        self.waiting = False
        for spring in (self.orb, self.fade, self.lens, self.reach, self.flash):
            spring.snap(0.0)
        self.label_swap.snap(1.0)
        self.animator.stop()
        self.widget.update()

    # -- geometry -------------------------------------------------------

    def center(self) -> QPointF:
        return QPointF(self.widget.width() / 2.0, self.widget.height() / 2.0)

    def drop_radius(self) -> float:
        return TOOL_DROP_R if self.items and self.items[0].kind == "tool" else DROP_R

    def ring(self) -> float:
        count = max(1, len(self.items))
        needed = count * (2.0 * self.drop_radius() + 14.0) / (2.0 * math.pi)
        return min(RING_MAX, max(RING, needed))

    def angle_of(self, index: int) -> float:
        count = max(1, len(self.items))
        return -90.0 + index * 360.0 / count

    def hit_test(self, local: QPointF) -> int:
        count = len(self.items)
        if count == 0:
            return -1
        center = self.center()
        dx, dy = local.x() - center.x(), local.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance < DEAD_ZONE:
            return -1
        angle = math.degrees(math.atan2(dy, dx))
        step = 360.0 / count
        return int(round(((angle + 90.0) % 360.0) / step)) % count

    def set_hover(self, index: int) -> bool:
        if index == self.hover or index >= len(self.items):
            return False
        previous = self.hover
        self.hover = index
        for position, spring in enumerate(self.hovers):
            spring.to(1.0 if position == index else 0.0)
        if index >= 0:
            target = self.angle_of(index)
            if previous < 0 or self.lens.value < 0.05:
                self.lens_angle.snap(target)
            else:
                current = self.lens_angle.value
                target = current + ((target - current + 540.0) % 360.0 - 180.0)
                self.lens_angle.to(target)
            self.lens.to(1.0)
            self.reach.snap(0.0).to(1.0)
        else:
            self.lens.to(0.0)
            self.reach.to(0.0)
        self.label_swap.snap(0.0).to(1.0)
        self.animator.kick()
        return True

    # -- motion ---------------------------------------------------------

    def _tick(self, elapsed: float) -> bool:
        self._phase = (self._phase + elapsed * (140.0 if self.waiting else 40.0)) % 360.0
        return self.waiting

    # -- painting -------------------------------------------------------

    def paint(self, p: QPainter, catch_drops: bool = True) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        center = self.center()
        fade = _clamp(self.fade.value)
        if catch_drops:
            # Layered windows only receive drops where a pixel is painted.
            # An almost invisible disc turns the whole wheel into a target.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 2))
            p.drawEllipse(center, EXTENT - 2.0, EXTENT - 2.0)
        if fade <= 0.003:
            return
        p.save()
        p.setOpacity(fade)
        self._paint_pool(p, center)
        self._paint_bridges(p, center)
        layer = self._paint_layer()
        if layer is not None:
            p.drawImage(QRectF(0, 0, self.widget.width(), self.widget.height()), layer)
        self._paint_orb(p, center)
        self._paint_lens(p, center, layer)
        self._paint_label(p, center)
        self._paint_modes(p, center)
        p.restore()

    def _drop_center(self, center: QPointF, index: int) -> QPointF:
        birth = self.births[index].value if index < len(self.births) else 1.0
        return _polar(center, self.angle_of(index), self.ring() * birth)

    def _paint_pool(self, p: QPainter, center: QPointF) -> None:
        """A barely-there shadow behind the cluster (no colour)."""
        radius = (self.ring() + self.drop_radius() + 30.0) * (0.75 + 0.25 * _clamp(self.orb.value))
        gradient = QRadialGradient(center, radius)
        shade = QColor(0, 0, 0, 46 if self.dark else 22)
        gradient.setColorAt(0.0, shade)
        gradient.setColorAt(0.7, glass.with_alpha(shade, 0.55))
        gradient.setColorAt(1.0, glass.with_alpha(shade, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(center, radius, radius)

    def _paint_bridges(self, p: QPainter, center: QPointF) -> None:
        orb_r = ORB_R * _clamp(self.orb.value, 0.0, 1.3)
        drop_r = self.drop_radius()
        # Birth necks: every drop splits off the orb and the neck snaps.
        for index, spring in enumerate(self.births):
            birth = spring.value
            if birth <= 0.02 or birth >= 0.72 or index == self.hover:
                continue
            strength = 1.0 - birth / 0.72
            target = self._drop_center(center, index)
            radius = drop_r * (0.42 + 0.58 * min(1.0, birth)) * 0.9
            path = glass.liquid_bridge(center, orb_r * 0.92, target, radius, 0.55 * strength)
            if path is not None:
                glass.paint_glass(p, path, self.dark, self.backdrop, opacity=strength,
                                  rim=0.6, specular=0.0)
        if self.hover < 0 or self.hover >= len(self.items):
            return
        reach = _clamp(self.reach.value, 0.0, 1.15)
        if reach <= 0.02:
            return
        target = self._drop_center(center, self.hover)
        end = QPointF(center.x() + (target.x() - center.x()) * reach,
                      center.y() + (target.y() - center.y()) * reach)
        path = glass.liquid_bridge(center, orb_r * 0.9, end, drop_r * (0.45 + 0.4 * reach),
                                   0.18 + 0.14 * (1.0 - reach))
        if path is not None:
            glass.paint_glass(p, path, self.dark, self.backdrop, magnify=1.08, rim=0.8,
                              specular=0.0, lift=0.4 * reach)

    def _paint_layer(self) -> QImage | None:
        if not self.items:
            return None
        ratio = float(self.widget.devicePixelRatioF() or 1.0)
        width = max(2, int(self.widget.width() * ratio))
        height = max(2, int(self.widget.height() * ratio))
        key = (width, height, ratio, self.dark, self.hover, round(self.flash.value, 3),
               getattr(self.backdrop, "generation", 0),
               tuple(round(s.value, 3) for s in self.births),
               tuple(round(s.value, 3) for s in self.hovers))
        if key == self._layer_key and self._layer is not None:
            return self._layer
        if self._layer is None or self._layer.width() != width or self._layer.height() != height:
            self._layer = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        layer = self._layer
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.GlobalColor.transparent)
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        center = self.center()
        t = glass.tokens(self.dark)
        flash = _clamp(self.flash.value)
        for index, item in enumerate(self.items):
            birth = self.births[index].value
            if birth <= 0.01:
                continue
            hover = _clamp(self.hovers[index].value)
            grow = _clamp(birth, 0.0, 1.25)
            radius = self.drop_radius() * (0.42 + 0.58 * min(1.0, grow)) * (1.0 + 0.06 * hover)
            if index == self.hover:
                radius *= 1.0 + 0.22 * flash
            point = self._drop_center(center, index)
            opacity = _clamp(birth * 1.8)
            sprite_key = (self.dark, ratio, round(point.x(), 2), round(point.y(), 2),
                          round(radius, 2), round(hover, 3), round(opacity, 3),
                          round(flash, 3) if index == self.hover else 0,
                          getattr(self.backdrop, "generation", 0))
            cached = self._drop_cache.get(index)
            if cached is not None and cached[0] == sprite_key:
                painter.drawImage(cached[2], cached[1])
                continue
            extent = math.ceil(radius * 1.65 + 12)
            origin = QPointF(math.floor(point.x() - extent), math.floor(point.y() - extent))
            sprite = QImage(math.ceil(extent * 2 * ratio), math.ceil(extent * 2 * ratio), QImage.Format.Format_ARGB32_Premultiplied)
            sprite.setDevicePixelRatio(ratio)
            sprite.fill(Qt.GlobalColor.transparent)
            detail = QPainter(sprite)
            detail.setRenderHints(painter.renderHints())
            detail.translate(-origin)
            self._paint_drop(detail, item, point, radius, hover, flash if index == self.hover else 0, opacity, t)
            detail.end()
            self._drop_cache[index] = (sprite_key, sprite, origin)
            painter.drawImage(origin, sprite)
        painter.end()
        self._layer_key = key
        return layer

    def _paint_drop(self, painter, item, point, radius, hover, flash, opacity, t):
        painter.save()
        painter.setOpacity(opacity)
        glass.drop_shadow(painter, point, radius, glass.with_alpha(t.shadow, 0.7 + 0.4 * hover),
                          lift=4.0 + 3.0 * hover)
        path = glass.circle(point, radius)
        glass.paint_glass(painter, path, self.dark, self.backdrop, magnify=1.18, lift=hover)
        if flash > 0.01:
            glass.glow(painter, point, radius * 1.5, QColor(255, 255, 255), flash)
        box = QRectF(point.x() - radius, point.y() - radius, radius * 2.0, radius * 2.0)
        ink = glass.glass_ink(self.backdrop, box, self.dark, hover)
        self._paint_content(painter, item, point, radius, ink)
        painter.restore()

    def _paint_content(self, p: QPainter, item: FanItem, point: QPointF, radius: float, ink: QColor) -> None:
        scale = radius / self.drop_radius()
        if item.kind == "tool":
            icon = 22.0 * scale
            paint_icon(p, item.key, QRectF(point.x() - icon / 2.0, point.y() - icon * 0.92, icon, icon),
                       ink, 1.8 * scale)
            label_font = glass.font(11.5 * scale, QFont.Weight.Bold)
            metrics = QFontMetricsF(label_font)
            width = radius * 1.84
            text = metrics.elidedText(item.label, Qt.TextElideMode.ElideRight, width)
            p.setFont(label_font)
            glass.text(p, QRectF(point.x() - width / 2.0, point.y() + icon * 0.18, width, 18.0 * scale),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), text, ink)
            return
        text = item.label.upper()
        size = 15.5 if len(text) <= 3 else 14.0 if len(text) == 4 else 12.0
        label_font = glass.font(size * scale, QFont.Weight.Bold, label=True)
        p.setFont(label_font)
        box = QRectF(point.x() - radius, point.y() - radius, radius * 2.0, radius * 2.0)
        glass.text(p, box, int(Qt.AlignmentFlag.AlignCenter), text, ink)

    def _paint_orb(self, p: QPainter, center: QPointF) -> None:
        grow = _clamp(self.orb.value, 0.0, 1.3)
        if grow <= 0.01:
            return
        t = glass.tokens(self.dark)
        radius = ORB_R * grow
        glass.drop_shadow(p, center, radius, t.shadow, lift=7.0)
        path = glass.circle(center, radius)
        glass.paint_glass(p, path, self.dark, self.backdrop, magnify=1.22, clear=True,
                          lift=0.25 * _clamp(self.reach.value))
        if self.waiting or not self.items:
            # Waiting for the payload: a soft white arc circles the rim.
            pen = QPen(QColor(255, 255, 255, 200), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            ring = QRectF(center.x() - radius + 3, center.y() - radius + 3, radius * 2 - 6, radius * 2 - 6)
            p.drawArc(ring, int(-self._phase * 16 * 2), 70 * 16)
        if not self.preview.isNull():
            ratio = float(self.widget.devicePixelRatioF() or 1.0)
            box = radius * 1.08
            pix = self.preview.scaled(QSize(int(box * ratio), int(box * ratio)),
                                      Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            w = pix.width() / ratio
            h = pix.height() / ratio
            rect = QRectF(center.x() - w / 2.0, center.y() - h / 2.0, w, h)
            if len(self.files) > 1:
                for depth in (2, 1):
                    if len(self.files) > depth:
                        back = rect.translated(5.0 * depth, -4.0 * depth)
                        p.save()
                        p.setOpacity(p.opacity() * (0.55 / depth))
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(255, 255, 255, 200))
                        p.drawRoundedRect(back, 8.0, 8.0)
                        p.restore()
            clip = QPainterPath()
            clip.addRoundedRect(rect, 9.0 * grow, 9.0 * grow)
            p.save()
            # The orb already has a shadow; avoid a Gaussian blur for every
            # thumbnail size during the birth spring.
            p.setClipPath(clip)
            p.drawPixmap(rect, pix, QRectF(pix.rect()))
            p.restore()
        if len(self.files) > 1:
            badge = _polar(center, -45.0, radius * 0.98)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawEllipse(badge, 11.0, 11.0)
            p.setPen(QColor("#111114"))
            p.setFont(glass.font(11, QFont.Weight.Bold, label=True))
            p.drawText(QRectF(badge.x() - 11, badge.y() - 11, 22, 22), int(Qt.AlignmentFlag.AlignCenter),
                       str(len(self.files)) if len(self.files) < 100 else "99+")

    def _paint_lens(self, p: QPainter, center: QPointF, layer: QImage | None) -> None:
        presence = _clamp(self.lens.value, 0.0, 1.2)
        if presence <= 0.02 or layer is None or not self.items:
            return
        radius = self.drop_radius() * LENS_SCALE * presence
        hover = self.hover if self.hover >= 0 else 0
        birth = self.births[hover].value if hover < len(self.births) else 1.0
        spot = _polar(center, self.lens_angle.value, self.ring() * birth)
        mag = 1.0 + (LENS_MAG - 1.0) * min(1.0, presence)
        p.save()
        p.setClipPath(glass.circle(spot, radius))
        box = QRectF(spot.x() - radius, spot.y() - radius, radius * 2.0, radius * 2.0)
        self.backdrop.draw(p, box, magnify=mag, clear=True)
        p.translate(spot)
        p.scale(mag, mag)
        p.translate(-spot)
        p.drawImage(QRectF(0, 0, self.widget.width(), self.widget.height()), layer)
        p.restore()
        glass.paint_lens(p, spot, radius, self.dark, min(1.0, presence))

    def _label_text(self) -> str:
        if self.message:
            return self.message
        if 0 <= self.hover < len(self.items):
            item = self.items[self.hover]
            if item.kind == "conversion":
                return i18n.tr("wheel.to_format", target=item.label.upper())
            return item.label
        if self.waiting or (not self.items and not self.files):
            return i18n.tr("wheel.reading")
        if not self.items:
            return i18n.tr("wheel.nothing")
        if len(self.files) > 1:
            return i18n.tr("wheel.files_count", n=len(self.files))
        return mode_label(self.mode)

    def _paint_label(self, p: QPainter, center: QPointF) -> None:
        grow = _clamp(self.orb.value)
        if grow <= 0.05:
            return
        t = glass.tokens(self.dark)
        text = self._label_text()
        label_font = glass.font(14.5, QFont.Weight.Bold)
        metrics = QFontMetricsF(label_font)
        text = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, 280.0)
        width = max(108.0, metrics.horizontalAdvance(text) + 36.0)
        swap = _clamp(self.label_swap.value)
        top = center.y() + ORB_R + 14.0 + 4.0 * (1.0 - swap)
        rect = QRectF(center.x() - width / 2.0, top, width, PILL_H)
        path = glass.pill(rect)
        hovered = 0 <= self.hover < len(self.items)
        p.save()
        p.setOpacity(p.opacity() * grow)
        glass.soft_shadow(p, rect, PILL_H / 2.0, 12.0, glass.with_alpha(t.shadow, 0.7), QPointF(0, 4))
        glass.paint_glass(p, path, self.dark, self.backdrop, magnify=1.05, specular=0.6,
                          lift=0.5 if hovered else 0.0)
        p.setOpacity(p.opacity() * (0.35 + 0.65 * swap))
        p.setFont(label_font)
        ink = glass.glass_ink(self.backdrop, rect, self.dark, 0.5 if hovered else 0.0)
        glass.text(p, rect, int(Qt.AlignmentFlag.AlignCenter), text, ink)
        p.restore()

    def chip_rects(self, center: QPointF | None = None) -> list[tuple[str, QRectF]]:
        """No mode chips: the label under the orb names the mode (simpler)."""
        return []

    def _paint_modes(self, p: QPainter, center: QPointF) -> None:
        return


class LiquidWheel(QWidget):
    """The on-screen wheel window driven by the drag monitor."""

    activated = Signal(list, str)
    closed = Signal()
    modeRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setWindowTitle("Eshab")
        self.resize(int(EXTENT * 2), int(EXTENT * 2))
        self.scene = WheelScene(self)
        self._factory: Callable[[list[str]], Sequence[FanItem]] | None = None
        self._prompt: tuple[str, str] = ("", "")
        self._keyboard_mode = False
        self._accepting = True
        self._farewell = 0
        self._sound = None
        self._sound_disabled = False
        theme.add_theme_listener(self._on_theme_change)
        self.destroyed.connect(lambda *_: theme.remove_theme_listener(self._on_theme_change))
        screen = QGuiApplication.primaryScreen()
        refresh = screen.refreshRate() if screen is not None else 60.0
        self.scene.animator._timer.setInterval(max(6, min(16, int(1000.0 / max(30.0, refresh)))))

    # -- compatibility helpers -------------------------------------------

    @property
    def _items(self) -> list[FanItem]:
        return self.scene.items

    @property
    def _file_paths(self) -> list[str]:
        return self.scene.files

    @property
    def _hover(self) -> int:
        return self.scene.hover

    # -- public API -----------------------------------------------------

    def set_factory(self, factory: Callable[[list[str]], Sequence[FanItem]]) -> None:
        self._factory = factory

    def set_mode(self, mode: str) -> None:
        self.scene.mode = mode
        self.update()

    def set_modes(self, modes: Sequence[str]) -> None:
        self.scene.modes = list(modes)
        self.update()

    def set_items(self, items: Sequence[FanItem], animate: bool = False) -> None:
        replay = animate or (self.isVisible() and len(items) != len(self.scene.items))
        self.scene.waiting = False
        self.scene.set_items(items, animate=replay or not self.isVisible())
        self.update()

    def set_prompt(self, main: str, sub: str = "") -> None:
        self._prompt = (str(main), str(sub))

    def set_files(self, files: Sequence[str] | None) -> None:
        self.scene.set_files(files)

    def file_paths(self) -> list[str]:
        return list(self.scene.files)

    def center_at(self, global_pos: QPoint) -> None:
        center = QPoint(global_pos)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            margin = int(self.scene.ring() + self.scene.drop_radius() + 12)
            left, right = area.left() + margin, area.right() - margin
            if left <= right:
                center.setX(min(max(center.x(), left), right))
            top, bottom = area.top() + margin + 34, area.bottom() - margin
            if top <= bottom:
                center.setY(min(max(center.y(), top), bottom))
        self.move(center.x() - int(EXTENT), center.y() - int(EXTENT))
        if not self.isVisible():
            self.scene.backdrop.capture(self.frameGeometry())

    def update_cursor(self, global_pos: QPoint) -> None:
        if self._accepting:
            self._set_hover(self.scene.hit_test(QPointF(self.mapFromGlobal(global_pos))))

    def hit_test(self, local: QPointF) -> int:
        return self.scene.hit_test(local)

    def reset(self) -> None:
        self._farewell += 1
        self.scene.clear()
        self.scene.message = ""
        self._accepting = True

    def set_keyboard_mode(self, flag: bool) -> None:
        flag = bool(flag)
        if flag == self._keyboard_mode:
            return
        self._keyboard_mode = flag
        visible = self.isVisible()
        if flag:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, False)
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.clearFocus()
            self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            if visible:
                self.show()

    def play_appearance(self) -> None:
        self.scene.appear()

    def dismiss(self) -> None:
        """Animated farewell, then hide and reset (cancelled gesture)."""
        if not self.isVisible():
            return
        self._accepting = False
        self._farewell += 1
        token = self._farewell
        self.scene.depart()
        self._after(220, token, self._finish_farewell)

    def cancel_dismiss(self) -> None:
        """A new gesture started while the farewell was still playing."""
        self._farewell += 1
        self._accepting = True
        if self.isVisible():
            self.scene.fade.to(1.0)
            self.scene.orb.to(1.0)
            for spring in self.scene.births:
                spring.to(1.0)
            self.scene.animator.kick()

    def _close(self) -> None:
        self.reset()
        self.hide()
        self.closed.emit()

    # -- internals ------------------------------------------------------

    def _after(self, ms: int, token: int, callback) -> None:
        QTimer.singleShot(ms, lambda: callback() if token == self._farewell else None)

    def _finish_farewell(self) -> None:
        self.hide()
        self.reset()

    def _set_hover(self, index: int) -> None:
        if self.scene.set_hover(index) and index >= 0:
            self._play_highlight()

    def _activate(self, index: int) -> None:
        if not (0 <= index < len(self.scene.items)):
            return
        key = self.scene.items[index].key
        files = list(self.scene.files)
        self._accepting = False
        self.scene.set_hover(index)
        self._farewell += 1
        token = self._farewell
        self.scene.depart(chosen=index)
        self._after(280, token, self._finish_farewell)
        self.activated.emit(files, key)

    def _play_highlight(self) -> None:
        if self._sound_disabled or not settings.get("soundsAndHapticsEnabled"):
            return
        try:
            if self._sound is None:
                from PySide6.QtMultimedia import QSoundEffect

                self._sound = QSoundEffect(self)
                self._sound.setSource(QUrl.fromLocalFile(str(app_paths.highlight_sound())))
                self._sound.setVolume(0.45)
            self._sound.play()
        except Exception:
            self._sound_disabled = True
            log.warning("Highlight sound disabled", exc_info=True)

    def _merge_files(self, payload: list[str]) -> list[str]:
        """Keep the full selection when the OLE payload collapsed it."""
        known = self.scene.files
        if known and len(payload) < len(known) and set(payload) <= set(known):
            return list(known)
        return payload

    @staticmethod
    def _local_files(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def _accept(self, event, position: QPointF) -> None:
        """Copy-only, and only while the pointer points at a target.

        Refusing inside the orb shows the "no" cursor: dropping there is a
        visible cancel instead of a silent nothing.
        """
        if self._accepting and self.scene.hit_test(position) >= 0 and (
            event.possibleActions() & Qt.DropAction.CopyAction
        ):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    # -- drag and drop --------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if not self._accepting:
            event.ignore()
            return
        files = self._local_files(event)
        if not files:
            log.info("Drop enter ignored: no local files (formats=%s)", event.mimeData().formats())
            event.ignore()
            return
        files = self._merge_files(files)
        changed = files != self.scene.files
        self.scene.set_files(files)
        if (changed or not self.scene.items) and self._factory is not None:
            self.scene.waiting = False
            self.scene.set_items(self._factory(files), animate=True)
        log.info("Drop enter: %d file(s), %d target(s), mode=%s", len(files),
                 len(self.scene.items), self.scene.mode)
        # Accept the enter itself so move events keep flowing even while the
        # pointer is still inside the orb.
        if self.scene.items and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()
        self._set_hover(self.scene.hit_test(event.position()))

    def dragMoveEvent(self, event) -> None:
        position = event.position()
        self._set_hover(self.scene.hit_test(position) if self._accepting else -1)
        self._accept(event, position)

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(-1)

    def dropEvent(self, event) -> None:
        position = event.position()
        index = self.scene.hit_test(position) if self._accepting else -1
        log.info("Drop: target=%d of %d at (%.0f, %.0f)", index, len(self.scene.items),
                 position.x(), position.y())
        if index < 0 or not (event.possibleActions() & Qt.DropAction.CopyAction):
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self._activate(index)

    # -- mouse and keyboard (pinned wheel) ------------------------------

    def mouseMoveEvent(self, event) -> None:
        if self._accepting:
            self._set_hover(self.scene.hit_test(event.position()))

    def leaveEvent(self, event) -> None:
        self._set_hover(-1)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position()
        for mode, rect in self.scene.chip_rects():
            if rect.contains(position) and mode != self.scene.mode:
                self.modeRequested.emit(mode)
                event.accept()
                return
        index = self.scene.hit_test(position)
        if index >= 0:
            self._activate(index)
        else:
            self._close()
        event.accept()

    def wheelEvent(self, event) -> None:
        count = len(self.scene.items)
        delta = event.angleDelta().y()
        if count and delta:
            step = 1 if delta < 0 else -1
            current = self.scene.hover
            self._set_hover((current + step) % count if current >= 0 else (0 if step > 0 else count - 1))
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._close()
            event.accept()
            return
        count = len(self.scene.items)
        if count == 0:
            super().keyPressEvent(event)
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = -1 if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
            current = self.scene.hover
            self._set_hover((current + step) % count if current >= 0 else (0 if step > 0 else count - 1))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.scene.hover >= 0:
                self._activate(self.scene.hover)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    # -- appearance -----------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.scene.dark = theme.is_dark()
        if not self.scene.backdrop.ready():
            self.scene.backdrop.capture(self.frameGeometry())
        self.scene.waiting = not self.scene.items
        self._accepting = True
        self.scene.appear()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.scene.backdrop.reset()

    def _on_theme_change(self, dark: bool) -> None:
        self.scene.dark = bool(dark)
        self.scene._drop_cache.clear()
        self.scene._layer_key = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self.scene.paint(painter, catch_drops=True)
        painter.end()


# Older modules import the wheel under its previous name.
TangerineWheel = LiquidWheel
