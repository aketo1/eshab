"""A direct, file-first home for the tray application."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QStackedWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import actions, catalog, i18n, paths, theme
from .liquid_ui import LiquidButton as QPushButton, LiquidTabBar, prepare_window, show_window, paint_window


class HomeWindow(QWidget):
    """Choose files, then expose only operations those files can perform."""

    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self._files: list[Path] = []
        self._windows = []
        self._more = False
        prepare_window(self)
        self.setObjectName("WorkspaceRoot")
        self.setWindowTitle(i18n.tr("app.name"))
        self.setWindowIcon(QIcon(str(paths.icon_path())))
        self.setLayoutDirection(theme.direction())
        self.setAcceptDrops(True)
        self.resize(960, 700)
        self.setMinimumSize(720, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel(i18n.tr("home.title"))
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        heading.addWidget(title)
        subtitle = QLabel(i18n.tr("home.subtitle"))
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        settings_btn = QPushButton(i18n.tr("tray.settings"))
        settings_btn.clicked.connect(self._settings)
        header.addWidget(settings_btn)
        root.addLayout(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_page())
        self.stack.addWidget(self._files_page())
        root.addWidget(self.stack, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setProperty("muted", True)
        self.message.hide()
        root.addWidget(self.message)

        footer = QHBoxLayout()
        hint = QLabel(i18n.tr("home.shortcut_hint"))
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        footer.addWidget(hint, 1)
        help_btn = QPushButton(i18n.tr("home.help"))
        help_btn.setProperty("flat", True)
        help_btn.clicked.connect(self._help)
        footer.addWidget(help_btn)
        root.addLayout(footer)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.choose_files)
        self._style()

    def _style(self):
        p = theme.palette(theme.is_dark())
        self.setStyleSheet(f"""
            QWidget#WorkspaceRoot {{ background: transparent; }}
            QFrame#DropCard {{ background: rgba(255,255,255,25); border: 1px solid rgba(255,255,255,165); border-radius: 24px; }}
            QFrame#DropCard[dragActive="true"] {{ border-color: {p['text']}; background: {p['hover']}; }}
            QPushButton {{ min-height: 28px; border-radius: 10px; }}
            QPushButton#ToolChoice {{ text-align: left; padding: 12px 16px; min-height: 32px; }}
            QLabel#SectionTitle {{ font-size: 17px; font-weight: 600; }}
            QListWidget {{ background: rgba(255,255,255,25); }}
            QTabBar::tab {{ padding: 10px 20px; }}
        """)

    def _empty_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.drop_card = QFrame(objectName="DropCard")
        box = QVBoxLayout(self.drop_card)
        box.setContentsMargins(32, 30, 32, 30)
        box.setSpacing(16)
        box.addStretch()
        mark = QLabel()
        mark.setPixmap(QIcon(str(paths.icon_path())).pixmap(64, 64))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("font-size: 44px; font-weight: 300;")
        box.addWidget(mark)
        title = QLabel(i18n.tr("home.drop"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        box.addWidget(title)
        hint = QLabel(i18n.tr("home.drop_hint"))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setProperty("muted", True)
        box.addWidget(hint)
        choose = QPushButton(i18n.tr("home.choose"))
        choose.setProperty("accent", True)
        choose.setMinimumWidth(180)
        choose.clicked.connect(self.choose_files)
        box.addWidget(choose, 0, Qt.AlignmentFlag.AlignHCenter)
        shortcut = QLabel("Ctrl + O")
        shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut.setProperty("muted", True)
        box.addWidget(shortcut)
        box.addStretch()
        layout.addWidget(self.drop_card, 1)
        quick = QHBoxLayout()
        for key, callback in (("tray.edit_pdf", self._pdf), ("tray.images_pdf", self._images_pdf)):
            button = QPushButton(i18n.tr(key))
            button.clicked.connect(callback)
            quick.addWidget(button)
        layout.addLayout(quick)
        return page

    def _files_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.count_label = QLabel(objectName="SectionTitle")
        top.addWidget(self.count_label, 1)
        add = QPushButton(i18n.tr("home.add"))
        add.clicked.connect(self.choose_files)
        clear = QPushButton(i18n.tr("home.clear"))
        clear.clicked.connect(self.clear_files)
        top.addWidget(add)
        top.addWidget(clear)
        layout.addLayout(top)

        splitter = QSplitter()
        self.file_list = QListWidget()
        self.file_list.setAccessibleName(i18n.tr("home.files"))
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self._refresh_options)
        self.file_list.itemDoubleClicked.connect(lambda item: self._edit_selected())
        splitter.addWidget(self.file_list)
        panel = QWidget()
        right = QVBoxLayout(panel)
        right.setContentsMargins(8, 0, 0, 0)
        self.selection_label = QLabel()
        self.selection_label.setWordWrap(True)
        self.selection_label.setProperty("muted", True)
        right.addWidget(self.selection_label)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(LiquidTabBar())
        convert = QWidget()
        conversion_layout = QVBoxLayout(convert)
        conversion_layout.setContentsMargins(18, 22, 18, 18)
        conversion_layout.setSpacing(16)
        label = QLabel(i18n.tr("home.format"))
        conversion_layout.addWidget(label)
        self.formats = QComboBox()
        self.formats.setAccessibleName(i18n.tr("home.format"))
        label.setBuddy(self.formats)
        self.formats.currentIndexChanged.connect(self._format_changed)
        conversion_layout.addWidget(self.formats)
        self.conversion_hint = QLabel()
        self.conversion_hint.setWordWrap(True)
        self.conversion_hint.setProperty("muted", True)
        conversion_layout.addWidget(self.conversion_hint)
        self.convert_btn = QPushButton(i18n.tr("home.convert"))
        self.convert_btn.setProperty("accent", True)
        self.convert_btn.clicked.connect(self._convert)
        conversion_layout.addWidget(self.convert_btn)
        save_hint = QLabel(i18n.tr("home.save_hint"))
        save_hint.setWordWrap(True)
        save_hint.setProperty("muted", True)
        conversion_layout.addWidget(save_hint)
        conversion_layout.addStretch()
        self.tabs.addTab(convert, i18n.tr("home.convert_tab"))

        self.tools_scroll = QScrollArea()
        self.tools_scroll.setWidgetResizable(True)
        self.tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabs.addTab(self.tools_scroll, i18n.tr("home.tools_tab"))
        right.addWidget(self.tabs, 1)
        splitter.addWidget(panel)
        splitter.setSizes([350, 480])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        return page

    def choose_files(self):
        from PySide6.QtWidgets import QFileDialog
        names, _ = QFileDialog.getOpenFileNames(self, i18n.tr("home.choose"))
        if names:
            self.add_files(names)

    def add_files(self, names):
        new = [Path(name).resolve() for name in names if Path(name).is_file()]
        self._files = list(dict.fromkeys(self._files + new))
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for path in self._files:
            item = QListWidgetItem(f"{path.name}\n{path.suffix.upper().lstrip('.')}  ·  {self._size(path)}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
            item.setSelected(True)
        self.file_list.blockSignals(False)
        self.count_label.setText(i18n.tr("home.file_count", n=len(self._files)))
        self.stack.setCurrentIndex(1 if self._files else 0)
        self._refresh_options()

    @staticmethod
    def _size(path):
        try:
            size = path.stat().st_size
            return f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{max(1, size / 1024):.0f} KB"
        except OSError:
            return "—"

    def selected_paths(self):
        return [Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.file_list.selectedItems()]

    def clear_files(self):
        self._files.clear()
        self.file_list.clear()
        self.message.hide()
        self.stack.setCurrentIndex(0)

    def _refresh_options(self):
        selected = self.selected_paths()
        self.selection_label.setText(i18n.tr("home.selected", n=len(selected)))
        previous = self.formats.currentData()
        self.formats.blockSignals(True)
        self.formats.clear()
        self.formats.addItem(i18n.tr("home.choose_format"), None)
        for conversion in catalog.conversions_for(selected):
            self.formats.addItem(conversion.target_ext.upper(), conversion.target_ext)
        index = self.formats.findData(previous) if previous else 0
        self.formats.setCurrentIndex(max(0, index))
        self.formats.blockSignals(False)
        self.formats.setEnabled(self.formats.count() > 1)
        self._format_changed()
        self._render_tools()

    def _format_changed(self):
        selected = self.selected_paths()
        target = self.formats.currentData()
        applicable = catalog.conversion_paths(target, selected) if target else []
        self.convert_btn.setEnabled(bool(applicable))
        if target and len(applicable) != len(selected):
            text = i18n.tr("home.partial", n=len(applicable), total=len(selected))
        elif target == "pdf" and len(applicable) > 1 and all(catalog.family_of(p) == "image" for p in applicable):
            text = i18n.tr("home.pdf_order")
        elif self.formats.count() == 1:
            text = i18n.tr("home.no_conversion") if selected else i18n.tr("home.select_file")
        else:
            text = i18n.tr("home.format_hint")
        self.conversion_hint.setText(text)

    def _render_tools(self):
        old = self.tools_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 12, 14, 12)
        available = catalog.tools_for(self.selected_paths())
        priority = {"img.edit": 0, "pdf.edit": 0, "img.crop": 1, "vid.trim": 0,
                    "aud.trim": 0, "img.annotate": 2, "img.compress": 3,
                    "pdf.compress": 1, "vid.compress": 1, "aud.compress": 1}
        ordered = sorted(available, key=lambda tool: priority.get(tool.id, 10))
        for tool in (ordered if self._more else ordered[:4]):
            button = QPushButton(i18n.tr("tool." + tool.id), objectName="ToolChoice")
            button.setToolTip(i18n.tr("home.tool_hint", n=len(catalog.tool_paths(tool.id, self.selected_paths()))))
            button.clicked.connect(lambda checked=False, key=tool.id: self._run_tool(key))
            layout.addWidget(button)
        if len(ordered) > 4:
            more = QPushButton(i18n.tr("home.less_tools" if self._more else "home.more_tools", n=len(ordered) - 4))
            more.setProperty("flat", True)
            more.clicked.connect(self._toggle_more)
            layout.addWidget(more)
        if not ordered:
            label = QLabel(i18n.tr("home.no_tools"))
            label.setWordWrap(True)
            label.setProperty("muted", True)
            layout.addWidget(label)
        layout.addStretch()
        self.tools_scroll.setWidget(inner)

    def _toggle_more(self):
        self._more = not self._more
        self._render_tools()

    def _track(self, window):
        if window is not None:
            if self.controller is not None:
                self.controller._track(window)
            # Keep modeless editor/progress wrappers alive while open.
            self._windows.append(window)
            signal = getattr(window, "destroyed", None)
            if signal is not None:
                signal.connect(lambda *_: self._windows.remove(window) if window in self._windows else None)

    def _convert(self):
        target = self.formats.currentData()
        sources = catalog.conversion_paths(target, self.selected_paths()) if target else []
        if sources:
            self._perform(lambda: actions.run_conversions(sources, target))

    def _run_tool(self, key):
        sources = catalog.tool_paths(key, self.selected_paths())
        if sources:
            self._perform(lambda: actions.run_tool(sources, key))

    def _perform(self, call):
        try:
            self._track(call())
        except Exception as exc:
            self.message.setText(str(exc))
            self.message.show()

    def _edit_selected(self):
        selected = self.selected_paths()
        if not selected:
            return
        family = catalog.family_of(selected[0])
        key = {"image": "img.edit", "pdf": "pdf.edit", "video": "vid.trim", "audio": "aud.trim"}.get(family)
        if key and key in {tool.id for tool in catalog.tools_for(selected)}:
            self._run_tool(key)
        else:
            self.tabs.setCurrentIndex(0)

    def _settings(self):
        if self.controller is not None:
            self.controller.open_settings()

    def _pdf(self):
        if self.controller is not None:
            self.controller.open_pdf()

    def _images_pdf(self):
        if self.controller is not None:
            self.controller.open_images_pdf()

    def _help(self):
        QMessageBox.information(self, i18n.tr("home.help"), i18n.tr("home.help_text"))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.drop_card.setProperty("dragActive", True)
            self.drop_card.style().unpolish(self.drop_card)
            self.drop_card.style().polish(self.drop_card)

    def dragLeaveEvent(self, event):
        self._reset_drop_style()

    def _reset_drop_style(self):
        self.drop_card.setProperty("dragActive", False)
        self.drop_card.style().unpolish(self.drop_card)
        self.drop_card.style().polish(self.drop_card)

    def dropEvent(self, event):
        self._reset_drop_style()
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def present(self):
        area = self.screen().availableGeometry()
        self.resize(min(self.width(), area.width() - 40), min(self.height(), area.height() - 60))
        self.move(area.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        show_window(self)

    def paintEvent(self, event):
        paint_window(self)
