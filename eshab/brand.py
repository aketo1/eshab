"""The Eshab mark: stable glass drops, continuous light, and quiet pointer response."""
from __future__ import annotations

import ctypes
import math
import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


def brand_frame(seconds, hover=0.):
    phase = seconds * math.tau / 8.
    hover = max(0., min(1., hover))
    return [
        (50., 55., 24. + .6 * math.sin(phase)),
        (50. + 1.6 * math.sin(phase), 16. - 2. * hover + 1.2 * math.cos(phase), 10.5),
        (16. - 2. * hover + 1.2 * math.sin(phase + 1.1), 79. + 1.5 * math.sin(phase + .8), 9.),
        (84. + 2. * hover + 1.2 * math.sin(phase - 1.1), 79. + 1.5 * math.sin(phase - .8), 9.),
    ]


def _motion_allowed():
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False
    try:
        enabled = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value)
    except (AttributeError, OSError):
        return True


class BrandMark(QWidget):
    def __init__(self, parent=None, size=36):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName("Eshab")
        self._hover = 0.
        self._motion = _motion_allowed()
        self._last_time = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        now = time.monotonic()
        dt = min(.05, max(0., now - self._last_time))
        self._last_time = now
        target = float(self.rect().contains(self.mapFromGlobal(QCursor.pos())))
        self._hover += (target - self._hover) * (1. - math.exp(-10. * dt))
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._last_time = time.monotonic()
        if self._motion:
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        painter.translate((self.width() - side) / 2, (self.height() - side) / 2)
        painter.scale(side / 100., side / 100.)
        seconds = time.time() if self._motion else 0.
        phase = seconds * math.tau / 8.
        circles = brand_frame(seconds, self._hover)
        light_x = 26. + 5. * math.sin(phase)
        fill = QLinearGradient(light_x, 5., 82., 96.)
        fill.setColorAt(0., QColor(255, 255, 255, 190))
        fill.setColorAt(.42, QColor(215, 230, 250, 88))
        fill.setColorAt(1., QColor(130, 155, 190, 40))
        tx, ty, tr = circles[1]
        neck = QPainterPath(QPointF(tx - 4., ty + tr * .7))
        neck.cubicTo(tx - 4., 30., 44., 33., 43., 38.)
        neck.lineTo(57., 38.)
        neck.cubicTo(56., 33., tx + 4., 30., tx + 4., ty + tr * .7)
        neck.closeSubpath()
        painter.fillPath(neck, fill)
        # Thin, continuous liquid bridges stretch with the satellite drops.
        for x, y, radius in circles[2:]:
            sign = -1 if x < 50. else 1
            bridge = QPainterPath(QPointF(50. + sign * 16., 69.))
            bridge.cubicTo(50. + sign * 22., 72., x - sign * 7., y - 6., x - sign * 4., y - 3.)
            bridge.lineTo(x - sign * 7., y + 1.)
            bridge.cubicTo(x - sign * 9., y - 4., 50. + sign * 24., 76., 50. + sign * 18., 73.)
            bridge.closeSubpath()
            painter.fillPath(bridge, fill)
        for index, (x, y, radius) in enumerate(circles):
            circle = QRectF(x - radius, y - radius, radius * 2., radius * 2.)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(20, 35, 55, 85), 3.))
            painter.drawEllipse(circle)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(246, 252, 255, 220), 1.5))
            painter.drawEllipse(circle)
            shine = QPainterPath()
            angle = -2.85 + .65 * math.sin(phase + index * .7)
            shine.moveTo(x + radius * .82 * math.cos(angle), y + radius * .82 * math.sin(angle))
            for index in range(1, 13):
                a = angle + index / 12. * 1.15
                shine.lineTo(x + radius * .82 * math.cos(a), y + radius * .82 * math.sin(a))
            painter.setPen(QPen(QColor(255, 255, 255, 175), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(shine)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 165))
            painter.drawEllipse(QPointF(x + radius * .5 * math.cos(angle + .3), y + radius * .5 * math.sin(angle + .3)), 1.1, 1.1)
        painter.end()
