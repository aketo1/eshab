"""The file shelf: one fixed native surface with paint-only reveal motion.

Only an explicit shelf action can create or present this window. Jobs and
notifications never open it. Hover changes neither native window geometry nor
its region until a transition has finished.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QFileInfo, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QDrag, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileIconProvider, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import glass, i18n, theme
from .brand import BrandMark


def tr(ar, en):
    return ar if i18n.is_rtl() else en


class FileRibbon(QListWidget):
    def __init__(self, island):
        super().__init__(island.details)
        self.island = island
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(QSize(28, 28))
        self.setGridSize(QSize(82, 66))
        self.setFixedHeight(74)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemDoubleClicked.connect(self._open)
        self.setToolTip(tr("اسحب الملفات للخارج · Delete يزيلها من الرف فقط", "Drag files out · Delete removes shelf references only"))

    def _open(self, item):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def startDrag(self, actions):
        selected = self.selectedItems()
        urls = [QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)) for item in selected
                if Path(item.data(Qt.ItemDataRole.UserRole)).exists()]
        if not urls:
            return
        mime = QMimeData()
        mime.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(selected[0].icon().pixmap(36, 36))
        self.island._dragging = True
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            self.island._dragging = False
            self.island._check_hover()

    def dragEnterEvent(self, event):
        self.island.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.island.dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.island.dragLeaveEvent(event)

    def dropEvent(self, event):
        self.island.dropEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().x() or event.angleDelta().y()
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            self.island._sync_shelf()
        else:
            super().keyPressEvent(event)


class ActivityIsland(QWidget):
    COMPACT_WIDTH = 104
    COMPACT_HEIGHT = 38
    EXPANDED_HEIGHT = 190
    ENTER_DELAY = .07
    LEAVE_DELAY = .16

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setWindowTitle(tr("اسحب · رف الملفات", "Eshab · File shelf"))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setLayoutDirection(theme.direction())
        self.expanded = False
        self._dragging = False
        self._drop_hover = False
        self._candidate = None
        self._candidate_since = 0.
        self._display = None
        self._region_expanded = None
        self._amount = glass.Spring(0., stiffness=310., damping=36.)
        self._arrival = glass.Spring(0., stiffness=200., damping=28.)
        self.motion = glass.Animator(self, self._animate)
        self.motion.track(self._amount, self._arrival)
        self.mark = BrandMark(self, size=28)
        self.details = QWidget(self)
        self.details.setObjectName("ShelfDetails")
        self._fade = QGraphicsOpacityEffect(self.details)
        self._fade.setOpacity(0.)
        self.details.setGraphicsEffect(self._fade)
        layout = QVBoxLayout(self.details)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.shelf_label = QLabel(tr("رف الملفات", "File shelf"))
        self.shelf_label.setMinimumWidth(0)
        self.shelf_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        heading.addWidget(self.shelf_label, 1)
        clear = QPushButton(tr("إفراغ", "Clear"))
        clear.setToolTip(tr("إزالة الاختصارات فقط", "Remove references only"))
        clear.clicked.connect(self.clear_shelf)
        heading.addWidget(clear)
        close = QPushButton("×")
        close.setFixedWidth(30)
        close.setAccessibleName(tr("إغلاق الرف", "Close shelf"))
        close.setToolTip(tr("إغلاق الرف", "Close shelf"))
        close.clicked.connect(self.close)
        heading.addWidget(close)
        layout.addLayout(heading)
        self.ribbon = FileRibbon(self)
        layout.addWidget(self.ribbon)
        self.hint = QLabel(tr("أفلت ملفاتك هنا، واسحبها وقت ما تحتاجها", "Drop files here. Drag them out when you need them."))
        self.hint.setObjectName("ShelfHint")
        self.hint.setFixedHeight(16)
        self.hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.hint)
        self.details.hide()
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(40)
        self._hover_timer.timeout.connect(self._check_hover)
        self._apply_style()
        theme.add_theme_listener(self._theme_changed)
        callback = self._theme_changed
        self.destroyed.connect(lambda *_: theme.remove_theme_listener(callback))
        self._configure_screen()

    @property
    def files(self):
        return [Path(self.ribbon.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.ribbon.count())]

    def _configure_screen(self):
        self._region_expanded = None
        display = QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self._display = display
        area = display.availableGeometry()
        # The supplied reference is 408px wide on a 1280px desktop.
        width = max(104, min(408, round(area.width() * .31875)))
        height = min(self.EXPANDED_HEIGHT, area.height() - 16)
        self.setFixedSize(width, height)
        self.move(area.center().x() - width // 2, display.geometry().top())
        self.details.setGeometry(14, 43, width - 28, height - 54)
        self._apply_region(False)
        self._place_mark(0.)

    def _theme_changed(self, dark):
        self._apply_style()
        self.update()

    def _apply_style(self):
        palette = theme.native_design_tokens()
        self.setStyleSheet(f"""
            ActivityIsland, #ShelfDetails {{ background: transparent; color: {palette['ink']}; }}
            QLabel {{ color: {palette['ink']}; background: transparent; border: 0; font-size: 12px; }}
            #ShelfHint {{ color: {palette['muted']}; font-size: 10px; }}
            QPushButton {{ color: {palette['ink']}; background: {palette['soft']};
                border: 1px solid {palette['line']}; border-radius: 11px; padding: 4px 9px;
                min-height: 18px; font-size: 11px; }}
            QPushButton:hover {{ background: {palette['selected']}; }}
            QListWidget {{ border: 0; background: transparent; padding: 0; outline: none; }}
            QListWidget::item {{ color: {palette['ink']}; background: {palette['soft']};
                border: 1px solid {palette['line']}; border-radius: 13px; padding: 4px; }}
            QListWidget::item:selected {{ background: {palette['selected']}; }}
            QScrollBar:horizontal {{ height: 5px; background: transparent; }}
            QScrollBar::handle:horizontal {{ background: rgba(130,155,190,110); border-radius: 2px; min-width: 20px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        """)

    def _compact_rect(self):
        return QRectF((self.width() - self.COMPACT_WIDTH) / 2, 0, self.COMPACT_WIDTH, self.COMPACT_HEIGHT)

    def _surface_rect(self, amount=None):
        value = max(0., min(1., self._amount.value if amount is None else amount))
        compact = self._compact_rect()
        return QRectF(compact.x() * (1 - value), 0,
                      compact.width() + (self.width() - compact.width()) * value,
                      compact.height() + (self.height() - compact.height()) * value)

    @staticmethod
    def _path(rect):
        radius = min(24., rect.height() / 2)
        path = QPainterPath(QPointF(rect.left(), rect.top()))
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - radius)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
        path.lineTo(rect.left() + radius, rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
        path.closeSubpath()
        return path

    def _apply_region(self, expanded):
        # Only two native input regions; never rebuild a region on animation frames.
        if self._region_expanded == expanded:
            return
        path = self._path(self._surface_rect(1. if expanded else 0.))
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        self._region_expanded = expanded

    def present(self, expanded=False):
        if not self.isVisible():
            self._configure_screen()
            self.expanded = False
            self._amount.snap(0.)
            self._fade.setOpacity(0.)
            self.details.hide()
            self.show()
        self.raise_()
        self._hover_timer.start()
        # Opening the shelf is explicit; the first hover transition follows intent.
        if expanded and self._compact_rect().contains(QPointF(self.mapFromGlobal(QCursor.pos()))):
            self.set_expanded(True)

    def set_expanded(self, expanded):
        expanded = bool(expanded)
        if expanded == self.expanded and self._amount.target == float(expanded):
            return
        self.expanded = expanded
        self._candidate = None
        if expanded:
            self._apply_region(True)
            self.details.show()
        self._amount.to(float(expanded))
        self.motion.kick()

    def _place_mark(self, value):
        compact_x = (self.width() - self.mark.width()) / 2
        expanded_x = self.width() - self.mark.width() - 15 if i18n.is_rtl() else 15
        self.mark.move(round(compact_x + (expanded_x - compact_x) * value), 5)

    def _animate(self, elapsed):
        value = max(0., min(1., self._amount.value))
        self._place_mark(value)
        # Clip child painting to the glass while it opens. This is a child
        # widget region, not a change to the native desktop window's region.
        clip = QRegion(self._path(self._surface_rect()).toFillPolygon().toPolygon())
        self.details.setMask(clip.translated(-self.details.x(), -self.details.y()))
        fade = max(0., min(1., (value - .35) / .6))
        fade = fade * fade * (3 - 2 * fade)
        self._fade.setOpacity(fade)
        self.details.setEnabled(value > .92 and self.expanded)
        if self._amount.settled:
            if not self.expanded:
                self.details.hide()
                self._apply_region(False)
            else:
                self._fade.setOpacity(1.)
        return False

    def _check_hover(self):
        if not self.isVisible() or self._dragging:
            return
        point = QPointF(self.mapFromGlobal(QCursor.pos()))
        if self.expanded:
            inside = QRectF(self.rect()).adjusted(-6, 0, 6, 8).contains(point)
        else:
            inside = self._compact_rect().adjusted(-2, 0, 2, 2).contains(point)
        if not inside:
            self._drop_hover = False
        desired = inside or self._drop_hover
        if desired == self.expanded:
            self._candidate = None
            return
        now = time.monotonic()
        if self._candidate != desired:
            self._candidate, self._candidate_since = desired, now
            return
        delay = self.ENTER_DELAY if desired else self.LEAVE_DELAY
        if now - self._candidate_since >= delay:
            self.set_expanded(desired)

    def enterEvent(self, event):
        self._check_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._check_hover()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._compact_rect().contains(event.position()):
            self.set_expanded(True)

    def _sync_shelf(self):
        count = self.ribbon.count()
        self.shelf_label.setText(tr("رف الملفات", "File shelf") + (f" · {count}" if count else ""))
        hint = tr("أفلت ملفاتك هنا، واسحبها وقت ما تحتاجها", "Drop files here. Drag them out when you need them.")
        self.hint.setToolTip(hint)
        self.hint.setText(self.hint.fontMetrics().elidedText(hint, Qt.TextElideMode.ElideRight, self.width() - 28))
        self.update()

    def add(self, files):
        known = {str(path.resolve()).casefold() for path in self.files}
        provider = QFileIconProvider()
        added = 0
        for value in files:
            path = Path(value).resolve()
            key = str(path).casefold()
            if not path.exists() or key in known:
                continue
            item = QListWidgetItem(provider.icon(QFileInfo(str(path))), path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.ribbon.addItem(item)
            known.add(key)
            added += 1
        self._sync_shelf()
        self.present()
        if added:
            self._arrival.snap(1.).to(0.)
            self.motion.kick()

    def clear_shelf(self):
        self.ribbon.clear()
        self._sync_shelf()

    @staticmethod
    def _local_files(event):
        return [url.toLocalFile() for url in event.mimeData().urls()
                if url.isLocalFile() and Path(url.toLocalFile()).exists()]

    def dragEnterEvent(self, event):
        if self._local_files(event):
            self._drop_hover = True
            self.set_expanded(True)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._local_files(event):
            self._drop_hover = True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_hover = False
        self._check_hover()
        event.accept()

    def dropEvent(self, event):
        files = self._local_files(event)
        self._drop_hover = False
        if not files:
            event.ignore()
            return
        self.add(files)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def hideEvent(self, event):
        self._hover_timer.stop()
        self.motion.stop()
        self._amount.snap(0.)
        self._arrival.snap(0.)
        self.expanded = False
        self._candidate = None
        self._drop_hover = False
        self.details.hide()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._surface_rect()
        path = self._path(rect.adjusted(.5, 0, -.5, -.5))
        dark = theme.is_dark()
        painter.fillPath(path, theme.material_color(QColor(18, 25, 38, 12) if dark else QColor(246, 250, 255, 12)))
        material = QLinearGradient(rect.topLeft(), rect.bottomRight())
        material.setColorAt(0, theme.surface_color(QColor(230, 242, 255, 48 if dark else 65)))
        material.setColorAt(.5, theme.surface_color(QColor(21, 32, 50, 42) if dark else QColor(246, 251, 255, 38)))
        material.setColorAt(1, theme.surface_color(QColor(175, 202, 240, 35)))
        painter.fillPath(path, material)
        painter.setPen(QPen(QColor(255, 255, 255, 115), 1.))
        painter.drawPath(path)
        arrival = max(0., min(1., self._arrival.value))
        if arrival:
            painter.fillPath(path, QColor(180, 215, 255, round(36 * arrival)))
        if not self.expanded and self._amount.value < .1 and self.ribbon.count():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#c5dcff"))
            painter.drawEllipse(QPointF(rect.center().x() + 24, 19), 2., 2.)
        painter.end()


_island = None


def get_island():
    global _island
    import shiboken6
    if _island is None or not shiboken6.isValid(_island):
        _island = ActivityIsland()
    return _island
