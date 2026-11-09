"""Eshab's controller: tray icon, drag monitor, liquid wheel and jobs."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QLocale, QLockFile, QObject, QThread, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import actions, catalog, i18n, paths, render, settings, startup, theme
from .monitor import DragMonitor
from .wheel import FanItem, LiquidWheel

log = logging.getLogger("eshab")


def _write_crash_log(message: str) -> None:
    try:
        with (paths.data_dir() / "crash.log").open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def _show_error(message: str) -> None:
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "Eshab", 0x10)
    except Exception:
        pass


def _install_excepthooks() -> None:
    def handle_exception(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception: %s", exc, exc_info=(exc_type, exc, tb))
        _write_crash_log(text)

    def handle_thread_exception(args):
        if issubclass(args.exc_type, SystemExit):
            return
        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        log.error("Unhandled exception in thread: %s", args.exc_value,
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        _write_crash_log(text)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception


def _warm_catalog() -> None:
    try:
        catalog.available_engines()
    except Exception:
        pass


def enabled_modes() -> list[str]:
    modes = []
    for mode, key in (("conversion", "conversionWheelDragModifierMask"),
                      ("tools", "toolsWheelDragModifierMask"),
                      ("actions", "actionsWheelDragModifierMask")):
        if settings.parse_mask(settings.get(key, "")):
            modes.append(mode)
    return modes or ["conversion"]


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._mode = "conversion"
        self._jobs = []
        self._home = None
        self._settings_window = None
        self._last_output: Path | None = None
        from .progress import events
        events().started.connect(self._track)

        self.wheel = LiquidWheel()
        self.wheel.set_factory(self._factory)
        self.wheel.set_modes(enabled_modes())
        self.wheel.activated.connect(self._activated)
        self.wheel.modeRequested.connect(self._refresh_wheel)

        self.monitor = DragMonitor(self)
        self.monitor.wheelShown.connect(self._show_wheel)
        self.monitor.wheelMoved.connect(self._move_wheel)
        self.monitor.wheelHidden.connect(self._hide_wheel)
        self.monitor.wheelRefreshed.connect(self._refresh_wheel)
        self.monitor.keyboardTriggered.connect(self._keyboard_wheel)
        self.monitor.stickyTriggered.connect(self._keyboard_wheel)
        self.monitor.stickyClicked.connect(self._sticky_click)
        self.wheel.closed.connect(self.monitor.sticky_release)

        self.tray = QSystemTrayIcon(QIcon(str(paths.icon_path())), self)
        self.tray.setToolTip(i18n.tr("tray.tooltip"))
        self._menu: QMenu | None = None
        self._active_menu: QMenu | None = None
        self._build_tray_menu()
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._open_last_output)
        self.tray.show()
        i18n.add_listener(self._language_changed)

    # -- tray ------------------------------------------------------------

    def _build_tray_menu(self) -> None:
        menu = QMenu()
        menu.setLayoutDirection(theme.direction())
        theme.style_menu(menu)
        menu.addAction(i18n.tr("home.open")).triggered.connect(self.open_home)
        from .file_actions import show_shelf
        menu.addAction(i18n.tr("shelf.title")).triggered.connect(lambda: show_shelf())
        menu.addSeparator()
        menu.addAction(i18n.tr("tray.edit_pdf")).triggered.connect(self.open_pdf)
        menu.addAction(i18n.tr("tray.images_pdf")).triggered.connect(lambda: self.open_images_pdf())
        self._active_menu = menu.addMenu(i18n.tr("tray.active"))
        theme.style_menu(self._active_menu)
        self._active_menu.aboutToShow.connect(self._rebuild_active)
        menu.addSeparator()
        menu.addAction(i18n.tr("tray.settings")).triggered.connect(self.open_settings)
        launch = menu.addAction(i18n.tr("tray.startup"))
        launch.setCheckable(True)
        launch.setChecked(startup.enabled())
        launch.toggled.connect(startup.set_enabled)
        menu.addSeparator()
        menu.addAction(i18n.tr("tray.quit")).triggered.connect(lambda: self._quit())
        self._menu = menu
        self.tray.setContextMenu(menu)

    def _language_changed(self, code=None) -> None:
        try:
            self.tray.setToolTip(i18n.tr("tray.tooltip"))
            self._build_tray_menu()
            self.wheel.set_modes(enabled_modes())
            if self.wheel.file_paths():
                self._refresh_wheel(self._mode)
            self.wheel.update()
        except Exception:
            log.exception("Could not refresh the UI after a language change")

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_home()

    def _rebuild_active(self) -> None:
        self._active_menu.clear()
        if not self._jobs:
            self._active_menu.addAction(i18n.tr("tray.nothing_active")).setEnabled(False)
            return
        for window in list(self._jobs):
            action = self._active_menu.addAction(window.windowTitle() or i18n.tr("tray.working"))
            action.triggered.connect(lambda _=False, w=window: (w.show(), w.raise_()))

    # -- wheel -----------------------------------------------------------

    def _items_for(self, files, mode) -> list[FanItem]:
        sources = [Path(f) for f in (files or [])]
        if mode == "actions":
            from .file_actions import ACTIONS

            return [FanItem(key, i18n.tr(label), kind="tool") for key, label in ACTIONS]
        if mode == "tools":
            return [FanItem(tool.id, i18n.tr("tool." + tool.id), kind="tool")
                    for tool in catalog.tools_for(sources)]
        return [FanItem(conv.target_ext, i18n.tr("conv." + conv.target_ext), kind="conversion")
                for conv in catalog.conversions_for(sources)]

    def _factory(self, files):
        return self._items_for(files, self._mode)

    def _show_wheel(self, pos, files, mode) -> None:
        log.info("Wheel shown: mode=%s, known files=%d", mode, len(files or []))
        self.wheel.cancel_dismiss()
        self._mode = mode
        self.wheel.set_keyboard_mode(False)
        self.wheel.set_modes(enabled_modes())
        self.wheel.set_mode(mode)
        if files:
            self.wheel.set_files(files)
            self.wheel.set_items(self._items_for(files, mode))
        elif not self.wheel.isVisible():
            self.wheel.reset()
            self.wheel.set_mode(mode)
        if not self.wheel.isVisible():
            self.wheel.center_at(pos)
        self.wheel.show()
        self.wheel.raise_()

    def _keyboard_wheel(self, pos, files, mode) -> None:
        self._show_wheel(pos, files, mode)
        self.wheel.set_keyboard_mode(True)

    def _sticky_click(self, pos) -> None:
        if self.wheel.isVisible() and not self.wheel.frameGeometry().contains(pos):
            self.monitor.notify_dropped()
            self.wheel._close()

    def _refresh_wheel(self, mode) -> None:
        if mode == self._mode and self.wheel.scene.items:
            return
        self._mode = mode
        self.wheel.set_mode(mode)
        files = self.wheel.file_paths()
        if files:
            self.wheel.set_items(self._items_for(files, mode), animate=True)

    def _move_wheel(self, pos) -> None:
        self.wheel.update_cursor(pos)

    def _hide_wheel(self) -> None:
        self.wheel.set_keyboard_mode(False)
        self.wheel.dismiss()

    def _activated(self, files, key) -> None:
        log.info("Wheel activated: mode=%s, target=%s, files=%d", self._mode, key, len(files or []))
        self.monitor.notify_dropped()
        if not files:
            return
        try:
            if self._mode == "actions":
                from .file_actions import run

                message = run(key, files)
                if message:
                    self.tray.showMessage(i18n.tr("app.name"), message,
                                          QSystemTrayIcon.MessageIcon.Information, 2500)
                return
            sources = [Path(f) for f in files]
            if self._mode == "tools":
                subset = [str(p) for p in catalog.tool_paths(key, sources)]
                window = actions.run_tool(subset, key, None, i18n.tr("tool." + key)) if subset else None
            else:
                subset = [str(p) for p in catalog.conversion_paths(key, sources)]
                window = actions.run_conversions(subset, key) if subset else None
            self._track(window)
        except Exception as exc:
            log.exception("Action %s failed to start", key)
            QMessageBox.warning(None, i18n.tr("app.name"), str(exc))

    # -- jobs ------------------------------------------------------------

    def _track(self, window) -> None:
        if window is None:
            return
        if hasattr(window, "bridge") and hasattr(window, "controller"):
            window.controller = self
            return
        if hasattr(window, "job_windows"):
            for job_window in window.job_windows:
                self._track(job_window)
            return
        if not hasattr(window, "job"):
            if hasattr(window, "job_window"):
                self._track(window.job_window)
                if hasattr(window, "finished"):
                    window.finished.connect(lambda *_: self._track(window.job_window))
            return
        if window in self._jobs or getattr(window, "_job_done", False):
            return
        self._jobs.append(window)
        window.job.finished.connect(self._job_finished)
        window.job.finished.connect(lambda *_a, w=window: self._forget(w))
        window.job.failed.connect(lambda *_a, w=window: self._forget(w))

    def _forget(self, window) -> None:
        if window in self._jobs:
            self._jobs.remove(window)

    def _job_finished(self, outputs) -> None:
        if outputs:
            self._last_output = Path(outputs[0])
            log.info("Job completed: %d output file(s)", len(outputs))

    def _open_last_output(self) -> None:
        if self._last_output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output.parent)))

    # -- windows ---------------------------------------------------------

    def open_home(self) -> None:
        from .studio import StudioWindow

        if self._home is None:
            self._home = StudioWindow(controller=self)
        self._home.present()

    def open_settings(self):
        if self._settings_window is not None and self._settings_window.isVisible():
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            return self._settings_window
        from . import settings_window

        self._settings_window = settings_window.open_settings(pdf_callback=self.open_images_pdf)
        return self._settings_window

    def open_images_pdf(self, files=None, order=None):
        from .editors.pdf import open_images_pdf

        try:
            window = open_images_pdf(files, order=order)
            self._track(window)
            return window
        except Exception as exc:
            log.exception("Could not open the images-to-PDF editor")
            QMessageBox.warning(None, i18n.tr("app.name"), str(exc))
            return None

    def open_pdf(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(None, i18n.tr("pdfedit.title"), "", "PDF (*.pdf)")
        if not path:
            return None
        try:
            from .studio import open_studio

            return open_studio("pdf", path, controller=self)
        except Exception as exc:
            log.exception("Could not open the PDF editor")
            QMessageBox.warning(None, i18n.tr("app.name"), str(exc))
            return None

    def handle_request(self, request) -> None:
        action = request.get("action")
        if action == "quit":
            self._quit(confirm=False)
            return
        if action == "welcome":
            self.open_home()
            return
        if action == "edit":
            self.open_pdf(request["paths"][0])
            return
        from . import engines, progress
        from .image_pdf import PdfOptions, is_pdf_image

        files = [Path(p) for p in request["paths"]]
        if not files:
            self.open_images_pdf(order=request["order"])
            return
        if not all(is_pdf_image(p) and p.is_file() for p in files):
            QMessageBox.warning(None, i18n.tr("app.name"), i18n.tr("pdf.images.invalid"))
            return
        if request["quick"]:
            options = PdfOptions(order=request["order"])
            window = progress.run_job(i18n.tr("action.creating_pdf"),
                                      lambda ctx: [engines.images_to_pdf(files, ctx, set(), options)],
                                      anchor=QCursor.pos())
            self._track(window)
        else:
            self.open_images_pdf(files, request["order"])

    def _quit(self, confirm: bool = True) -> None:
        if self._jobs and confirm:
            choice = QMessageBox.question(None, i18n.tr("app.name"), i18n.tr("tray.quit_running"))
            if choice != QMessageBox.StandardButton.Yes:
                return
        for window in list(self._jobs):
            job = getattr(window, "job", None)
            if job is not None:
                job.cancel()
        self.monitor.stop()
        self.tray.hide()
        self.app.quit()


def _already_running(app) -> int:
    tray = QSystemTrayIcon(QIcon(str(paths.icon_path())))
    tray.show()
    tray.showMessage(i18n.tr("app.name"), i18n.tr("tray.already_running"),
                     QSystemTrayIcon.MessageIcon.Information, 4000)
    QTimer.singleShot(4200, app.quit)
    app.exec()
    return 1


def _run() -> int:
    from .requests import RequestServer, forward_request, parse_request

    request = parse_request(sys.argv[1:])
    app = QApplication(sys.argv)
    # Arabic text, Western digits: sizes and pixels read as 1920, not ١٩٢٠.
    QLocale.setDefault(QLocale("en_US"))
    app.setApplicationName("Eshab")
    app.setApplicationDisplayName(i18n.tr("app.name"))
    app.setApplicationVersion(paths.APP_VERSION)
    app.setOrganizationName("Eshab")
    app.setWindowIcon(QIcon(str(paths.icon_png())))
    app.setQuitOnLastWindowClosed(False)
    theme.apply_app_theme()

    if request is not None and forward_request(request, 300):
        return 0
    if request is not None and request.get("action") == "quit":
        return 0  # nothing is running
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("No system tray available")
        return 1

    lock = QLockFile(str(paths.data_dir() / "eshab.lock"))
    if not lock.tryLock(0):
        if request is None:
            request = parse_request(["--welcome"])
        if request is not None:
            for _ in range(6):
                if forward_request(request, 500):
                    return 0
                QThread.msleep(150)
            _show_error(i18n.tr("pdf.instance.old"))
            return 2
        return _already_running(app)

    server = RequestServer(app)
    if not server.listen():
        raise RuntimeError(server.server.errorString())
    controller = Controller(app)
    server.received.connect(controller.handle_request)
    if request is not None:
        QTimer.singleShot(0, lambda: controller.handle_request(request))
    # Engine discovery can launch ffprobe; never run it on the UI event loop.
    threading.Thread(target=_warm_catalog, daemon=True).start()
    QTimer.singleShot(700, render.ensure_ready)
    if request is None:
        def first_run() -> None:
            controller.open_home()
            if not settings.get("welcomeShown", False):
                settings.set("welcomeShown", True)
                settings.save()

        QTimer.singleShot(250, first_run)
    return app.exec()


def main() -> int:
    logging.basicConfig(
        filename=str(paths.log_file()),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.getLogger("comtypes").setLevel(logging.WARNING)
    _install_excepthooks()
    try:
        return _run()
    except Exception as exc:
        text = f"Eshab failed to start: {exc}\n\n" + "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__))
        log.error("Eshab failed to start: %s", exc, exc_info=True)
        _write_crash_log(text)
        _show_error(text)
        return 1
