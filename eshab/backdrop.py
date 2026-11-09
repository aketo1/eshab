"""The glass behind Eshab's windows: the desktop wallpaper, blurred once.

Windows' own acrylic does not reach Qt Quick's swap chain, so windows draw
this instead: a soft, cached copy of the wallpaper that each window slides
under itself as it moves, like Mica. It costs one small image per wallpaper
and nothing per frame.
"""
from __future__ import annotations

import ctypes
import hashlib
import logging
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QImage

from . import paths

log = logging.getLogger("eshab")

SPI_GETDESKWALLPAPER = 0x0073


def wallpaper_path() -> Path | None:
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buffer), buffer, 0):
            candidate = Path(buffer.value) if buffer.value else None
            if candidate is not None and candidate.is_file():
                return candidate
    except Exception:
        pass
    transcoded = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    return transcoded if transcoded.is_file() else None


def blurred_wallpaper() -> QUrl:
    """A blurred copy of the wallpaper sized for the primary screen, or an empty URL."""
    source = wallpaper_path()
    screen = QGuiApplication.primaryScreen()
    if source is None or screen is None:
        return QUrl()
    size = screen.size()
    stamp = f"{source}|{source.stat().st_mtime_ns}|{size.width()}x{size.height()}"
    cache_dir = paths.data_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"backdrop-{hashlib.sha1(stamp.encode()).hexdigest()[:12]}.png"
    if not target.is_file():
        image = QImage(str(source))
        if image.isNull():
            return QUrl()
        cover = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
        cover = cover.copy((cover.width() - size.width()) // 2, (cover.height() - size.height()) // 2,
                           size.width(), size.height())
        # Down then up twice: a wide, smooth blur without any imaging library.
        tiny = cover.scaled(QSize(max(8, size.width() // 28), max(8, size.height() // 28)),
                            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        soft = tiny.scaled(QSize(max(8, size.width() // 7), max(8, size.height() // 7)),
                           Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        soft = soft.scaled(QSize(max(8, size.width() // 3), max(8, size.height() // 3)),
                           Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        for old in cache_dir.glob("backdrop-*.png"):
            try:
                old.unlink()
            except OSError:
                pass
        if not soft.save(str(target)):
            log.warning("Could not cache the window backdrop")
            return QUrl()
    return QUrl.fromLocalFile(str(target))
