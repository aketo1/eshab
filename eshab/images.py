"""Images that QML asks Python for: ``image://eshab/<kind>/<arg>``.

* ``glyph/<name>/<RRGGBB>`` — a line icon from :mod:`eshab.icons`
* ``thumb/<url-quoted path>`` — a small preview of a file (pictures are
  decoded, anything else gets its Windows file-type icon)
* ``frost/<n>`` — the blurred desktop under the wheel, captured just before
  it opens

Everything is drawn on QImage in the loader thread; nothing here touches
QPixmap, so it is safe off the GUI thread.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QImageReader, QPainter
from PySide6.QtQuick import QQuickImageProvider

log = logging.getLogger("eshab")

PICTURE_SUFFIXES = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico", ".svg"}


class Images(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image,
                         QQuickImageProvider.Flag.ForceAsynchronousImageLoading)
        self._lock = threading.Lock()
        self._frost: dict[str, QImage] = {}

    # -- frost -----------------------------------------------------------

    def put_frost(self, key: str, image: QImage) -> None:
        with self._lock:
            self._frost = {key: image}

    # -- provider --------------------------------------------------------

    def requestImage(self, image_id: str, size: QSize, requested: QSize) -> QImage:
        kind, _, rest = image_id.partition("/")
        try:
            if kind == "glyph":
                image = _glyph(rest, requested)
            elif kind == "thumb":
                image = _thumbnail(Path(unquote(rest)), requested)
            elif kind == "frost":
                with self._lock:
                    image = self._frost.get(rest, QImage())
            else:
                image = QImage()
        except Exception:
            log.exception("Image %s failed", image_id)
            image = QImage()
        if image.isNull():
            image = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


def _glyph(spec: str, requested: QSize) -> QImage:
    from . import icons

    name, _, color = spec.partition("/")
    side = max(requested.width(), requested.height(), 16) if requested.isValid() else 48
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    icons.paint_icon(painter, name, QRectF(0, 0, side, side), QColor("#" + (color or "FFFFFF")),
                     stroke=max(1.6, side / 13.0))
    painter.end()
    return image


def _thumbnail(path: Path, requested: QSize) -> QImage:
    side = max(requested.width(), requested.height(), 32) if requested.isValid() else 96
    if path.suffix.lower() in PICTURE_SUFFIXES:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        source = reader.size()
        if source.isValid():
            source.scale(side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            reader.setScaledSize(source)
        image = reader.read()
        if not image.isNull():
            return image
    return _shell_icon(path, side)


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


def _shell_icon(path: Path, side: int) -> QImage:
    """The file type's own icon, as Explorer shows it."""
    info = _SHFILEINFOW()
    flags = 0x000000100 | (0x000000000 if side > 32 else 0x000000001)  # SHGFI_ICON | LARGE/SMALL
    if not ctypes.windll.shell32.SHGetFileInfoW(str(path), 0, ctypes.byref(info), ctypes.sizeof(info), flags):
        return QImage()
    if not info.hIcon:
        return QImage()      # a file type with no icon of its own
    try:
        image = QImage.fromHICON(int(info.hIcon))
    finally:
        ctypes.windll.user32.DestroyIcon(info.hIcon)
    return image


def frost_under(rect) -> QImage:
    """Capture the desktop under ``rect`` (global, logical px) and blur it.

    Called before the wheel shows, so it never captures itself.
    """
    centre = rect.center()
    screen = QGuiApplication.screenAt(centre) or QGuiApplication.primaryScreen()
    if screen is None:
        return QImage()
    geometry = screen.geometry()
    pixmap = screen.grabWindow(0, rect.x() - geometry.x(), rect.y() - geometry.y(), rect.width(), rect.height())
    image = pixmap.toImage()
    if image.isNull():
        return image
    width, height = image.width(), image.height()
    tiny = image.scaled(max(4, width // 18), max(4, height // 18),
                        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    soft = tiny.scaled(max(4, width // 5), max(4, height // 5),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return soft.scaled(max(4, width // 2), max(4, height // 2),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
