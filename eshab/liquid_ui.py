"""Clear glass controls with interruptible, paint-only hover motion.

These remain native Qt buttons: keyboard access, focus, signals and dialogs
keep their normal behavior. No screenshots or blur passes run on hover.
"""
from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import QEasingCurve, QPointF, Property, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QPushButton, QToolButton, QTabBar, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy

from . import glass, i18n, theme
from .brand import BrandMark


def motion_enabled():
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False
    try:
        enabled = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value)
    except Exception:
        return True


class WindowControl(QPushButton):
    """Native, high-contrast window controls, independent of the web surface."""
    def __init__(self, kind, parent):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(38, 32)
        labels = {"close": ("إغلاق", "Close"), "maximize": ("تكبير / استعادة", "Maximize / restore"),
                  "minimize": ("تصغير", "Minimize")}
        label = labels[kind][0 if i18n.is_rtl() else 1]
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = theme.is_dark()
        background = QColor(255, 255, 255, 24 if dark else 170)
        ink = QColor("#f2f6ff" if dark else "#24324b")
        if self.kind == "close":
            background = QColor(207, 79, 89, 145 if self.underMouse() else 48)
            ink = QColor("#ffffff" if dark or self.underMouse() else "#9c2633")
        elif self.underMouse():
            background = QColor(125, 160, 220, 80)
        background = theme.surface_color(background)
        painter.setPen(QPen(QColor(255, 255, 255, 65 if dark else 190), 1))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)
        painter.setPen(QPen(ink, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self.kind == "close":
            painter.drawLine(QPointF(14, 11), QPointF(24, 21))
            painter.drawLine(QPointF(24, 11), QPointF(14, 21))
        elif self.kind == "minimize":
            painter.drawLine(QPointF(13, 17), QPointF(25, 17))
        else:
            painter.drawRoundedRect(QRectF(14, 11, 10, 10), 1, 1)
        painter.end()



class _ElidedTitle(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setToolTip(text)
        self.setFixedHeight(20)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor(theme.design_tokens()["ink"]))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeading, text)


class WindowHeader(QWidget):
    """Shared title and native window controls for all tool pages."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setFixedHeight(64)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(12)
        mark = BrandMark(self, size=36)
        row.addWidget(mark)
        labels = QVBoxLayout()
        labels.setSpacing(3)
        title = _ElidedTitle(owner.windowTitle())
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        owner.windowTitleChanged.connect(title.setText)
        owner.windowTitleChanged.connect(title.setToolTip)
        labels.addWidget(title)
        subtitle = QLabel("اسحب · على جهازك" if i18n.is_rtl() else "Eshab · On your device")
        subtitle.setProperty("dim", True)
        subtitle.setStyleSheet("font-size: 10px;")
        subtitle.setFixedHeight(14)
        labels.addWidget(subtitle)
        row.addLayout(labels, 1)
        controls = QWidget()
        controls.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        buttons = QHBoxLayout(controls)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(5)
        for kind in ("minimize", "maximize", "close"):
            button = WindowControl(kind, controls)
            buttons.addWidget(button)
            if kind == "close":
                button.clicked.connect(owner.close)
            elif kind == "minimize":
                button.clicked.connect(owner.showMinimized)
            else:
                button.clicked.connect(lambda: owner.showNormal() if owner.isMaximized() else owner.showMaximized())
        row.addWidget(controls)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()


def prepare_window(widget):
    widget.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    widget.setProperty("glassWindow", True)
    widget._acrylic = False


def install_window_header(widget):
    if not getattr(widget, '_window_header', None) and isinstance(widget.layout(), QVBoxLayout):
        widget._window_header = WindowHeader(widget)
        widget.layout().insertWidget(0, widget._window_header)


def show_window(widget):
    install_window_header(widget)
    widget._acrylic = theme.glass_window(widget)


def paint_window(widget):
    dark = theme.is_dark()
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(widget.rect())
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 24, 24)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(widget.rect(), Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.fillPath(path, theme.window_tint(dark))
    sheen = QLinearGradient(rect.topLeft(), rect.bottomRight())
    sheen.setColorAt(0, theme.surface_color(QColor(255, 255, 255, 22 if dark else 35)))
    sheen.setColorAt(.52, QColor(255, 255, 255, 0))
    sheen.setColorAt(1, theme.surface_color(QColor(210, 222, 246, 8 if dark else 16)))
    painter.fillPath(path, sheen)
    painter.setPen(QPen(QColor(255, 255, 255, 35 if dark else 180), 1))
    painter.drawPath(path)
    painter.end()


class _LiquidMotion:
    def _init_liquid(self):
        self._hover_amount = 0.0
        self._hover_animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_animation.setDuration(170)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)

    def _get_hover(self):
        return self._hover_amount

    def _set_hover(self, value):
        self._hover_amount = float(value)
        self.update()

    def _animate_hover(self, value):
        self._hover_animation.stop()
        if motion_enabled():
            self._hover_animation.setStartValue(self._hover_amount)
            self._hover_animation.setEndValue(value)
            self._hover_animation.start()
        else:
            self._set_hover(value)

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        dark = theme.is_dark()
        hover = self._hover_amount
        checked = self.isCheckable() and self.isChecked()
        primary = bool(self.property("accent"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 2, -3, -4)
        if self.isDown():
            rect.adjust(1, 1, -1, 0)
        radius = min(16.0, rect.height() / 2)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        shadow = QPainterPath()
        shadow.addRoundedRect(rect.translated(0, 2), radius, radius)
        painter.fillPath(shadow, QColor(0, 0, 0, 40 if dark else 18))
        # Clear glass body, with a bright edge and inner reflection.
        body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body.setColorAt(0, theme.surface_color(QColor(255, 255, 255, round((36 if dark else 74) + 20 * hover))))
        body.setColorAt(.48, theme.surface_color(QColor(255, 255, 255, 9 if dark else 18)))
        body.setColorAt(1, theme.surface_color(QColor(255, 255, 255, 19 if dark else 41)))
        painter.fillPath(path, body)
        if checked or primary:
            painter.fillPath(path, theme.surface_color(QColor(220, 232, 255, 44 if dark else 75)))
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 200 if dark else 255))
        rim.setColorAt(.45, QColor(255, 255, 255, 35 if dark else 90))
        rim.setColorAt(1, QColor(255, 255, 255, 150 if dark else 245))
        painter.setPen(QPen(rim, 1.2))
        painter.drawPath(path)
        inset = rect.adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(255, 255, 255, 25 if dark else 115), 1))
        painter.drawRoundedRect(inset, max(1, radius - 2), max(1, radius - 2))
        if hover > .01:
            glow = QRadialGradient(QPointF(rect.left() + rect.width() * (.25 + .4 * hover), rect.top()), max(rect.width(), rect.height()))
            glow.setColorAt(0, QColor(255, 255, 255, round(20 * hover)))
            glow.setColorAt(.8, QColor(255, 255, 255, 0))
            painter.fillPath(path, glow)
        color = QColor(theme.design_tokens(dark)["blue" if primary else "ink"])
        if not self.isEnabled():
            color.setAlpha(95)
        painter.setPen(color)
        font = self.font()
        if primary or checked:
            font.setBold(True)
        painter.setFont(font)
        text = self.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
        content = rect.adjusted(12, 0, -12, 0)
        if not self.icon().isNull():
            icon_size = min(20, int(rect.height() - 12))
            text_width = painter.fontMetrics().horizontalAdvance(text)
            start = rect.center().x() - (icon_size + 8 + text_width) / 2
            self.icon().paint(painter, int(start), int(rect.center().y() - icon_size / 2), icon_size, icon_size)
            content.setLeft(start + icon_size + 8)
        if text:
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(content.width()))))
        elif isinstance(self, QToolButton) and self.arrowType() != Qt.ArrowType.NoArrow:
            cx, cy = rect.center().x(), rect.center().y()
            arrow = QPainterPath()
            arrow_type = self.arrowType()
            if arrow_type == Qt.ArrowType.LeftArrow:
                arrow.moveTo(cx + 3.0, cy - 4.5)
                arrow.lineTo(cx - 2.5, cy)
                arrow.lineTo(cx + 3.0, cy + 4.5)
            elif arrow_type == Qt.ArrowType.RightArrow:
                arrow.moveTo(cx - 3.0, cy - 4.5)
                arrow.lineTo(cx + 2.5, cy)
                arrow.lineTo(cx - 3.0, cy + 4.5)
            elif arrow_type == Qt.ArrowType.UpArrow:
                arrow.moveTo(cx - 4.5, cy + 2.5)
                arrow.lineTo(cx, cy - 3.0)
                arrow.lineTo(cx + 4.5, cy + 2.5)
            else:
                arrow.moveTo(cx - 4.5, cy - 2.5)
                arrow.lineTo(cx, cy + 3.0)
                arrow.lineTo(cx - 4.5, cy + 2.5)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(arrow)
        if self.hasFocus():
            painter.setPen(QPen(QColor(110, 150, 210, 180), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)
        if checked:
            painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            y = rect.bottom() - 4
            painter.drawLine(QPointF(rect.center().x() - 7, y), QPointF(rect.center().x() + 7, y))
        painter.end()


class LiquidButton(_LiquidMotion, QPushButton):
    hoverAmount = Property(float, _LiquidMotion._get_hover, _LiquidMotion._set_hover)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_liquid()

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(size.width() + 24, max(42, size.height()))


class LiquidToolButton(_LiquidMotion, QToolButton):
    hoverAmount = Property(float, _LiquidMotion._get_hover, _LiquidMotion._set_hover)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_liquid()

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(size.width() + 18, max(40, size.height()))


class LiquidTabBar(QTabBar):
    """A native tab bar with a sliding glass selection capsule."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indicator = QRectF()
        self._slide = QPropertyAnimation(self, b"indicatorRect", self)
        self._slide.setDuration(240)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.currentChanged.connect(self._select)
        self.setDrawBase(False)
        self.setExpanding(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _get_indicator(self):
        return self._indicator

    def _set_indicator(self, rect):
        self._indicator = rect
        self.update()

    indicatorRect = Property(QRectF, _get_indicator, _set_indicator)

    def _select(self, index):
        if index < 0:
            return
        target = QRectF(self.tabRect(index)).adjusted(3, 3, -3, -5)
        self._slide.stop()
        if motion_enabled() and not self._indicator.isEmpty():
            self._slide.setStartValue(self._indicator)
            self._slide.setEndValue(target)
            self._slide.start()
        else:
            self._set_indicator(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._slide.stop()
        if self.currentIndex() >= 0:
            self._set_indicator(QRectF(self.tabRect(self.currentIndex())).adjusted(3, 3, -3, -5))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = theme.is_dark()
        rect = self._indicator
        if not rect.isEmpty():
            body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            body.setColorAt(0, theme.surface_color(QColor(255, 255, 255, 85 if dark else 230)))
            body.setColorAt(.6, theme.surface_color(QColor(255, 255, 255, 22 if dark else 70)))
            body.setColorAt(1, theme.surface_color(QColor(255, 255, 255, 48 if dark else 150)))
            painter.setBrush(body)
            painter.setPen(QPen(QColor(255, 255, 255, 110 if dark else 245), 1.2))
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        for index in range(self.count()):
            text_rect = QRectF(self.tabRect(index)).adjusted(10, 0, -10, -2)
            painter.setPen(QColor(theme.design_tokens(dark)["ink"]))
            font = self.font()
            font.setBold(index == self.currentIndex())
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.tabText(index))
        painter.end()


def stylesheet(dark):
    card = f"rgba(255,255,255,{theme.surface_alpha(18 if dark else 58)})"
    border = "rgba(255,255,255,56)" if dark else "rgba(255,255,255,143)"
    selected = f"rgba(168,196,240,{theme.surface_alpha(41)})" if dark else f"rgba(255,255,255,{theme.surface_alpha(112)})"
    return f"""
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QFrame[glassCard="true"], QTabWidget::pane, QGroupBox {{ background: {card}; border: 1px solid {border}; border-radius: 18px; }}
        QTabBar::tab:selected {{ background: {selected}; color: {'#FFFFFF' if dark else '#252936'}; border: 1px solid {border}; }}
        QTabBar::tab {{ padding: 10px 18px; border-radius: 16px; }}
        QListWidget, QPlainTextEdit, QTextEdit {{ background: {card}; border: 1px solid {border}; border-radius: 14px; }}
        QListWidget::item:selected {{ background: {selected}; color: {'#FFFFFF' if dark else '#252936'}; }}
        QLineEdit, QComboBox {{ background: {card}; border: 1px solid {border}; min-height: 26px; }}
    """
