"""Eshab's look outside the HUD: palette, Qt stylesheet and glass windows.

The identity is clear liquid glass without brand colours: surfaces take
their colour from what is behind them.  The HUD surfaces paint themselves with :mod:`eshab.glass`;
regular windows (editors, settings, the home window) get the same palette
through :func:`stylesheet`. Clear per-pixel window surfaces are configured
through :func:`glass_window` without an opaque acrylic backdrop.

``appearanceTheme`` (``system``, ``light`` or ``dark``) picks the palette.
"""

from __future__ import annotations

import ctypes
import logging

log = logging.getLogger("eshab")

# Clear glass, no brand colour. "Accent" is ink: white on dark, graphite on light.
ACCENT = "#1C1C1E"
ACCENT_BRIGHT = "#3A3A3C"
ACCENT_DARK = "#000000"
AQUA = ROSE = ACCENT

FAN_PETAL_RADIUS = 152.0
FAN_CENTER_RADIUS = 44.0
FAN_HOVER_LIFT = 6.0

APPEARANCE_DEFAULT = "system"
APPEARANCE_VALUES = ("system", "light", "dark")

LIGHT = {
    "window": "#f1f5fa",
    "card": "#FFFFFF",
    "card_alt": "#F6F6F8",
    "text": "#252934",
    "text_dim": "#647187",
    "border": "#E3E3E8",
    "field": "#FFFFFF",
    "hover": "#ECECF0",
    "glass": (255, 255, 255, 215),
    "glass_edge": (255, 255, 255, 255),
    "petal": (255, 255, 255, 235),
    "petal_edge": (226, 226, 232, 235),
    "petal_text": "#111114",
    "shadow": (0, 0, 0, 50),
    "slider_track": "rgba(17, 17, 20, 30)",
    "slider_thumb": "#FFFFFF",
    "slider_thumb_edge": "rgba(17, 17, 20, 45)",
}

DARK = {
    "window": "#151e2c",
    "card": "#1C1C1E",
    "card_alt": "#232326",
    "text": "#f1f3f8",
    "text_dim": "#aab9cc",
    "border": "#2E2E32",
    "field": "#1A1A1C",
    "hover": "#2C2C2F",
    "glass": (28, 28, 30, 215),
    "glass_edge": (255, 255, 255, 60),
    "petal": (36, 36, 40, 235),
    "petal_edge": (80, 80, 88, 235),
    "petal_text": "#F5F5F7",
    "shadow": (0, 0, 0, 120),
    "slider_track": "rgba(255, 255, 255, 40)",
    "slider_thumb": "#FFFFFF",
    "slider_thumb_edge": "rgba(255, 255, 255, 80)",
}

HUD_LIGHT = {
    "wash": (250, 250, 252, 205),
    "halo": (0, 0, 0, 30),
    "hub": (255, 255, 255, 240),
    "peach": "#ECECF0",
    "track": (17, 17, 20, 40),
    "icon": "#111114",
}

HUD_DARK = {
    "wash": (22, 22, 24, 210),
    "halo": (0, 0, 0, 60),
    "hub": (30, 30, 32, 245),
    "peach": "#2C2C2F",
    "track": (255, 255, 255, 45),
    "icon": "#F5F5F7",
}

_theme_listeners: list = []


def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


def hud(dark: bool) -> dict:
    return HUD_DARK if dark else HUD_LIGHT


def qcolor(token):
    """Convert a token (``#rrggbb`` or ``(r, g, b[, a])``) to a QColor."""
    from PySide6.QtGui import QColor

    if isinstance(token, QColor):
        return QColor(token)
    if isinstance(token, (tuple, list)):
        return QColor(*token)
    return QColor(str(token))


def appearance_mode() -> str:
    try:
        from . import settings

        value = settings.get("appearanceTheme", APPEARANCE_DEFAULT)
    except Exception:
        value = APPEARANCE_DEFAULT
    mode = str(value or APPEARANCE_DEFAULT).lower()
    return mode if mode in APPEARANCE_VALUES else APPEARANCE_DEFAULT


def is_dark() -> bool:
    mode = appearance_mode()
    if mode == "light":
        return False
    if mode == "dark":
        return True
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            return False
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def direction():
    """Qt layout direction for the current language."""
    from PySide6.QtCore import Qt

    from . import i18n

    return Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight


def add_theme_listener(callback) -> None:
    if callback not in _theme_listeners:
        _theme_listeners.append(callback)


def remove_theme_listener(callback) -> None:
    if callback in _theme_listeners:
        _theme_listeners.remove(callback)


def refresh_listeners(dark: bool | None = None) -> None:
    if dark is None:
        dark = is_dark()
    for callback in list(_theme_listeners):
        try:
            callback(bool(dark))
        except Exception:
            log.exception("Theme listener failed")


def apply_app_theme() -> bool:
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
    except Exception:
        return False
    if app is None:
        return False
    dark = is_dark()
    app.setLayoutDirection(direction())
    app.setStyleSheet(stylesheet(dark))
    refresh_listeners(dark)
    return True


def rgba(c) -> str:
    if isinstance(c, str):
        return c
    r, g, b, a = c
    return f"rgba({r}, {g}, {b}, {a})"


FONT_STACK = "'Segoe UI Variable Text', 'Segoe UI', 'Dubai', sans-serif"
_transparency_preview = None


def transparency_level() -> int:
    from . import settings
    return _transparency_preview if _transparency_preview is not None else settings.get("glassTransparency", 60)


def material_alpha(alpha: int) -> int:
    """Opaque at zero, the original material at 60, very clear at 100."""
    value = transparency_level()
    if value <= 60:
        return round(alpha + (255 - alpha) * (1 - value / 60))
    return round(alpha * (1 - .82 * (value - 60) / 40))


def surface_strength() -> float:
    value = transparency_level()
    return 1.4 - .4 * value / 60 if value <= 60 else 1 - .82 * (value - 60) / 40


def surface_alpha(alpha: int) -> int:
    """Scale decorative fills while preserving text, icons and focus outlines."""
    return max(0, min(255, round(alpha * surface_strength())))


def material_color(color):
    value = qcolor(color)
    value.setAlpha(material_alpha(value.alpha()))
    return value


def surface_color(color):
    value = qcolor(color)
    value.setAlpha(surface_alpha(value.alpha()))
    return value


def preview_transparency(value: int) -> None:
    """Update painted surfaces live; the settings page commits styles on release."""
    global _transparency_preview
    _transparency_preview = max(0, min(100, int(value)))
    refresh_listeners()
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for window in app.topLevelWidgets():
        if window.isVisible():
            window.update()


def commit_transparency(value: int) -> None:
    global _transparency_preview
    from . import settings
    value = max(0, min(100, int(value)))
    if _transparency_preview is None and settings.get("glassTransparency", 60) == value:
        return
    settings.set("glassTransparency", value)
    _transparency_preview = None
    apply_app_theme()


def design_tokens(dark: bool | None = None) -> dict:
    """Shared material and colour values for web views and every native tool."""
    dark = is_dark() if dark is None else dark
    def fill(alpha):
        return f"rgba(255,255,255,{surface_alpha(round(alpha * 255)) / 255:.4f})"
    def body(r, g, b, alpha):
        return f"rgba({r},{g},{b},{material_alpha(alpha) / 255:.4f})"
    return {
        "ink": "#f1f3f8" if dark else "#252934",
        "muted": "#aab9cc" if dark else "#647187",
        "blue": "#afc9f5" if dark else "#416fae",
        "surface-top": fill(.14 if dark else .29),
        "surface-mid": fill(.035 if dark else .07),
        "surface-bottom": fill(.075 if dark else .16),
        "line": "rgba(255,255,255,.22)" if dark else "rgba(255,255,255,.56)",
        "soft": fill(.055 if dark else .15),
        "selected": f"rgba(170,199,245,{surface_alpha(41) / 255:.4f})" if dark else fill(.44),
        "overlay-bg": body(26, 40, 57, 191) if dark else body(242, 247, 255, 168),
        "dialog-bg": body(28, 43, 64, 237) if dark else body(237, 243, 251, 232),
    }


def native_design_tokens(dark: bool | None = None) -> dict:
    """QSS uses 0–255 alpha; browser CSS uses 0–1."""
    result = design_tokens(dark)
    for key, value in result.items():
        if value.startswith("rgba("):
            channels, alpha = value.rsplit(",", 1)
            result[key] = f"{channels},{round(float(alpha[:-1]) * 255)})"
    return result


def stylesheet(dark: bool) -> str:
    from .liquid_ui import stylesheet as liquid_stylesheet
    p = palette(dark)
    h = hud(dark)
    glass_card = f"rgba(255,255,255,{surface_alpha(18 if dark else 58)})"
    glass_card_alt = f"rgba(255,255,255,{surface_alpha(10 if dark else 32)})"
    glass_line = "rgba(255, 255, 255, 56)" if dark else "rgba(255, 255, 255, 143)"
    glass_line_soft = glass_line
    field = f"rgba(255,255,255,{surface_alpha(14 if dark else 38)})"
    # Neutral "ink" accent: a white capsule with dark text on dark, the reverse on light.
    acc = "rgba(168, 196, 240, 52)" if dark else "rgba(255,255,255,150)"
    acc_hover = "rgba(168,196,240,75)" if dark else "rgba(255,255,255,180)"
    acc_text = "#afc9f5" if dark else "#416fae"
    select = "rgba(255, 255, 255, 46)" if dark else "rgba(17, 17, 20, 30)"
    return f"""
    QWidget {{
        color: {p['text']};
        font-family: {FONT_STACK};
        font-size: 13px;
    }}
    QMainWindow, QDialog, #SettingsRoot {{
        background: {p['window']};
    }}
    QWidget[glassWindow="true"] {{
        background: transparent;
    }}
    QFrame[glassCard="true"] {{
        background: {glass_card};
        border: 1px solid {glass_line};
        border-radius: 18px;
    }}
    QTabWidget::pane {{
        border: 1px solid {glass_line_soft};
        border-radius: 16px;
        background: {glass_card};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p['text_dim']};
        padding: 7px 16px;
        margin: 0 3px 6px 3px;
        border-radius: 15px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background: {acc};
        color: {acc_text};
    }}
    QTabBar::tab:hover:!selected {{
        background: {glass_card};
        color: {p['text']};
    }}
    QGroupBox {{
        border: 1px solid {glass_line_soft};
        border-radius: 16px;
        background: {glass_card_alt};
        margin-top: 14px;
        padding: 14px 12px 12px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        right: 14px;
        padding: 0 4px;
        color: {p['text_dim']};
    }}
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {glass_card}, stop:1 {glass_card_alt});
        border: 1px solid {glass_line};
        border-radius: 15px;
        padding: 6px 16px;
        min-height: 18px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {p['hover']};
        border-color: {glass_line};
    }}
    QPushButton:pressed {{
        background: {p['card_alt']};
    }}
    QPushButton:disabled {{
        color: {p['text_dim']};
        border-color: {glass_line_soft};
    }}
    QPushButton[accent="true"] {{
        background: {acc};
        border: 1px solid rgba(255, 255, 255, 120);
        color: {acc_text};
    }}
    QPushButton[accent="true"]:hover {{
        background: {acc_hover};
    }}
    QPushButton[accent="true"]:disabled {{
        background: {p['card_alt']};
        border-color: {p['border']};
        color: {p['text_dim']};
    }}
    QPushButton[flat="true"] {{
        background: transparent;
        border: none;
        color: {p['text']};
        padding: 4px 6px;
    }}
    QPushButton[chip="true"] {{
        background: {h['peach']};
        border: 1px solid {glass_line};
        border-radius: 13px;
        padding: 5px 14px;
        color: {h['icon']};
    }}
    QPushButton[chip="true"]:hover {{
        background: {acc};
        color: {acc_text};
    }}
    QPushButton[chip="true"]:disabled {{
        background: {p['card_alt']};
        color: {p['text_dim']};
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 14px;
        padding: 6px 10px;
        font-weight: 600;
    }}
    QToolButton:hover {{
        background: {glass_card};
        border-color: {glass_line};
    }}
    QToolButton:checked {{
        background: {acc};
        color: {acc_text};
        border-color: rgba(255, 255, 255, 120);
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {field};
        border: 1px solid {glass_line_soft};
        border-radius: 11px;
        padding: 6px 10px;
        selection-background-color: {select};
        selection-color: {p['text']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {p['text_dim']};
    }}
    QSpinBox[numericControl="true"], QDoubleSpinBox[numericControl="true"] {{
        min-height: 50px;
        min-width: 92px;
        padding: 4px 6px;
    }}
    QToolButton[numericStepButton="true"] {{
        background: {p['card_alt']};
        border: none;
        border-radius: 0;
        padding: 0;
        color: {p['text_dim']};
    }}
    QToolButton[numericStepButton="true"]:hover {{
        background: {'rgba(144, 181, 235, 140)' if dark else 'rgba(95, 139, 205, 100)'};
        color: {acc_text};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        selection-background-color: {select};
        selection-color: {p['text']};
        outline: none;
        padding: 4px;
    }}
    QCheckBox, QRadioButton {{
        spacing: 8px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {p['border']};
        background: {field};
    }}
    QCheckBox::indicator {{
        border-radius: 6px;
    }}
    QRadioButton::indicator {{
        border-radius: 9px;
    }}
    QCheckBox::indicator:checked {{
        background: {'#afc9f5' if dark else '#416fae'};
        border-color: {p['text_dim']};
        image: none;
    }}
    QRadioButton::indicator:checked {{
        background: #FFFFFF;
        border: 5px solid {p['text']};
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {p['slider_track']};
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {'#afc9f5' if dark else '#6f91c6'};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {p['slider_thumb']};
        border: 1px solid {p['slider_thumb_edge']};
        width: 18px;
        height: 18px;
        margin: -7px 0;
        border-radius: 9px;
    }}
    QSlider::handle:horizontal:hover {{
        border-color: {p['text_dim']};
    }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
    QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['text_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 3px; }}
    QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 28px; }}
    QMenu {{
        background: {rgba((30, 30, 32, material_alpha(242))) if dark else rgba((252, 252, 253, material_alpha(246)))};
        border: 1px solid {glass_line};
        border-radius: 14px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 18px;
        border-radius: 9px;
        margin: 1px 0;
    }}
    QMenu::item:selected {{
        background: {select};
        color: {p['text']};
    }}
    QMenu::item:disabled {{ color: {p['text_dim']}; }}
    QMenu::separator {{ height: 1px; background: {glass_line_soft}; margin: 5px 10px; }}
    QMenu::indicator {{ width: 14px; height: 14px; border-radius: 7px; border: 1px solid {p['border']}; margin: 0 6px; }}
    QMenu::indicator:checked {{ background: {acc}; border-color: {p['text_dim']}; }}
    QLabel[muted="true"], QLabel[dim="true"], QLabel#dim {{ color: {p['text_dim']}; }}
    QToolTip {{
        background: {p['card']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 5px 9px;
    }}
    QListWidget, QTreeWidget, QTableWidget {{
        background: {field};
        border: 1px solid {glass_line_soft};
        border-radius: 14px;
        outline: none;
        padding: 4px;
    }}
    QListWidget::item, QTreeWidget::item {{
        padding: 6px 8px;
        border-radius: 10px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {select};
        color: {p['text']};
    }}
    QHeaderView::section {{
        background: {p['card_alt']};
        border: none;
        border-bottom: 1px solid {p['border']};
        padding: 6px 8px;
        font-weight: 600;
    }}
    QProgressBar {{
        border: none;
        border-radius: 6px;
        background: {p['slider_track']};
        text-align: center;
        color: {p['text']};
        height: 12px;
    }}
    QProgressBar::chunk {{
        background: {acc};
        border-radius: 6px;
    }}
    """ + liquid_stylesheet(dark)


def style_menu(menu) -> None:
    """Rounded, translucent menu (the tray menu and its submenus)."""
    from PySide6.QtCore import Qt

    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


# -- Windows 11 glass windows ------------------------------------------------

class _MARGINS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_TRANSIENTWINDOW = 3  # acrylic


def glass_window(widget, dark: bool | None = None) -> bool:
    """Keep the Qt alpha surface clear, without the opaque DWM acrylic wash."""
    if dark is None:
        dark = is_dark()
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), 4)
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4)
        backdrop = ctypes.c_int(1)  # DWMSBT_NONE: per-pixel transparency is painted by Qt.
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(backdrop), 4)
        margins = _MARGINS(0, 0, 0, 0)
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        return True
    except Exception:
        log.debug("DWM frame configuration unavailable", exc_info=True)
        return False


def window_tint(dark: bool):
    """One clear neutral material for every regular application window."""
    from PySide6.QtGui import QColor

    return material_color(QColor(18, 25, 38, 112) if dark else QColor(246, 250, 255, 118))
