"""Liquid glass: the material every Eshab surface is made of.

One small kit shared by the wheel, the progress pill, the welcome window and
the editors, so the whole app reads as one family:

* :class:`Backdrop` grabs the desktop behind a surface once and keeps two
  blurred copies of it, a frosted one for the glass body and a clearer one
  for lenses, so a surface can *refract* what is behind it;
* :func:`paint_glass` fills any shape with that material: refracted backdrop,
  tint, inner glow, a bright rim and a specular highlight;
* :func:`liquid_bridge` builds the gooey neck that joins two drops;
* :class:`Spring` / :class:`Animator` drive every motion with a damped
  spring, so animations can be interrupted mid-flight without jumps.

Only QtCore/QtGui are imported: the module is safe in headless tests.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from . import theme

from PySide6.QtCore import QElapsedTimer, QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

log = logging.getLogger("eshab")

try:  # Pillow ships with the app; stay importable without it.
    from PIL import Image, ImageFilter
except Exception:  # pragma: no cover
    Image = None
    ImageFilter = None


# -- identity ---------------------------------------------------------------
#
# Clear glass, no brand colours: the material takes its colour from whatever
# is behind it, like Liquid Glass on the iPhone.  The only colours left are
# functional (an error mark) and stay tiny.

SUCCESS = "#34C759"
DANGER = "#FF453A"

# Kept so older imports keep working; every one of them is neutral now.
VIOLET = VIOLET_LIGHT = VIOLET_DEEP = "#FFFFFF"
AQUA = AQUA_LIGHT = AQUA_DEEP = "#FFFFFF"
ROSE = ROSE_LIGHT = ROSE_DEEP = "#FFFFFF"


@dataclass(frozen=True)
class Tokens:
    ink: QColor
    ink_dim: QColor
    base: QColor        # whisper of tint under the sheen
    sheen_top: QColor
    sheen_bottom: QColor
    rim: QColor
    rim_soft: QColor
    shade: QColor       # inner shade at the bottom of a shape
    pool: QColor
    shadow: QColor


def tokens(dark: bool) -> Tokens:
    if dark:
        return Tokens(
            ink=QColor("#FFFFFF"),
            ink_dim=QColor(255, 255, 255, 215),
            base=QColor(10, 10, 14, 105),
            sheen_top=QColor(255, 255, 255, 52),
            sheen_bottom=QColor(255, 255, 255, 10),
            rim=QColor(255, 255, 255, 200),
            rim_soft=QColor(255, 255, 255, 48),
            shade=QColor(0, 0, 0, 68),
            pool=QColor(0, 0, 0, 0),
            shadow=QColor(0, 0, 0, 115),
        )
    return Tokens(
        ink=QColor("#0B0B0E"),
        ink_dim=QColor(11, 11, 14, 195),
        base=QColor(255, 255, 255, 135),
        sheen_top=QColor(255, 255, 255, 155),
        sheen_bottom=QColor(255, 255, 255, 38),
        rim=QColor(255, 255, 255, 255),
        rim_soft=QColor(255, 255, 255, 110),
        shade=QColor(0, 0, 0, 28),
        pool=QColor(0, 0, 0, 0),
        shadow=QColor(0, 0, 0, 70),
    )


def accent(mode: str = "") -> tuple[QColor, QColor, QColor]:
    """Neutral highlight (no brand colour): light, base, deep."""
    return QColor(255, 255, 255, 235), QColor(255, 255, 255, 210), QColor(255, 255, 255, 190)


def ink_for(luminance: float) -> QColor:
    """Black text on bright backgrounds, white text on dark ones."""
    return QColor("#111114") if luminance > 0.6 else QColor("#FFFFFF")


def glass_ink(backdrop: "Backdrop | None", rect: QRectF, dark: bool, lift: float = 0.0) -> QColor:
    """Ink for text *on* glass: the backdrop seen through the glass's own sheen."""
    behind = backdrop.luminance(rect, 0.15 if dark else 0.85) if backdrop is not None else (0.15 if dark else 0.85)
    alpha = theme.material_alpha(105 if dark else 135) / 255.
    seen = behind * (1 - alpha) + (.04 if dark else 1.) * alpha + .16 * lift
    return ink_for(seen)


def with_alpha(color: QColor, alpha: float) -> QColor:
    copy = QColor(color)
    copy.setAlphaF(max(0.0, min(1.0, color.alphaF() * alpha)))
    return copy


def mix(first: QColor, second: QColor, amount: float) -> QColor:
    t = max(0.0, min(1.0, amount))
    return QColor(
        round(first.red() + (second.red() - first.red()) * t),
        round(first.green() + (second.green() - first.green()) * t),
        round(first.blue() + (second.blue() - first.blue()) * t),
        round(first.alpha() + (second.alpha() - first.alpha()) * t),
    )


# -- type -------------------------------------------------------------------

#: Dubai ships with Windows 10/11 and draws Arabic and Latin in one voice;
#: Segoe UI Variable is the fallback everywhere else.
UI_FAMILIES = ["Dubai", "Segoe UI Variable Text", "Segoe UI"]
LABEL_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Dubai"]


def font(px: float, weight: QFont.Weight = QFont.Weight.Normal, *, label: bool = False) -> QFont:
    """A pixel-sized font; *label* picks the Latin display face (PDF, PNG)."""
    result = QFont()
    result.setFamilies(LABEL_FAMILIES if label else UI_FAMILIES)
    result.setPixelSize(max(6, int(round(px))))
    result.setWeight(weight)
    result.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if label:
        result.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104.0)
    return result


# -- motion -----------------------------------------------------------------


class Spring:
    """Damped spring; ``value`` chases ``target`` and may overshoot."""

    __slots__ = ("value", "velocity", "target", "stiffness", "damping", "delay")

    def __init__(self, value: float = 0.0, stiffness: float = 420.0, damping: float = 28.0):
        self.value = float(value)
        self.velocity = 0.0
        self.target = float(value)
        self.stiffness = stiffness
        self.damping = damping
        self.delay = 0.0

    def to(self, target: float, delay: float = 0.0) -> "Spring":
        self.target = float(target)
        self.delay = max(0.0, delay)
        return self

    def snap(self, value: float) -> "Spring":
        self.value = self.target = float(value)
        self.velocity = 0.0
        self.delay = 0.0
        return self

    def step(self, dt: float) -> None:
        if self.delay > 0.0:
            self.delay -= dt
            return
        force = -self.stiffness * (self.value - self.target) - self.damping * self.velocity
        self.velocity += force * dt
        self.value += self.velocity * dt

    @property
    def settled(self) -> bool:
        return (
            self.delay <= 0.0
            and abs(self.value - self.target) < 5e-4
            and abs(self.velocity) < 5e-3
        )


class Animator(QObject):
    """Steps a set of springs at display rate and repaints *widget*.

    The timer only runs while something is still moving.
    """

    SUBSTEP = 1.0 / 240.0

    def __init__(self, widget, on_tick=None):
        super().__init__(widget)
        self._widget = widget
        self._springs: list[Spring] = []
        self._on_tick = on_tick
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        screen = QGuiApplication.primaryScreen()
        refresh = screen.refreshRate() if screen is not None else 60.0
        self._timer.setInterval(max(8, round(1000 / max(60.0, min(120.0, refresh)))))
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()

    def track(self, *springs: Spring) -> None:
        for spring in springs:
            if spring not in self._springs:
                self._springs.append(spring)

    def forget(self, *springs: Spring) -> None:
        for spring in springs:
            if spring in self._springs:
                self._springs.remove(spring)

    def kick(self) -> None:
        if not self._timer.isActive():
            self._clock.restart()
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        elapsed = min(self._clock.restart() / 1000.0, 1.0 / 20.0)
        steps = max(1, int(math.ceil(elapsed / self.SUBSTEP)))
        dt = elapsed / steps
        for _ in range(steps):
            for spring in self._springs:
                spring.step(dt)
        busy = not all(spring.settled for spring in self._springs)
        if self._on_tick is not None:
            busy = bool(self._on_tick(elapsed)) or busy
        if not busy:
            for spring in self._springs:
                if spring.delay <= 0.0:
                    spring.value = spring.target
                    spring.velocity = 0.0
            self._timer.stop()
        self._widget.update()


# -- backdrop ---------------------------------------------------------------


class Backdrop:
    """The desktop behind a surface, blurred twice: ``frost`` and ``clear``.

    Paint with :meth:`draw` using widget-local rectangles; ``magnify`` > 1
    samples a smaller area, so the glass looks like a lens.
    """

    def __init__(self, frost: float = 9.0, clear: float = 2.2):
        self._frost_radius = frost
        self._clear_radius = clear
        self.frost: QImage | None = None
        self.clear: QImage | None = None
        self._size = (1.0, 1.0)
        self.generation = 0

    def ready(self) -> bool:
        return self.frost is not None

    def reset(self) -> None:
        self.generation += 1
        self.frost = self.clear = None

    def capture(self, global_rect: QRect) -> None:
        self.reset()
        if global_rect.width() < 4 or global_rect.height() < 4:
            return
        try:
            image = _grab(global_rect)
            if image is None or image.isNull():
                return
            self.use_image(image, (global_rect.width(), global_rect.height()))
        except Exception:
            log.debug("Backdrop capture failed; glass falls back to tint", exc_info=True)
            self.reset()

    def use_image(self, image: QImage, logical_size: tuple[float, float]) -> None:
        """Adopt *image* (already showing what is behind the surface)."""
        self.generation += 1
        self._size = (float(logical_size[0]), float(logical_size[1]))
        small = image.scaled(
            max(4, image.width() // 3),
            max(4, image.height() // 3),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.frost = _blur(small, self._frost_radius)
        medium = image.scaled(
            max(4, image.width() // 2),
            max(4, image.height() // 2),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.clear = _blur(medium, self._clear_radius)

    def luminance(self, rect: QRectF, fallback: float = 0.3) -> float:
        """Average brightness (0..1) of the frosted backdrop under *rect*."""
        image = self.frost
        if image is None:
            return fallback
        sx = image.width() / self._size[0]
        sy = image.height() / self._size[1]
        total, count = 0.0, 0
        for fx in (0.25, 0.5, 0.75):
            for fy in (0.25, 0.5, 0.75):
                x = int((rect.left() + rect.width() * fx) * sx)
                y = int((rect.top() + rect.height() * fy) * sy)
                if 0 <= x < image.width() and 0 <= y < image.height():
                    c = image.pixelColor(x, y)
                    total += 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
                    count += 1
        return total / count if count else fallback

    def draw(self, p: QPainter, rect: QRectF, magnify: float = 1.0, clear: bool = False,
             offset: QPointF | None = None) -> None:
        image = self.clear if clear else self.frost
        if image is None:
            return
        sx = image.width() / self._size[0]
        sy = image.height() / self._size[1]
        center = rect.center()
        if offset is not None:
            center = center + offset
        w = rect.width() / max(0.2, magnify)
        h = rect.height() / max(0.2, magnify)
        source = QRectF((center.x() - w / 2) * sx, (center.y() - h / 2) * sy, w * sx, h * sy)
        p.drawImage(rect, image, source)


def _grab(rect: QRect) -> QImage | None:
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    origin = screen.geometry().topLeft()
    image = screen.grabWindow(
        0, rect.x() - origin.x(), rect.y() - origin.y(), rect.width(), rect.height()
    ).toImage()
    if image.isNull() or image.width() < 4:
        image = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()
    return image


def _blur(image: QImage, radius: float) -> QImage:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    if Image is None or radius <= 0.0:
        return image
    raw = bytes(image.constBits())
    pil = Image.frombuffer("RGBA", (image.width(), image.height()), raw, "raw", "RGBA",
                           image.bytesPerLine(), 1)
    pil = pil.filter(ImageFilter.GaussianBlur(radius))
    data = pil.tobytes("raw", "RGBA")
    out = QImage(data, pil.width, pil.height, pil.width * 4, QImage.Format.Format_RGBA8888)
    return out.copy()


# -- shapes -----------------------------------------------------------------


def circle(center: QPointF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(center, radius, radius)
    return path


def pill(rect: QRectF, radius: float | None = None) -> QPainterPath:
    path = QPainterPath()
    r = rect.height() / 2.0 if radius is None else radius
    path.addRoundedRect(rect, r, r)
    return path


def _polar(center: QPointF, angle: float, radius: float) -> QPointF:
    return QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius)


def liquid_bridge(c1: QPointF, r1: float, c2: QPointF, r2: float, waist: float = 0.38) -> QPainterPath | None:
    """The gooey neck between two drops, tangent to both circles.

    *waist* is the neck's half-width as a share of the smaller radius: 0 is
    a thread about to snap, 1 is a fat liquid column.  Returns ``None`` when
    the drops overlap so much that no neck is visible.
    """
    dx, dy = c2.x() - c1.x(), c2.y() - c1.y()
    d = math.hypot(dx, dy)
    if d < 1e-3 or d <= abs(r1 - r2) + 1.0:
        return None
    if d < (r1 + r2) * 0.92:  # still mostly inside the bigger drop: a bulge
        return circle(c2, r2)
    theta = math.atan2(dy, dx)
    spread1 = math.radians(54.0)
    spread2 = math.radians(54.0)
    ux, uy = dx / d, dy / d
    nx, ny = -uy, ux
    a1 = _polar(c1, theta + spread1, r1)
    b1 = _polar(c1, theta - spread1, r1)
    a2 = _polar(c2, theta + math.pi - spread2, r2)
    b2 = _polar(c2, theta + math.pi + spread2, r2)
    mid = QPointF((c1.x() + c2.x()) / 2.0, (c1.y() + c2.y()) / 2.0)
    w = max(0.6, waist * min(r1, r2))
    gap = max(1.0, d - r1 - r2)
    pull = 0.42 * gap + 0.25 * min(r1, r2)
    wa = QPointF(mid.x() + nx * w, mid.y() + ny * w)
    wb = QPointF(mid.x() - nx * w, mid.y() - ny * w)
    path = QPainterPath(a1)
    path.cubicTo(
        QPointF(a1.x() + ux * pull * 0.6, a1.y() + uy * pull * 0.6),
        QPointF(wa.x() - ux * pull, wa.y() - uy * pull),
        wa,
    )
    path.cubicTo(
        QPointF(wa.x() + ux * pull, wa.y() + uy * pull),
        QPointF(a2.x() - ux * pull * 0.6, a2.y() - uy * pull * 0.6),
        a2,
    )
    path.lineTo(c2)
    path.lineTo(b2)
    path.cubicTo(
        QPointF(b2.x() - ux * pull * 0.6, b2.y() - uy * pull * 0.6),
        QPointF(wb.x() + ux * pull, wb.y() + uy * pull),
        wb,
    )
    path.cubicTo(
        QPointF(wb.x() - ux * pull, wb.y() - uy * pull),
        QPointF(b1.x() + ux * pull * 0.6, b1.y() + uy * pull * 0.6),
        b1,
    )
    path.lineTo(c1)
    path.closeSubpath()
    # Round caps: the neck never ends in a point, even while it is short.
    return path.united(circle(c2, r2)).united(circle(c1, r1 * 0.98))


# -- painting ---------------------------------------------------------------

_shadow_cache: dict[tuple, QImage] = {}


def soft_shadow(p: QPainter, rect: QRectF, radius: float, blur: float = 18.0,
                color: QColor | None = None, offset: QPointF = QPointF(0.0, 8.0)) -> None:
    """A real gaussian shadow under a rounded rect (cached per size)."""
    color = color or QColor(0, 0, 0, 90)
    margin = int(math.ceil(blur * 2.2))
    key = (int(rect.width()), int(rect.height()), int(radius), int(blur), color.rgba())
    image = _shadow_cache.get(key)
    if image is None:
        width = int(rect.width()) + margin * 2
        height = int(rect.height()) + margin * 2
        image = QImage(max(4, width), max(4, height), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(margin, margin, rect.width(), rect.height()), radius, radius)
        painter.end()
        image = _blur(image, blur / 2.0)
        if len(_shadow_cache) > 64:
            _shadow_cache.clear()
        _shadow_cache[key] = image
    target = QRectF(rect.x() - margin + offset.x(), rect.y() - margin + offset.y(),
                    image.width(), image.height())
    p.drawImage(target, image)


def drop_shadow(p: QPainter, center: QPointF, radius: float, color: QColor, lift: float = 6.0,
                spread: float = 1.25) -> None:
    """Cheap round shadow for drops: one radial gradient, no blur pass."""
    shadow_center = QPointF(center.x(), center.y() + lift)
    r = radius * spread
    gradient = QRadialGradient(shadow_center, r)
    gradient.setColorAt(0.0, color)
    gradient.setColorAt(0.55, with_alpha(color, 0.55))
    gradient.setColorAt(1.0, with_alpha(color, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gradient)
    p.drawEllipse(shadow_center, r, r)


def glow(p: QPainter, center: QPointF, radius: float, color: QColor, strength: float = 1.0) -> None:
    if strength <= 0.01:
        return
    gradient = QRadialGradient(center, radius)
    gradient.setColorAt(0.0, with_alpha(color, 0.55 * strength))
    gradient.setColorAt(0.45, with_alpha(color, 0.22 * strength))
    gradient.setColorAt(1.0, with_alpha(color, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gradient)
    p.drawEllipse(center, radius, radius)


def paint_glass(
    p: QPainter,
    path: QPainterPath,
    dark: bool,
    backdrop: Backdrop | None = None,
    *,
    tint: QColor | None = None,
    tint_strength: float = 0.0,
    magnify: float = 1.06,
    clear: bool = False,
    opacity: float = 1.0,
    rim: float = 1.0,
    specular: float = 1.0,
    lift: float = 0.0,
) -> None:
    """Fill *path* with liquid glass.

    *tint* (with *tint_strength* 0..1) colours the body, e.g. the accent of a
    selected drop.  *magnify* > 1 refracts the backdrop like a lens.
    """
    if opacity <= 0.005:
        return
    t = tokens(dark)
    bounds = path.boundingRect()
    if bounds.width() < 1 or bounds.height() < 1:
        return
    p.save()
    p.setOpacity(p.opacity() * opacity)
    p.setPen(Qt.PenStyle.NoPen)
    p.setClipPath(path, Qt.ClipOperation.IntersectClip)
    if backdrop is not None and backdrop.ready():
        p.save()
        p.setOpacity(p.opacity() * min(1., theme.surface_strength()))
        backdrop.draw(p, bounds, magnify=magnify, clear=clear)
        p.restore()
    p.fillPath(path, theme.material_color(t.base))
    if tint is not None and tint_strength > 0.005:
        body = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
        top = mix(tint, QColor("#FFFFFF"), 0.28)
        top.setAlphaF(0.92 * tint_strength)
        bottom = QColor(tint)
        bottom.setAlphaF(0.96 * tint_strength)
        body.setColorAt(0.0, top)
        body.setColorAt(1.0, bottom)
        p.save()
        p.setOpacity(p.opacity() * min(1., theme.surface_strength()))
        p.fillPath(path, body)
        p.restore()
    sheen = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
    sheen.setColorAt(0.0, theme.surface_color(with_alpha(t.sheen_top, 1.0 + 1.4 * lift)))
    sheen.setColorAt(0.55, theme.surface_color(with_alpha(t.sheen_bottom, 1.0 + 3.0 * lift)))
    sheen.setColorAt(1.0, theme.surface_color(with_alpha(t.sheen_bottom, 0.4 + 2.0 * lift)))
    p.fillPath(path, sheen)
    # Inner light: a soft bright band hugging the edge (clipped inside).
    edge = min(6.0, max(2.0, min(bounds.width(), bounds.height()) * 0.08))
    inner = QPen(theme.surface_color(with_alpha(QColor(255, 255, 255), (0.24 if dark else 0.42) + 0.2 * lift)), edge * 2.0)
    inner.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.strokePath(path, inner)
    shade = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
    shade.setColorAt(0.0, with_alpha(t.shade, 0.0))
    shade.setColorAt(0.62, with_alpha(t.shade, 0.0))
    shade.setColorAt(1.0, theme.surface_color(t.shade))
    p.fillPath(path, shade)
    p.restore()
    if rim > 0.0:
        _rim(p, path, bounds, dark, opacity * rim)
    if specular > 0.0:
        _specular(p, path, bounds, dark, opacity * specular)


def _rim(p: QPainter, path: QPainterPath, bounds: QRectF, dark: bool, opacity: float) -> None:
    t = tokens(dark)
    gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
    gradient.setColorAt(0.0, t.rim)
    gradient.setColorAt(0.38, t.rim_soft)
    gradient.setColorAt(0.62, t.rim_soft)
    gradient.setColorAt(1.0, with_alpha(t.rim, 0.75))
    p.save()
    p.setOpacity(p.opacity() * opacity)
    pen = QPen(QBrush(gradient), 1.15)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.restore()


def _specular(p: QPainter, path: QPainterPath, bounds: QRectF, dark: bool, opacity: float) -> None:
    """A crisp highlight along the upper-left curve plus a soft bloom."""
    p.save()
    p.setOpacity(p.opacity() * opacity * min(1., theme.surface_strength()))
    p.setClipPath(path, Qt.ClipOperation.IntersectClip)
    w, h = bounds.width(), bounds.height()
    bloom_c = QPointF(bounds.left() + w * 0.30, bounds.top() + h * 0.18)
    bloom = QRadialGradient(bloom_c, max(w, h) * 0.42)
    bloom.setColorAt(0.0, QColor(255, 255, 255, 120 if dark else 170))
    bloom.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bloom)
    p.drawEllipse(bloom_c, max(w, h) * 0.42, max(w, h) * 0.30)
    inset = max(1.6, min(w, h) * 0.07)
    arc_rect = bounds.adjusted(inset, inset, -inset, -inset)
    pen = QPen(QColor(255, 255, 255, 235), min(2.2, max(1.2, min(w, h) * 0.035)))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if abs(w - h) < 2.0:  # round drop: an arc
        p.drawArc(arc_rect, int(118 * 16), int(46 * 16))
    else:  # capsule or card: a short stroke along the top edge
        radius = min(h / 2.0, 22.0)
        y = arc_rect.top() + 0.5
        start = arc_rect.left() + radius * 0.85
        end = arc_rect.left() + min(w * 0.42, radius * 0.85 + min(w * 0.30, 70.0))
        stroke = QPainterPath(QPointF(start - radius * 0.35, y + radius * 0.32))
        stroke.quadTo(QPointF(start - radius * 0.05, y), QPointF(start + radius * 0.4, y))
        stroke.lineTo(QPointF(end, y))
        p.drawPath(stroke)
    p.restore()


def text(p: QPainter, rect: QRectF, flags: int, value: str, ink: QColor) -> None:
    """Draw *value* with a high-contrast opposite-tone halo (legible on any glass)."""
    halo = QColor(0, 0, 0, 155) if ink.lightness() > 128 else QColor(255, 255, 255, 185)
    halo_soft = QColor(halo)
    halo_soft.setAlpha(int(halo.alpha() * 0.55))
    p.save()
    p.setPen(halo_soft)
    p.drawText(rect.translated(-0.6, 0.6), flags, value)
    p.drawText(rect.translated(0.6, 0.6), flags, value)
    p.setPen(halo)
    p.drawText(rect.translated(0.0, 1.2), flags, value)
    p.setPen(ink)
    p.drawText(rect, flags, value)
    p.restore()


def iridescent_rim(p: QPainter, path: QPainterPath, strength: float = 1.0, width: float = 1.6,
                   turn: float = 0.0) -> None:
    """The prismatic violet/aqua/rose edge from the brand references."""
    if strength <= 0.01:
        return
    bounds = path.boundingRect()
    gradient = QConicalGradient(bounds.center(), 35.0 + turn)
    stops = (VIOLET_LIGHT, AQUA_LIGHT, ROSE_LIGHT, VIOLET_LIGHT)
    for index, name in enumerate(stops):
        color = QColor(name)
        color.setAlphaF(0.85 * strength)
        gradient.setColorAt(index / (len(stops) - 1), color)
    p.save()
    pen = QPen(QBrush(gradient), width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.restore()


def paint_lens(p: QPainter, center: QPointF, radius: float, dark: bool, opacity: float = 1.0) -> None:
    """Optics of a clear glass lens drawn *over* already magnified content."""
    if opacity <= 0.01:
        return
    path = circle(center, radius)
    p.save()
    p.setOpacity(p.opacity() * opacity * min(1., theme.surface_strength()))
    p.setClipPath(path, Qt.ClipOperation.IntersectClip)
    # Edge refraction: the rim of a thick lens darkens and catches colour.
    edge = QRadialGradient(center, radius)
    edge.setColorAt(0.0, QColor(255, 255, 255, 0))
    edge.setColorAt(0.78, QColor(255, 255, 255, 0))
    edge.setColorAt(0.93, QColor(255, 255, 255, 70 if dark else 110))
    edge.setColorAt(1.0, QColor(255, 255, 255, 150 if dark else 200))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(edge)
    p.drawEllipse(center, radius, radius)
    under = QLinearGradient(QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius))
    under.setColorAt(0.0, QColor(255, 255, 255, 40))
    under.setColorAt(0.5, QColor(255, 255, 255, 0))
    under.setColorAt(1.0, QColor(0, 0, 0, 34))
    p.setBrush(under)
    p.drawEllipse(center, radius, radius)
    p.restore()
    _rim(p, path, path.boundingRect(), dark, opacity)
    _specular(p, path, path.boundingRect(), dark, opacity)
