"""A bridge to the v1 editors and tool dialogs while they are rebuilt.

``Eshab --legacy-tool <key> <files…>`` opens one v1 window in its own
process and exits when it closes, so the tray process never loads the v1
UI, QtWebEngine or the imaging stack. Phase 4 replaces these windows; this
module goes with them.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("eshab")


def _prepare_webengine() -> None:
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    for flag in ("--disable-gpu", "--disable-gpu-compositing"):
        if flag not in flags:
            flags.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
    if not getattr(sys, "frozen", False):
        return
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    pyside = bundle / "PySide6"
    helper = pyside / "QtWebEngineProcess.exe"
    if not helper.is_file():
        return
    os.environ["QTWEBENGINEPROCESS_PATH"] = str(helper)
    if (pyside / "resources").is_dir():
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(pyside / "resources")
    locales = pyside / "translations" / "qtwebengine_locales"
    if locales.is_dir():
        os.environ["QTWEBENGINE_LOCALES_PATH"] = str(locales)
    bundled = [str(pyside), str(bundle)]
    rest = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p not in bundled]
    os.environ["PATH"] = os.pathsep.join(bundled + rest)


def main(argv: list[str]) -> int:
    from . import paths

    logging.basicConfig(filename=str(paths.data_dir() / "eshab-legacy.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    index = argv.index("--legacy-tool")
    key, files = argv[index + 1], [Path(f) for f in argv[index + 2:]]
    _prepare_webengine()

    from PySide6.QtCore import QLocale, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(argv[:1])
    QLocale.setDefault(QLocale("en_US"))
    app.setApplicationName("Eshab")
    app.setWindowIcon(QIcon(str(paths.assets_dir() / "icon.ico")))
    from . import i18n, render, theme

    theme.apply_app_theme()
    QTimer.singleShot(0, render.ensure_ready)
    try:
        if key == "file.shelf":
            from .file_actions import show_shelf

            show_shelf(files)
        elif key == "img.pdf":
            from .editors.pdf import open_images_pdf

            open_images_pdf(files)
        else:
            from .actions import run_tool

            run_tool([str(f) for f in files], key, None, i18n.tr("tool." + key))
    except Exception:
        log.exception("Legacy tool %s failed", key)
        return 1
    # Quit when the last window closes, or at once if nothing opened.
    QTimer.singleShot(1500, lambda: any(w.isVisible() for w in app.topLevelWindows()) or app.quit())
    return app.exec()
