"""Edit PDF: click any text or image on the page and change it in place.

A glass window with three parts: page thumbnails, the page itself and an
inspector.  On the page you can select, move and resize text and images,
add new text or pictures, and hide content for good.  Saving writes the same
file and keeps the previous version next to it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont, QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import glass, i18n, paths, theme
from .pdf_model import Element, PdfSession
from .liquid_ui import LiquidButton as QPushButton, LiquidToolButton as QToolButton, prepare_window, show_window, paint_window, install_window_header
from .editors.ui.controls import NumericDoubleSpinBox

log = logging.getLogger("eshab")

_OPEN: list["PdfEditor"] = []
HANDLE = 9.0


def _pixmap(session: PdfSession, index: int, scale: float, ratio: float) -> QPixmap:
    pix = session.render(index, scale * ratio)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(ratio)
    return result


class PageCanvas(QWidget):
    """One page with live selection, move, resize and tool interactions."""

    selectionChanged = Signal(object)

    def __init__(self, editor: "PdfEditor"):
        super().__init__()
        self.editor = editor
        self.zoom = 1.0
        self.index = 0
        self.elements: list[Element] = []
        self.selected: Element | None = None
        self.hover: Element | None = None
        self.mode = "select"
        self._pixmap: QPixmap | None = None
        self._drag_kind = ""          # "move", "resize", "redact"
        self._press_page: QPointF | None = None
        self._preview: QRectF | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # geometry
    def page_rect(self) -> QRectF:
        width, height = (595.0, 842.0) if getattr(self.editor.session.doc, "is_closed", False) else self.editor.session.page_size(self.index)
        w, h = width * self.zoom, height * self.zoom
        return QRectF((self.width() - w) / 2.0, 28.0, w, h)

    def sizeHint(self) -> QSize:
        width, height = (595.0, 842.0) if getattr(self.editor.session.doc, "is_closed", False) else self.editor.session.page_size(self.index)
        return QSize(int(width * self.zoom + 80), int(height * self.zoom + 64))

    def to_page(self, point: QPointF) -> QPointF:
        rect = self.page_rect()
        return QPointF((point.x() - rect.left()) / self.zoom, (point.y() - rect.top()) / self.zoom)

    def to_view(self, rect) -> QRectF:
        page = self.page_rect()
        x0, y0, x1, y1 = rect
        return QRectF(page.left() + x0 * self.zoom, page.top() + y0 * self.zoom,
                      (x1 - x0) * self.zoom, (y1 - y0) * self.zoom)

    def refresh(self, keep_selection: bool = False) -> None:
        session = self.editor.session
        self.index = max(0, min(self.index, session.count() - 1))
        ratio = float(self.devicePixelRatioF() or 1.0)
        self._pixmap = _pixmap(session, self.index, self.zoom, ratio)
        self.elements = session.elements(self.index)
        if keep_selection and self.selected is not None:
            self.selected = self._closest(self.selected)
        else:
            self.selected = None
        self.hover = None
        self.setMinimumSize(self.sizeHint())
        self.updateGeometry()
        self.selectionChanged.emit(self.selected)
        self.update()

    def _closest(self, old: Element) -> Element | None:
        best, distance = None, 1e9
        for element in self.elements:
            if element.kind != old.kind:
                continue
            d = sum(abs(a - b) for a, b in zip(element.rect, old.rect))
            if d < distance:
                best, distance = element, d
        return best if distance < 80 else None

    def select_at(self, page_point: QPointF, kind: str | None = None) -> None:
        if not self.editor._commit_pending_text():
            return
        self.elements = self.editor.session.elements(self.index)
        hit = self.editor.session.at(self.index, page_point.x(), page_point.y(), kind)
        self.selected = hit
        self.selectionChanged.emit(hit)
        self.update()

    def _handle_rect(self) -> QRectF | None:
        if self.selected is None:
            return None
        view = self.to_view(self.selected.rect)
        return QRectF(view.right() - HANDLE / 2, view.bottom() - HANDLE / 2, HANDLE, HANDLE)

    # input
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self.editor._commit_pending_text():
            return
        self.setFocus()
        position = event.position()
        page_point = self.to_page(position)
        self._press_page = page_point
        if self.mode == "redact":
            self._drag_kind = "redact"
            self._preview = QRectF(position, position)
            return
        if self.mode == "text":
            self.editor.add_text_at(page_point)
            return
        if self.mode == "image":
            self.editor.add_image_at(page_point)
            return
        handle = self._handle_rect()
        if handle is not None and handle.adjusted(-5, -5, 5, 5).contains(position):
            self._drag_kind = "resize"
            self._preview = self.to_view(self.selected.rect)
            return
        if self.selected is not None and self.to_view(self.selected.rect).contains(position):
            self._drag_kind = "move"
            self._preview = self.to_view(self.selected.rect)
            return
        self.select_at(page_point)
        if self.selected is not None:
            self._drag_kind = "move"
            self._preview = self.to_view(self.selected.rect)

    def mouseMoveEvent(self, event) -> None:
        position = event.position()
        if self._drag_kind and self._press_page is not None:
            now = self.to_page(position)
            dx = (now.x() - self._press_page.x()) * self.zoom
            dy = (now.y() - self._press_page.y()) * self.zoom
            if self._drag_kind == "redact":
                start = self.to_view((self._press_page.x(), self._press_page.y(),
                                      self._press_page.x(), self._press_page.y())).topLeft()
                self._preview = QRectF(start, position).normalized()
            elif self.selected is not None:
                base = self.to_view(self.selected.rect)
                if self._drag_kind == "move":
                    self._preview = base.translated(dx, dy)
                else:
                    self._preview = QRectF(base.topLeft(), QSize(int(max(12, base.width() + dx)),
                                                                  int(max(10, base.height() + dy))))
            self.update()
            return
        page_point = self.to_page(position)
        hover = None
        if self.mode == "select":
            hover = self.editor.session.at(self.index, page_point.x(), page_point.y())
        handle = self._handle_rect()
        if handle is not None and handle.adjusted(-5, -5, 5, 5).contains(position):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self.mode in ("text", "image"):
            self.setCursor(Qt.CursorShape.CrossCursor if self.mode == "image" else Qt.CursorShape.IBeamCursor)
        elif self.mode == "redact":
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor if hover is not None else Qt.CursorShape.ArrowCursor)
        if (hover is None) != (self.hover is None) or (hover and self.hover and hover.rect != self.hover.rect):
            self.hover = hover
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        kind, preview = self._drag_kind, self._preview
        self._drag_kind = ""
        self._preview = None
        self._press_page = None
        if not kind or preview is None:
            self.update()
            return
        page = self.page_rect()
        rect = ((preview.left() - page.left()) / self.zoom, (preview.top() - page.top()) / self.zoom,
                (preview.right() - page.left()) / self.zoom, (preview.bottom() - page.top()) / self.zoom)
        if kind == "redact":
            if preview.width() > 4 and preview.height() > 4:
                self.editor.apply(lambda: self.editor.session.redact(self.index, rect))
            self.update()
            return
        if self.selected is None:
            return
        moved = any(abs(a - b) > 0.6 for a, b in zip(rect, self.selected.rect))
        if moved:
            self.editor.move_selected(rect)
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected is not None:
            self.editor.delete_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.selected = None
            self.selectionChanged.emit(None)
            self.update()
            return
        super().keyPressEvent(event)

    # painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        page = self.page_rect()
        glass.soft_shadow(p, page, 4, 24, QColor(0, 0, 0, 90), QPointF(0, 12))
        if self._pixmap is not None:
            p.drawPixmap(page, self._pixmap, QRectF(self._pixmap.rect()))
        ink = QColor("#1C1C1E")  # pages are white: graphite outlines read everywhere
        if self.hover is not None and (self.selected is None or self.hover.rect != self.selected.rect):
            p.setPen(QPen(glass.with_alpha(ink, 0.55), 1.2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(self.to_view(self.hover.rect).adjusted(-2, -2, 2, 2), 3, 3)
        if self.selected is not None:
            view = self._preview if self._drag_kind in ("move", "resize") and self._preview else                 self.to_view(self.selected.rect)
            p.setPen(QPen(ink, 1.6))
            p.setBrush(QColor(0, 0, 0, 14))
            p.drawRoundedRect(view.adjusted(-2, -2, 2, 2), 3, 3)
            handle = QRectF(view.right() - HANDLE / 2, view.bottom() - HANDLE / 2, HANDLE, HANDLE)
            p.setPen(QPen(ink, 1.5))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(handle)
        if self._drag_kind == "redact" and self._preview is not None:
            p.setPen(QPen(QColor("#1C1C1E"), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QColor(0, 0, 0, 110))
            p.drawRect(self._preview)
        p.end()


class PdfEditor(QWidget):
    def __init__(self, source: Path, parent=None):
        super().__init__(None)
        self.source = Path(source)
        prepare_window(self)
        self.session = PdfSession(self.source)
        self._acrylic = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setProperty("glassWindow", True)
        self.setLayoutDirection(theme.direction())
        self.setWindowIcon(QPixmap(str(paths.icon_png())))
        self.resize(1240, 820)

        self.setMinimumSize(980, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)
        install_window_header(self)
        header = QHBoxLayout()
        name = QLabel(self.source.name)
        name.setStyleSheet("font-size: 17px; font-weight: 600;")
        header.addWidget(name, 1)
        self.save_btn = QPushButton(i18n.tr("pdfedit.save_original"))
        self.save_btn.clicked.connect(self.save)
        header.addWidget(self.save_btn)
        self.save_copy_btn = QPushButton(i18n.tr("pdfedit.save_copy_primary"))
        self.save_copy_btn.setProperty("accent", True)
        self.save_copy_btn.clicked.connect(self.save_as)
        header.addWidget(self.save_copy_btn)
        root.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_pages())
        body.addLayout(self._build_center(), 1)
        body.addWidget(self._build_inspector())
        root.addLayout(body, 1)

        for keys, slot in ((QKeySequence.StandardKey.Save, self.save),
                           (QKeySequence.StandardKey.Undo, self.undo),
                           (QKeySequence.StandardKey.Redo, self.redo),
                           ("Ctrl+Shift+S", self.save_as),
                           ("Ctrl+=", lambda: self.set_zoom(self.canvas.zoom * 1.15)),
                           ("Ctrl+-", lambda: self.set_zoom(self.canvas.zoom / 1.15))):
            QShortcut(QKeySequence(keys), self, activated=slot)

        self.canvas.selectionChanged.connect(self._show_selection)
        QTimer.singleShot(0, self._fit_width)
        self._refresh_all()

    # -- building -------------------------------------------------------------

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("glassCard", True)
        return frame

    def _build_pages(self) -> QWidget:
        card = self._card()
        card.setFixedWidth(164)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)
        title = QLabel(i18n.tr("pdfedit.pages"))
        title.setFont(glass.font(15, QFont.Weight.DemiBold))
        layout.addWidget(title)
        self.pages = QListWidget()
        self.pages.setIconSize(QSize(120, 160))
        self.pages.setSpacing(4)
        self.pages.setStyleSheet("QListWidget { background: transparent; border: none; }")
        self.pages.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.currentRowChanged.connect(self._goto_page)
        layout.addWidget(self.pages, 1)
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        for row, items in ((row1, (("pdfedit.rotate", i18n.tr("pdfedit.rotate_label"), self._rotate),
                                   ("pdfedit.duplicate", i18n.tr("pdfedit.duplicate_label"), self._duplicate))),
                           (row2, (("pdfedit.move_up", "↑", lambda: self._move_page(-1)),
                                   ("pdfedit.move_down", "↓", lambda: self._move_page(1))))):
            for key, glyph, slot in items:
                button = QToolButton()
                button.setText(glyph)
                button.setToolTip(i18n.tr(key))
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(slot)
                row.addWidget(button)
        layout.addLayout(row1)
        layout.addLayout(row2)
        delete = QPushButton(i18n.tr("pdfedit.delete_page_label"))
        delete.clicked.connect(self._delete_page)
        layout.addWidget(delete)
        return card

    def _build_center(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(10)
        bar = self._card()
        bar.setMinimumHeight(108)
        toolbar = QVBoxLayout(bar)
        toolbar.setContentsMargins(8, 5, 8, 5)
        mode_row = QHBoxLayout()
        toolbar.addLayout(mode_row)
        row = QHBoxLayout()
        toolbar.addLayout(row)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for key, mode in (("pdfedit.select", "select"), ("pdfedit.add_text", "text"),
                          ("pdfedit.add_image", "image"), ("pdfedit.redact", "redact")):
            button = QToolButton()
            button.setText(i18n.tr(key))
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("mode", mode)
            self.mode_group.addButton(button)
            mode_row.addWidget(button)
            if mode == "select":
                button.setChecked(True)
        self.mode_group.buttonClicked.connect(lambda b: self._set_mode(b.property("mode")))
        self.undo_btn = QToolButton()
        self.undo_btn.setText("↶ " + i18n.tr("pdfedit.undo"))
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn = QToolButton()
        self.redo_btn.setText("↷ " + i18n.tr("pdfedit.redo"))
        self.redo_btn.clicked.connect(self.redo)
        row.addWidget(self.undo_btn)
        row.addWidget(self.redo_btn)
        row.addStretch(1)
        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip(i18n.tr("pdfedit.zoom_out"))
        zoom_out.clicked.connect(lambda: self.set_zoom(self.canvas.zoom / 1.15))
        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip(i18n.tr("pdfedit.zoom_in"))
        zoom_in.clicked.connect(lambda: self.set_zoom(self.canvas.zoom * 1.15))
        row.addWidget(zoom_out)
        row.addWidget(zoom_in)
        fit = QToolButton()
        fit.setText(i18n.tr("pdfedit.fit"))
        fit.clicked.connect(self._fit_width)
        row.addWidget(fit)
        for button in bar.findChildren(QToolButton) + bar.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        column.addWidget(bar)

        self.canvas = PageCanvas(self)
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        self.scroll = scroll
        column.addWidget(scroll, 1)

        self.status = QLabel(i18n.tr("pdfedit.hint"))
        self.status.setProperty("muted", True)
        column.addWidget(self.status)
        return column

    def _build_inspector(self) -> QWidget:
        card = self._card()
        card.setFixedWidth(264)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self.inspector_title = QLabel(i18n.tr("pdfedit.nothing"))
        self.inspector_title.setFont(glass.font(16, QFont.Weight.DemiBold))
        layout.addWidget(self.inspector_title)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        empty = QLabel(i18n.tr("pdfedit.hint"))
        empty.setWordWrap(True)
        empty.setProperty("muted", True)
        empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.stack.addWidget(empty)

        text_page = QWidget()
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        text_layout.addWidget(QLabel(i18n.tr("pdfedit.text")))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setAccessibleName(i18n.tr("pdfedit.text"))
        self.text_edit.setPlaceholderText(i18n.tr("pdfedit.new_text"))
        self.text_edit.setMinimumHeight(150)
        text_layout.addWidget(self.text_edit)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(i18n.tr("pdfedit.size")))
        self.size_spin = NumericDoubleSpinBox()
        self.size_spin.setAccessibleName(i18n.tr("pdfedit.size"))
        self.size_spin.setRange(4, 200)
        self.size_spin.setDecimals(1)
        size_row.addWidget(self.size_spin, 1)
        self.color_btn = QPushButton(i18n.tr("pdfedit.color"))
        self.color_btn.clicked.connect(self._pick_color)
        text_layout.addLayout(size_row)
        text_layout.addWidget(self.color_btn)
        self.apply_btn = QPushButton(i18n.tr("pdfedit.apply"))
        self.apply_btn.setProperty("accent", True)
        self.apply_btn.clicked.connect(self._apply_text)
        text_layout.addWidget(self.apply_btn)
        hint = QLabel(i18n.tr("pdfedit.apply_hint"))
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        text_layout.addWidget(hint)
        delete_text = QPushButton(i18n.tr("pdfedit.delete"))
        delete_text.clicked.connect(self.delete_selected)
        text_layout.addWidget(delete_text)
        text_layout.addStretch(1)
        self.stack.addWidget(text_page)

        image_page = QWidget()
        image_layout = QVBoxLayout(image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(8)
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(170)
        image_layout.addWidget(self.image_preview)
        replace = QPushButton(i18n.tr("pdfedit.replace_image"))
        replace.setProperty("accent", True)
        replace.clicked.connect(self._replace_image)
        image_layout.addWidget(replace)
        delete_image = QPushButton(i18n.tr("pdfedit.delete"))
        delete_image.clicked.connect(self.delete_selected)
        image_layout.addWidget(delete_image)
        image_layout.addStretch(1)
        self.stack.addWidget(image_page)

        self.page_label = QLabel("")
        self.page_label.setProperty("muted", True)
        layout.addWidget(self.page_label)
        self._color = "#202438"
        return card

    # -- state ----------------------------------------------------------------

    def _title(self) -> None:
        mark = "• " if self.session.dirty else ""
        self.setWindowTitle(f"{mark}{self.source.name} — {i18n.tr('pdfedit.title')}")

    def _refresh_all(self, keep_selection: bool = False) -> None:
        self._refresh_pages()
        self.canvas.refresh(keep_selection)
        self._sync()

    def _refresh_pages(self) -> None:
        current = self.canvas.index
        self.pages.blockSignals(True)
        self.pages.clear()
        for index in range(self.session.count()):
            pix = _pixmap(self.session, index, 0.2, float(self.devicePixelRatioF() or 1.0))
            item = QListWidgetItem(pix, str(index + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pages.addItem(item)
        self.pages.setCurrentRow(min(current, self.session.count() - 1))
        self.pages.blockSignals(False)

    def _sync(self) -> None:
        self.undo_btn.setEnabled(self.session.can_undo())
        self.redo_btn.setEnabled(self.session.can_redo())
        self.page_label.setText(i18n.tr("pdfedit.page_of", page=self.canvas.index + 1, total=self.session.count()))
        self._title()

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def apply(self, change, keep_selection: bool = True, pages: bool = False) -> bool:
        try:
            change()
        except Exception as exc:
            log.info("PDF edit refused: %s", exc)
            QMessageBox.warning(self, i18n.tr("pdfedit.title"), str(exc))
            return False
        if pages:
            self._refresh_pages()
        else:
            item = self.pages.item(self.canvas.index)
            if item is not None:
                item.setIcon(_pixmap(self.session, self.canvas.index, 0.2, float(self.devicePixelRatioF() or 1.0)))
        self.canvas.refresh(keep_selection)
        self._sync()
        return True

    def _goto_page(self, row: int) -> None:
        if row < 0:
            return
        if not self._commit_pending_text():
            self.pages.blockSignals(True)
            self.pages.setCurrentRow(self.canvas.index)
            self.pages.blockSignals(False)
            return
        self.canvas.index = row
        self.canvas.refresh()
        self._sync()
        self.scroll.verticalScrollBar().setValue(0)

    def _set_mode(self, mode: str) -> None:
        if not self._commit_pending_text():
            return
        self.canvas.mode = mode
        self._say(i18n.tr({"text": "pdfedit.hint_text", "image": "pdfedit.hint_image",
                           "redact": "pdfedit.hint_redact"}.get(mode, "pdfedit.hint")))

    def _fit_width(self) -> None:
        width, _ = self.session.page_size(self.canvas.index)
        available = max(300, self.scroll.viewport().width() - 70)
        self.set_zoom(min(1.6, available / width))

    def set_zoom(self, zoom: float) -> None:
        if not self._commit_pending_text():
            return
        self.canvas.zoom = max(0.3, min(4.0, zoom))
        self.canvas.refresh(keep_selection=True)

    # -- selection --------------------------------------------------------------

    def _show_selection(self, element: Element | None) -> None:
        if element is None:
            self.inspector_title.setText(i18n.tr("pdfedit.nothing"))
            self.stack.setCurrentIndex(0)
            return
        if element.kind == "text":
            self.inspector_title.setText(i18n.tr("pdfedit.text"))
            self.text_edit.setPlainText(element.text)
            self.size_spin.setValue(float(element.size))
            self._color = element.color
            self._paint_color_button()
            self.stack.setCurrentIndex(1)
        else:
            self.inspector_title.setText(i18n.tr("pdfedit.add_image"))
            try:
                data = self.session.image_bytes(self.canvas.index, element)
                pix = QPixmap()
                pix.loadFromData(data)
                self.image_preview.setPixmap(pix.scaled(240, 170, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation))
            except Exception:
                self.image_preview.clear()
            self.stack.setCurrentIndex(2)

    def _paint_color_button(self) -> None:
        swatch = QPixmap(18, 18); swatch.fill(Qt.GlobalColor.transparent); painter = QPainter(swatch); painter.setRenderHint(QPainter.RenderHint.Antialiasing, True); painter.setPen(QPen(QColor(255, 255, 255, 190), 1.5)); painter.setBrush(QColor(self._color)); painter.drawRoundedRect(1, 1, 16, 16, 4, 4); painter.end(); self.color_btn.setIcon(QIcon(swatch))

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, i18n.tr("pdfedit.color"))
        if color.isValid():
            self._color = color.name()
            self._paint_color_button()

    def _fit_text(self, element: Element | None, text: str, rect, size: float) -> None:
        """Write text, growing the box when it does not fit."""
        x0, y0, x1, y1 = rect
        page_w, page_h = self.session.page_size(self.canvas.index)
        rtl = any("؀" <= ch <= "ۿ" for ch in text)
        last = None
        for attempt in range(5):
            try:
                self.session.change_text(self.canvas.index, element, text, (x0, y0, x1, y1), size, self._color)
                return
            except ValueError as exc:
                last = exc
                if "صغيرة" in str(exc):
                    raise
                grow_w = (x1 - x0) * 0.5
                if rtl:
                    x0 = max(8.0, x0 - grow_w)
                else:
                    x1 = min(page_w - 8.0, x1 + grow_w)
                y1 = min(page_h - 4.0, y1 + (y1 - y0) * 0.8)
        raise last

    def _has_pending_text(self) -> bool:
        element = self.canvas.selected
        return bool(element is not None and element.kind == "text" and
                    (self.text_edit.toPlainText() != element.text or
                     abs(self.size_spin.value() - element.size) > .05 or self._color != element.color))

    def _commit_pending_text(self) -> bool:
        return self._apply_text() if self._has_pending_text() else True

    def _apply_text(self) -> bool:
        element = self.canvas.selected
        if element is None or element.kind != "text":
            return True
        text = self.text_edit.toPlainText()
        x0, y0, x1, y1 = element.rect
        height = max(y1 - y0, self.size_spin.value() * 1.35)
        return self.apply(lambda: self._fit_text(element, text, (x0, y0, x1, y0 + height), self.size_spin.value()))

    def move_selected(self, rect) -> None:
        element = self.canvas.selected
        if element is None:
            return
        index = self.canvas.index
        if element.kind == "text":
            self._color = element.color
            self.apply(lambda: self._fit_text(element, element.text, rect, element.size))
        else:
            data = self.session.image_bytes(index, element)
            self.apply(lambda: self.session.change_image(index, element, data, rect))

    def delete_selected(self) -> None:
        element = self.canvas.selected
        if element is None:
            return
        index = self.canvas.index
        self.apply(lambda: self.session.delete_element(index, element), keep_selection=False)

    def _replace_image(self) -> None:
        element = self.canvas.selected
        if element is None or element.kind != "image":
            return
        name, _ = QFileDialog.getOpenFileName(self, i18n.tr("pdfedit.replace_image"), "",
                                              i18n.tr("pdfedit.images_filter"))
        if not name:
            return
        data = Path(name).read_bytes()
        index = self.canvas.index
        self.apply(lambda: self.session.change_image(index, element, data, element.rect))

    def add_text_at(self, point: QPointF) -> None:
        page_w, page_h = self.session.page_size(self.canvas.index)
        text = i18n.tr("pdfedit.new_text")
        x0 = max(8.0, min(point.x(), page_w - 160))
        y0 = max(8.0, min(point.y() - 12, page_h - 40))
        rect = (x0, y0, min(page_w - 8, x0 + 220), y0 + 32)
        self._color = "#17142F"
        if self.apply(lambda: self.session.change_text(self.canvas.index, None, text, rect, 16, self._color),
                      keep_selection=False):
            self.canvas.select_at(QPointF(x0 + 4, y0 + 12), "text")
            self._reset_mode()
            self.text_edit.setFocus()
            self.text_edit.selectAll()

    def add_image_at(self, point: QPointF) -> None:
        name, _ = QFileDialog.getOpenFileName(self, i18n.tr("pdfedit.add_image"), "",
                                              i18n.tr("pdfedit.images_filter"))
        if not name:
            return
        data = Path(name).read_bytes()
        image = QImage()
        image.loadFromData(data)
        page_w, page_h = self.session.page_size(self.canvas.index)
        width = min(220.0, page_w * 0.5)
        height = width * (image.height() / image.width()) if not image.isNull() and image.width() else width
        x0 = max(4.0, min(point.x(), page_w - width - 4))
        y0 = max(4.0, min(point.y(), page_h - height - 4))
        rect = (x0, y0, x0 + width, y0 + height)
        if self.apply(lambda: self.session.change_image(self.canvas.index, None, data, rect), keep_selection=False):
            self.canvas.select_at(QPointF(x0 + width / 2, y0 + height / 2), "image")
            self._reset_mode()

    def _reset_mode(self) -> None:
        for button in self.mode_group.buttons():
            if button.property("mode") == "select":
                button.setChecked(True)
        self._set_mode("select")

    # -- pages ------------------------------------------------------------------

    def _rotate(self) -> None:
        if not self._commit_pending_text():
            return
        index = self.canvas.index
        self.apply(lambda: self.session.rotate_page(index), keep_selection=False, pages=True)

    def _duplicate(self) -> None:
        if not self._commit_pending_text():
            return
        index = self.canvas.index
        self.apply(lambda: self.session.duplicate_page(index), keep_selection=False, pages=True)

    def _delete_page(self) -> None:
        index = self.canvas.index
        if self.apply(lambda: self.session.delete_page(index), keep_selection=False, pages=True):
            self._goto_page(min(index, self.session.count() - 1))

    def _move_page(self, offset: int) -> None:
        if not self._commit_pending_text():
            return
        index = self.canvas.index
        target = [index]

        def change() -> None:
            target[0] = self.session.move_page(index, offset)

        if self.apply(change, keep_selection=False, pages=True):
            self.canvas.index = target[0]
            self.pages.setCurrentRow(target[0])

    # -- history and saving -------------------------------------------------------

    def undo(self) -> None:
        self.session.undo()
        self._refresh_all()

    def redo(self) -> None:
        self.session.redo()
        self._refresh_all()

    def save(self) -> bool:
        if not self._commit_pending_text():
            return False
        try:
            backup = self.session.save(self.source, overwrite=True,
                                       backup_label=i18n.tr("pdfedit.backup_label"))
        except Exception as exc:
            QMessageBox.warning(self, i18n.tr("pdfedit.title"), str(exc))
            return False
        self._sync()
        self._say(i18n.tr("pdfedit.saved_backup", name=backup.name) if backup else i18n.tr("pdfedit.saved"))
        return True

    def save_as(self) -> bool:
        if not self._commit_pending_text():
            return False
        suggested = str(self.source.with_name(f"{self.source.stem} - {i18n.tr('pdfedit.edited')}.pdf"))
        name, _ = QFileDialog.getSaveFileName(self, i18n.tr("pdfedit.save_as"), suggested, "PDF (*.pdf)")
        if not name:
            return False
        try:
            target = Path(name)
            if target.resolve() == self.source.resolve():
                return self.save()
            self.session.save(target)
        except Exception as exc:
            QMessageBox.warning(self, i18n.tr("pdfedit.title"), str(exc))
            return False
        self._sync()
        self._say(i18n.tr("pdfedit.saved"))
        return True

    # -- window ---------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        show_window(self)

    def closeEvent(self, event) -> None:
        if self.session.dirty or self._has_pending_text():
            box = QMessageBox(self)
            box.setWindowTitle(i18n.tr("pdfedit.title"))
            box.setText(i18n.tr("pdfedit.unsaved"))
            save = box.addButton(i18n.tr("pdfedit.save_btn"), QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton(i18n.tr("pdfedit.discard"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(i18n.tr("pdfedit.cancel"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is save:
                if not self.save():
                    event.ignore()
                    return
            elif clicked is not discard:
                event.ignore()
                return
        self.session.close()
        if self in _OPEN:
            _OPEN.remove(self)
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        paint_window(self)


def _fit_to_screen(window, width: int, height: int) -> None:
    """Size *window* to at most the work area (laptops are often 1280x800)."""
    screen = window.screen() or QApplication.primaryScreen()
    area = screen.availableGeometry()
    w = min(width, area.width() - 32)
    h = min(height, area.height() - 56)
    window.resize(w, h)
    window.move(area.left() + (area.width() - w) // 2, area.top() + max(8, (area.height() - h) // 2 - 12))


def open_pdf(source, parent=None) -> PdfEditor:
    editor = PdfEditor(Path(source), parent)
    _OPEN.append(editor)
    _fit_to_screen(editor, 1240, 820)
    editor.show()
    editor.raise_()
    editor.activateWindow()
    return editor
