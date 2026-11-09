"""Shared glass headers, scrollable tool bodies and fixed save controls.

Every tool uses the same native material and layout. Heavy work is handed
to background jobs; hover effects never capture or blur the desktop.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import i18n, jobs, progress, theme, tool_defaults
from ..liquid_ui import LiquidButton as QPushButton, paint_window, prepare_window, show_window, install_window_header


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def pil_to_qimage(img) -> QImage:
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(
        data, rgba.width, rgba.height, rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


def pil_to_pixmap(img, max_w: int, max_h: int) -> QPixmap:
    preview = img.copy()
    preview.thumbnail((max_w, max_h))
    return QPixmap.fromImage(pil_to_qimage(preview))


def run_batch(paths, run_one, title=None):
    paths = [Path(p) for p in paths]

    def work(ctx):
        reserved: set[Path] = set()
        outputs = []
        total = len(paths)
        for index, path in enumerate(paths):
            sub = jobs.batch_ctx(ctx, total, index) if total > 1 else ctx
            result = run_one(path, sub, reserved)
            if isinstance(result, list):
                outputs.extend(result)
            elif result is not None:
                outputs.append(result)
        return outputs

    if title is None:
        title = (
            i18n.tr("action.working_on", name=paths[0].name) if len(paths) == 1
            else i18n.tr("action.working_on_many", n=len(paths))
        )
    return progress.run_job(title, work)


# ---------------------------------------------------------------------------
# Theme / HUD helpers (defensive)
# ---------------------------------------------------------------------------

_CHIP_QSS_CACHE: dict[bool, bool] = {}


def hud_tokens(dark: bool | None = None) -> dict:
    """Return the HUD token dict from the theme, or an empty dict."""
    if dark is None:
        dark = theme.is_dark()
    provider = getattr(theme, "hud", None)
    if not callable(provider):
        return {}
    try:
        tokens = provider(dark)
    except Exception:
        return {}
    return dict(tokens) if tokens else {}


def _rgba_tuple(value) -> tuple[int, int, int, int] | None:
    try:
        parts = tuple(int(part) for part in tuple(value))
    except Exception:
        return None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], 255
    if len(parts) == 4:
        return parts
    return None


def _as_qcolor(value, fallback: tuple[int, int, int, int]) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if isinstance(value, str):
        color = QColor(value)
        if color.isValid():
            return color
        return QColor(*fallback)
    if value is not None:
        parts = _rgba_tuple(value)
        if parts is not None:
            return QColor(*parts)
    return QColor(*fallback)


def _token_to_qss(value) -> str | None:
    """CSS colour text for a theme token (str, tuple or QColor)."""
    if isinstance(value, QColor):
        if value.alpha() >= 255:
            return value.name()
        return "rgba(%d, %d, %d, %d)" % (
            value.red(), value.green(), value.blue(), value.alpha())
    if isinstance(value, str):
        return value
    if value is not None:
        parts = _rgba_tuple(value)
        if parts is not None:
            return "rgba(%d, %d, %d, %d)" % parts
    return None


def card_color(dark: bool) -> QColor:
    return QColor(theme.palette(dark)["window"])


def wash_color(dark: bool) -> QColor:
    tokens = hud_tokens(dark)
    fallback = (30, 25, 22, 195) if dark else (255, 244, 236, 200)
    return _as_qcolor(tokens.get("wash"), fallback)


def _border_color(dark: bool) -> QColor:
    return QColor(theme.palette(dark)["border"])


def _shadow_color(dark: bool) -> QColor:
    raw = theme.palette(dark).get("shadow", (0, 0, 0, 70))
    if isinstance(raw, str):
        color = QColor(raw)
        return color if color.isValid() else QColor(0, 0, 0, 70)
    try:
        r, g, b, a = tuple(raw)
        return QColor(int(r), int(g), int(b), int(a))
    except Exception:
        return QColor(0, 0, 0, 70)


def _theme_styles_chips() -> bool:
    """True when the global stylesheet already styles ``QPushButton[chip]``."""
    dark = theme.is_dark()
    cached = _CHIP_QSS_CACHE.get(dark)
    if cached is None:
        try:
            cached = 'chip' in theme.stylesheet(dark)
        except Exception:
            cached = False
        _CHIP_QSS_CACHE[dark] = cached
    return cached


def chip_button(text: str, parent: QWidget | None = None) -> QPushButton:
    """Peach 'chip' button used for secondary actions (Reset, Play, …)."""
    button = QPushButton(text, parent)
    button.setProperty("chip", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if not _theme_styles_chips():
        dark = theme.is_dark()
        tokens = hud_tokens(dark)
        background = _token_to_qss(tokens.get("peach")) or (
            "#4A392D" if dark else "#F8DCC4")
        foreground = _token_to_qss(tokens.get("icon")) or (
            theme.palette(dark)["text"] if dark else "#3A2416")
        hover = background
        probe = QColor(background)
        if probe.isValid():
            hover = probe.lighter(106).name() if dark else probe.darker(104).name()
        button.setStyleSheet(
            "QPushButton { background: %s; border: none; border-radius: 9px;"
            " padding: 5px 12px; color: %s; font-weight: 600; }"
            "QPushButton:hover { background: %s; }"
            "QPushButton:disabled { color: %s; }"
            % (background, foreground, hover, theme.palette(dark)["text_dim"])
        )
    return button


def section_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Small bold label used for section / field headings."""
    label = QLabel(text, parent)
    font = label.font()
    font.setPixelSize(12)
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    return label


def section_card(title: str | None = None, parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Create a visually divided glass card section with an optional header title."""
    card = QFrame(parent)
    card.setProperty("glassCard", True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(14)
    if title:
        hdr = QLabel(title, card)
        font = hdr.font()
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Bold)
        hdr.setFont(font)
        layout.addWidget(hdr)
    return card, layout


def align_form(form) -> None:
    """Right-align the labels of a QFormLayout (label + control rows)."""
    try:
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dialog shell
# ---------------------------------------------------------------------------

class ToolDialog(QDialog):
    """Resizable native editor with scrollable options and a fixed save row."""

    RADIUS = 24.0

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        prepare_window(self)
        self.setLayoutDirection(theme.direction())
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._outer = outer
        install_window_header(self)
        self._scroll = QScrollArea(self)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content = QWidget(self)
        self._content.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(self._content)
        self._body.setContentsMargins(20, 16, 20, 20)
        self._body.setSpacing(16)
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

    def showEvent(self, event) -> None:  # noqa: N802
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for combo in self.findChildren(QComboBox):
            combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for slider in self.findChildren(QSlider):
            slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        # Native window controls and a bounded height keep Save reachable on laptops.
        area = self.screen().availableGeometry()
        self.setMaximumSize(area.width() - 32, area.height() - 64)
        content_hint = self._content.sizeHint()
        footer_hint = self._outer.itemAt(self._outer.count() - 1).sizeHint()
        self.resize(min(self.maximumWidth(), max(self.width(), content_hint.width() + 4)),
                    min(self.maximumHeight(), max(self.height(), content_hint.height() + footer_hint.height() + self._window_header.height() + 8)))
        if self.width() > self.maximumWidth() or self.height() > self.maximumHeight():
            self.resize(min(self.width(), self.maximumWidth()), min(self.height(), self.maximumHeight()))
        super().showEvent(event)
        show_window(self)

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        paint_window(self)

    # -- buttons -----------------------------------------------------------
    def add_buttons(self, ok_text: str) -> QPushButton:
        key = getattr(self, "_defaults_key", None)
        if key:
            self.reuse_options = QCheckBox(i18n.tr("defaults.reuse"))
            self.reuse_options.setChecked(tool_defaults.is_enabled(key))
            self.reuse_options.setToolTip(i18n.tr("defaults.hint"))
            self._body.addWidget(self.reuse_options)
        footer_widget = QWidget(self)
        footer = QHBoxLayout(footer_widget)
        footer.setContentsMargins(18, 12, 18, 12)
        footer.setSpacing(9)
        footer.addStretch(1)

        cancel = QPushButton(i18n.tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)

        ok = QPushButton(ok_text)
        ok.setProperty("accent", True)
        ok.setAutoDefault(True)
        ok.setDefault(True)
        ok.clicked.connect(self._accept_clicked)
        footer.addWidget(ok)

        self._outer.addWidget(footer_widget)
        self._ok_button = ok
        return ok

    def _accept_clicked(self) -> None:
        self.accept()

    def done(self, result):
        from PySide6.QtMultimedia import QMediaPlayer
        for player in self.findChildren(QMediaPlayer):
            player.stop()
        timer = getattr(self, "_playhead_timer", None)
        if timer:
            timer.stop()
        super().done(result)

    def save_defaults(self) -> None:
        pass

    def configure_defaults(self, key: str) -> dict | None:
        self._defaults_key = key
        return tool_defaults.load_options(key)

    def remember_options(self, options: dict) -> None:
        tool_defaults.remember(self._defaults_key, options, self.reuse_options.isChecked())

    def exec_with_defaults(self):
        key = getattr(self, "_defaults_key", None)
        if key and tool_defaults.can_reuse(key):
            self._accept_clicked()
            return self.result()
        return self.exec()
