"""What any Eshab window's QML may ask of Python: words, direction, the backdrop, the material."""
from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, QUrl, Qt, Slot
from PySide6.QtGui import QGuiApplication

from . import i18n, paths, settings

log = logging.getLogger("eshab")
MATERIALS = ("honey", "clear", "ink")


class Bridge(QObject):
    def __init__(self, parent=None, on_material=None):
        super().__init__(parent)
        self._backdrop: QUrl | None = None
        self._on_material = on_material
        self._theme = None

    @Property(bool, constant=True)
    def rtl(self) -> bool:
        return i18n.is_rtl()

    @Property(str, constant=True)
    def version(self) -> str:
        return i18n.tr("about.version", version=paths.APP_VERSION)

    @Property(QUrl, constant=True)
    def backdrop(self) -> QUrl:
        if self._backdrop is None:
            from .backdrop import blurred_wallpaper

            try:
                self._backdrop = blurred_wallpaper()
            except Exception:
                log.exception("Could not prepare the window backdrop")
                self._backdrop = QUrl()
        return self._backdrop

    @Slot(str, result=str)
    def tr(self, key: str) -> str:
        return i18n.tr(key)

    @Slot(int, int, result="QVariantMap")
    def workArea(self, x: int, y: int) -> dict:
        """The free part (taskbar left out) of the screen at a point, or under the cursor for (-1, -1)."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QCursor

        point = QCursor.pos() if x < 0 or y < 0 else QPoint(x, y)
        screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        if screen is None:
            return {"x": 0, "y": 0, "width": 1280, "height": 800}
        rect = screen.availableGeometry()
        return {"x": rect.x(), "y": rect.y(), "width": rect.width(), "height": rect.height()}

    @Slot(str)
    def setMaterial(self, key: str) -> None:
        if key not in MATERIALS:
            return
        settings.set("material", key)
        settings.save()
        if self._on_material is not None:
            self._on_material(key)
        elif self._theme is not None:
            self.apply_theme(self._theme)

    def apply_theme(self, theme) -> None:
        """The chosen material, and light or dark as Windows or the user says."""
        self._theme = theme
        material = settings.get("material", "honey")
        theme.setProperty("material", material if material in MATERIALS else "honey")
        choice = settings.appearance_theme()
        if choice == "system":
            dark = QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
        else:
            dark = choice == "dark"
        theme.setProperty("dark", dark)
