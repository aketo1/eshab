"""Eshab v2: the tray process.

It stays small on purpose: the tray icon, the drag monitor and, only while
a window is open, a Qt Quick engine. Conversions run in the worker process
(``eshab/worker.py``), so the heavy libraries never load here.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QLocale, QLockFile, QObject, QProcess, Property, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory, QSystemTrayIcon

from . import catalog, i18n, icons, paths, settings, shellmenu, startup
from .fanwheel import FanWheel
from .images import Images
from .activity import ActivityIsland, title_for
from .monitor import DragMonitor
from .tray import Tray
from .worker_client import WorkerClient

log = logging.getLogger("eshab")

QML_DIR = Path(__file__).resolve().parent / "qml"
MATERIALS = ("honey", "clear", "ink")
RELEASE_AFTER_MS = 30_000
WHEEL_KEEP_MS = 5 * 60_000
MENU_GATHER_MS = 450        # Explorer's per-file launches arrive within this
PREWARM_KEEP_MS = 60_000

#: Tools with no options run straight in the worker; the rest open their editor.
WORKER_TOOLS = {"arc.extract", "pdf.merge", "pdf.split", "vid.removeaudio", "aud.normalize",
                "txt.compress", "pdf.compress", "doc.compress"}


def _warm_catalog() -> None:
    try:
        catalog.available_engines()
    except Exception:
        log.exception("Engine discovery failed")


def items_for(files, mode: str) -> list[dict]:
    """The cards of one wheel for the dragged files, in the user's order."""
    from . import wheel_order

    return wheel_order.arrange(_items_for(files, mode), mode)


def _items_for(files, mode: str) -> list[dict]:
    paths = [Path(f) for f in files]
    if mode == "actions":
        from .file_actions import ACTIONS

        return [{"key": key, "label": i18n.tr(label), "text": "", "glyph": icons.icon_for(key), "kind": "action"}
                for key, label in ACTIONS]
    if mode == "tools":
        return [{"key": tool.id, "label": i18n.tr("tool." + tool.id), "text": "",
                 "glyph": icons.icon_for(tool.id), "kind": "tool"}
                for tool in catalog.tools_for(paths)]
    return [{"key": conv.target_ext, "label": i18n.tr("conv." + conv.target_ext),
             "text": i18n.tr("conv." + conv.target_ext), "glyph": icons.icon_for(conv.target_ext),
             "kind": "conversion"}
            for conv in catalog.conversions_for(paths)]


#: Settings the settings window may change, and the keys a wheel can open with.
SETTING_KEYS = {"appearanceTheme", "language", "conversionWheelDragModifierMask", "toolsWheelDragModifierMask",
                "actionsWheelDragModifierMask", "suppressInFullscreen", "useOfficeForPdf", "pdfPageSize",
                "pdfMarginPreset", "pdfPageNumbers"}
MASK_CHOICES = ("shift", "alt", "ctrl", "ctrl+shift", "ctrl+alt", "alt+shift", "")

#: Tools that open an editor (eshab/editor_app.py) in a process of its own.
EDITOR_TOOLS = {"img.compress", "img.metadata", "gif.metadata", "img.edit", "img.annotate", "img.background", "img.crop",
                "img.redact", "img.pdf", "img.collage", "qr.read", "pdf.qr", "aud.compress", "vid.compress", "aud.metadata",
                "vid.metadata", "pdf.metadata", "aud.trim", "aud.bleep", "aud.channels", "aud.visualizer", "vid.trim",
                "vid.crop", "vid.speed", "vid.snapshots", "vid.split", "vid.redact", "vid.join", "pdf.edit"}


def launch_editor(key: str, paths) -> None:
    """Open an editor in its own process; it reports back through the island."""
    from .worker_client import worker_command

    program, arguments = worker_command()
    arguments = [a for a in arguments if a != "--worker"] + ["--editor", key] + [str(p) for p in paths]
    if not QProcess.startDetached(program, arguments):
        log.error("Could not open the %s editor", key)


class Bridge(QObject):
    """What QML may ask of Python: strings, the backdrop, the material, the settings."""

    changed = Signal()

    def __init__(self, app: "App"):
        super().__init__(app)
        self._app = app
        self._backdrop: QUrl | None = None
        self._language_at_start = i18n.current_language()

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

    @Slot(str)
    def setMaterial(self, key: str) -> None:
        self._app.set_material(key)
        self.changed.emit()

    # -- the settings window -------------------------------------------------

    @Slot(str, result="QVariant")
    def setting(self, key: str):
        if key == "material":
            return settings.get("material", "honey")
        if key == "language":
            return i18n.current_language()
        return settings.get(key)

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value) -> None:
        if key not in SETTING_KEYS:
            return
        if key.endswith("ModifierMask") and value not in MASK_CHOICES:
            return
        settings.set(key, value)
        settings.save()
        if key == "appearanceTheme":
            self._app._apply_theme()
        self.changed.emit()

    @Property("QVariantList", constant=True)
    def maskChoices(self) -> list:
        return [{"value": mask, "label": settings.mask_label(mask)} for mask in MASK_CHOICES]

    @Slot(str, result=str)
    def maskLabel(self, mask: str) -> str:
        return settings.mask_label(mask)

    @Property(bool, notify=changed)
    def startup(self) -> bool:
        return startup.enabled()

    @Slot(bool)
    def setStartup(self, on: bool) -> None:
        startup.set_enabled(on)
        self._app.sync_menu()
        self.changed.emit()

    # -- the user's order of the wheel cards ---------------------------------

    @Slot(str, result="QVariantList")
    def wheelCards(self, mode: str) -> list:
        from . import wheel_order

        return wheel_order.cards(mode)

    @Slot(str, str, int)
    def moveCard(self, mode: str, key: str, delta: int) -> None:
        from . import wheel_order

        wheel_order.move(mode, key, delta)
        self.changed.emit()

    @Slot(str, str)
    def toggleCard(self, mode: str, key: str) -> None:
        from . import wheel_order

        wheel_order.toggle(mode, key)
        self.changed.emit()

    @Slot(str)
    def resetCards(self, mode: str) -> None:
        from . import wheel_order

        wheel_order.reset(mode)
        self.changed.emit()

    @Property(bool, notify=changed)
    def shellMenu(self) -> bool:
        return shellmenu.registered()

    @Slot(bool)
    def setShellMenu(self, on: bool) -> None:
        shellmenu.set_enabled(on)
        self.changed.emit()

    @Property(bool, notify=changed)
    def restartNeeded(self) -> bool:
        return i18n.current_language() != self._language_at_start

    @Slot()
    def restart(self) -> None:
        self._app.restart()

    @Slot()
    def openSettings(self) -> None:
        self._app.open_settings()

    @Slot()
    def openGuide(self) -> None:
        self._app.open_guide()

    @Slot()
    def openSettingsFolder(self) -> None:
        folder = paths.settings_file().parent
        QProcess.startDetached("explorer.exe", [str(folder)])


class App(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.bridge = Bridge(self)
        self._engine: QQmlEngine | None = None
        self._windows: dict[str, tuple[QQmlComponent, QObject]] = {}
        self._release = QTimer(self)
        self._release.setSingleShot(True)
        self._release.setInterval(RELEASE_AFTER_MS)
        self._release.timeout.connect(self._release_engine)

        self._island: ActivityIsland | None = None
        self.worker = WorkerClient(self)
        self.worker.finished.connect(self._job_finished)
        self.worker.failed.connect(self._job_failed)
        self.worker.cancelled.connect(lambda job_id: self._job_settled("idle", job_id))
        self.worker.progress.connect(lambda job_id, value: self._island and self._island.progress(job_id, value))
        self.worker.status.connect(lambda job_id, text: self._island and self._island.status(job_id, text))

        self.tray = Tray(self)
        self.tray.icon.setToolTip(i18n.tr("tray.tooltip"))
        self.tray.icon.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.icon.show()

        self._images: Images | None = None
        self._wheel: FanWheel | None = None
        self._menu_files: list[str] = []
        self._menu_mode = "conversion"
        self._menu_timer = QTimer(self)
        self._menu_timer.setSingleShot(True)
        self._menu_timer.timeout.connect(self._open_menu_wheel)
        shellmenu.sync()
        self.monitor = DragMonitor(self)
        self.monitor.wheelShown.connect(lambda pos, files, mode: self._show_wheel(pos, files, mode))
        self.monitor.keyboardTriggered.connect(lambda pos, files, mode: self._show_wheel(pos, files, mode, keyboard=True))
        self.monitor.stickyTriggered.connect(lambda pos, files, mode: self._show_wheel(pos, files, mode, pinned=True))
        self.monitor.wheelMoved.connect(lambda pos: self._wheel and self._wheel.pointer_global(pos))
        self.monitor.wheelRefreshed.connect(lambda mode: self._wheel and self._wheel.switch(mode))
        self.monitor.wheelHidden.connect(lambda: self._wheel and self._wheel.dismiss())
        self.monitor.stickyClicked.connect(self._sticky_click)
        self.monitor.dragStarted.connect(self._prewarm)
        # Engine discovery can start ffprobe: never on the UI thread.
        threading.Thread(target=_warm_catalog, name="eshab-catalog", daemon=True).start()

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self._apply_theme())

    # -- tray ------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight)
        menu.addAction(i18n.tr("recent.title")).triggered.connect(self.show_recent)
        menu.addAction(i18n.tr("tray.how")).triggered.connect(self.open_guide)
        menu.addAction(i18n.tr("tray.settings")).triggered.connect(self.open_settings)
        menu.addAction(i18n.tr("tray.about")).triggered.connect(self.open_about)
        menu.addSeparator()
        launch = menu.addAction(i18n.tr("tray.startup"))
        launch.setCheckable(True)
        launch.setChecked(startup.enabled())
        launch.toggled.connect(self._startup_toggled)
        menu.addSeparator()
        menu.addAction(i18n.tr("tray.quit")).triggered.connect(self.quit)
        self._menu = menu
        self._startup_action = launch
        self.tray.icon.setContextMenu(menu)

    def _startup_toggled(self, on: bool) -> None:
        startup.set_enabled(on)
        self.bridge.changed.emit()

    def sync_menu(self) -> None:
        """The menu's tick follows a change made in the settings window."""
        self._startup_action.blockSignals(True)
        self._startup_action.setChecked(startup.enabled())
        self._startup_action.blockSignals(False)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_guide()

    # -- the wheel -------------------------------------------------------

    def wheel(self) -> FanWheel:
        if self._wheel is None:
            self._wheel = FanWheel(self.engine(), self._images, items_for, self)
            self._wheel.activated.connect(self._activated)
            self._wheel.closed.connect(self.monitor.sticky_release)
        return self._wheel

    def _prewarm(self) -> None:
        """A file drag began in Explorer: build the wheel (not its graphics)
        so a modifier opens it sooner. Released after a minute if unused."""
        if self._wheel is not None:
            return
        try:
            self.wheel()
        except Exception:
            log.exception("Could not prepare the wheel")
            return
        if not self._release.isActive() or self._release.remainingTime() < PREWARM_KEEP_MS:
            self._release.start(PREWARM_KEEP_MS)

    def _show_wheel(self, pos, files, mode: str, pinned: bool = False, keyboard: bool = False) -> None:
        self._release.stop()
        try:
            self.wheel().show_at(pos, files, mode, pinned=pinned, keyboard=keyboard)
        except Exception:
            log.exception("The wheel could not open")
            return
        # Keep the engine warm for a while: the next drag opens instantly.
        self._release.start(WHEEL_KEEP_MS)

    def _sticky_click(self, pos) -> None:
        wheel = self._wheel
        if wheel is not None and wheel.is_open() and not wheel.contains(pos):
            self.monitor.notify_dropped()
            wheel.escape()

    def _activated(self, files, key: str, mode: str) -> None:
        self.monitor.notify_dropped()
        paths = [Path(f) for f in files]
        anchor = self._wheel.origin() if self._wheel is not None else QCursor.pos()
        try:
            if mode == "actions":
                self._run_action(key, paths, anchor)
            elif mode == "tools":
                subset = catalog.tool_paths(key, paths)
                if key in WORKER_TOOLS and subset:
                    self.tray.set_state("working")
                    self._track(self.worker.tool(subset, key), mode, key, subset, anchor)
                elif subset and key in EDITOR_TOOLS:
                    launch_editor(key, subset)
                elif subset:
                    log.warning("No editor or worker job for the %s tool", key)
            else:
                subset = catalog.conversion_paths(key, paths)
                if key == "pdf" and len(subset) > 1 and all(catalog.family_of(p) == catalog.FAMILY_IMAGE for p in subset):
                    launch_editor("img.pdf", subset)  # several pictures: let the user order the pages
                elif subset:
                    self._track(self.convert(subset, key), mode, key, subset, anchor)
        except Exception:
            log.exception("Could not start %s/%s", mode, key)

    def _track(self, job_id: str, mode: str, key: str, files, anchor) -> None:
        detail = files[0].name if len(files) == 1 else i18n.tr("wheel.files_count", n=len(files))
        try:
            self.island().start(job_id, title_for(mode, key), detail, anchor)
        except Exception:
            log.exception("Could not show the progress card")

    def _menu_wheel(self, files, mode: str) -> None:
        """Explorer runs one Eshab per selected file: gather them for a moment,
        then open one wheel under the pointer (click a card, or Esc)."""
        files = [str(Path(f)) for f in files if Path(f).exists()]
        if not files:
            return
        wheel = self._wheel
        if wheel is not None and wheel.is_open() and self._menu_mode == mode and wheel.keyboard:
            wheel.add_files(files)
            return
        if mode != self._menu_mode:
            self._menu_files = []
        self._menu_mode = mode
        for file in files:
            if file not in self._menu_files:
                self._menu_files.append(file)
        self._menu_timer.start(MENU_GATHER_MS)

    def _open_menu_wheel(self) -> None:
        files, self._menu_files = self._menu_files, []
        if files:
            self._show_wheel(QCursor.pos(), files, self._menu_mode, keyboard=True)
            if self._wheel is not None and self._wheel.is_open():
                self.monitor.pin()      # a click outside closes it

    def show_recent(self) -> None:
        try:
            self.island().show_recent(QCursor.pos())
        except Exception:
            log.exception("Could not show the recent files")

    def island(self) -> ActivityIsland:
        if self._island is None:
            self._island = ActivityIsland(self.engine(), self)
            self._island.cancelRequested.connect(self.worker.cancel)
        return self._island

    def _run_action(self, key: str, paths, anchor) -> None:
        if key == "file.shelf":
            self.island().shelve(paths)
            return
        from . import file_actions

        message = file_actions.run(key, paths)
        if message:
            self.island().note(message)

    # -- jobs ------------------------------------------------------------

    def convert(self, files, target: str) -> str:
        self.tray.set_state("working")
        return self.worker.convert(files, target)

    def _job_finished(self, job_id: str, outputs: list) -> None:
        if self._island is not None:
            self._island.finish(job_id, outputs[0] if outputs else "", "done")
        self._job_settled("done", job_id)

    def _job_settled(self, state: str, job_id: str = "") -> None:
        if state == "idle" and self._island is not None:
            self._island.dismiss(job_id)
        if not self.worker.busy():
            self.tray.set_state(state)

    def _job_failed(self, job_id: str, message: str) -> None:
        log.error("Job %s failed: %s", job_id, message)
        if self._island is not None:
            self._island.finish(job_id, "", "error", message)
        if not self.worker.busy():
            self.tray.set_state("error")

    # -- Qt Quick ----------------------------------------------------------

    def engine(self) -> QQmlEngine:
        if self._engine is None:
            engine = QQmlEngine(self)
            engine.addImportPath(str(QML_DIR))
            engine.rootContext().setContextProperty("eshab", self.bridge)
            self._images = Images()
            engine.addImageProvider("eshab", self._images)
            self._engine = engine
            self._apply_theme()
        return self._engine

    def _theme(self) -> QObject | None:
        if self._engine is None:
            return None
        return self._engine.singletonInstance("Eshab", "Theme")

    def _apply_theme(self) -> None:
        theme = self._theme()
        if theme is None:
            return
        material = settings.get("material", "honey")
        theme.setProperty("material", material if material in MATERIALS else "honey")
        choice = settings.appearance_theme()
        if choice == "system":
            dark = QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
        else:
            dark = choice == "dark"
        theme.setProperty("dark", dark)

    def set_material(self, key: str) -> None:
        if key not in MATERIALS:
            return
        settings.set("material", key)
        settings.save()
        self._apply_theme()

    def _open_window(self, name: str) -> None:
        self._release.stop()
        if name in self._windows:
            window = self._windows[name][1]
            window.show()
            window.raise_()
            window.requestActivate()
            return
        component = QQmlComponent(self.engine(), QUrl.fromLocalFile(str(QML_DIR / "windows" / f"{name}.qml")))
        window = component.create()
        if window is None:
            for error in component.errors():
                log.error("QML %s: %s", name, error.toString())
            return
        # The component must outlive the window: PySide deletes what it
        # created when the component is collected.
        self._windows[name] = (component, window)
        window.visibleChanged.connect(lambda visible, n=name: visible or self._close_window(n))
        window.show()
        window.requestActivate()

    def _close_window(self, name: str) -> None:
        entry = self._windows.pop(name, None)
        if entry is not None:
            component, window = entry
            window.deleteLater()
            component.deleteLater()
        if not self._windows:
            self._release.start(RELEASE_AFTER_MS)

    def _release_engine(self) -> None:
        """Nothing has been open for a while: give the Qt Quick engine and
        the graphics device back, so the tray returns to its idle size."""
        if self._windows or self._engine is None:
            return
        if self._island is not None and self._island.busy():
            self._release.start(RELEASE_AFTER_MS)
            return
        island, self._island = self._island, None
        if island is not None:
            island.window.deleteLater()
            island.drop.deleteLater()
            island.deleteLater()
        wheel, self._wheel = self._wheel, None
        if wheel is not None:
            if wheel.is_open():
                self._wheel = wheel
                self._release.start(WHEEL_KEEP_MS)
                return
            wheel.window.deleteLater()
            wheel.deleteLater()
        engine, self._engine = self._engine, None
        self._images = None
        engine.deleteLater()
        log.info("Released the Qt Quick engine")

    def open_about(self) -> None:
        self._open_window("About")

    def open_settings(self) -> None:
        self._open_window("Settings")

    def open_guide(self) -> None:
        self._open_window("Guide")

    def restart(self) -> None:
        """Start a new Eshab (it waits for this one to let go of its lock), then quit."""
        from .worker_client import worker_command

        program, arguments = worker_command()
        arguments = [a for a in arguments if a != "--worker"] + ["--restarted"]
        if QProcess.startDetached(program, arguments):
            self.quit()
        else:
            log.error("Could not restart Eshab")

    # -- requests ----------------------------------------------------------

    def handle_request(self, request: dict) -> None:
        action = request.get("action")
        if action == "quit":
            self.quit()
        elif action == "welcome":
            self.open_guide()
        elif action == "wheel":
            self._menu_wheel(request["paths"], request["mode"])
        elif action == "notify":
            # an editor finished its work in its own process: the island shows it like any job
            try:
                island = self.island()
                island.start(request["id"], request.get("title", ""), request.get("detail", ""), QCursor.pos())
                island.finish(request["id"], request.get("output", ""), "done", request.get("detail", ""))
            except Exception:
                log.exception("Could not show a finished edit")
        else:
            log.info("Request %r is not available in this build yet", action)

    def quit(self) -> None:
        self.monitor.stop()
        self.worker.shutdown()
        self.tray.icon.hide()
        self.qapp.quit()


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
    def handle(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.error("Unhandled exception: %s", exc, exc_info=(exc_type, exc, tb))
        _write_crash_log("".join(traceback.format_exception(exc_type, exc, tb)))

    def handle_thread(args):
        if issubclass(args.exc_type, SystemExit):
            return
        log.error("Unhandled exception in thread: %s", args.exc_value,
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = handle
    threading.excepthook = handle_thread


def _run() -> int:
    from .requests import RequestServer, forward_request, parse_request

    arguments = [a for a in sys.argv[1:] if a != "--restarted"]
    restarted = len(arguments) != len(sys.argv) - 1
    request = parse_request(arguments)
    app = QApplication(sys.argv[:1] + arguments)
    if "windows11" in (key.lower() for key in QStyleFactory.keys()):
        app.setStyle("windows11")  # native Windows 11 menus for the tray
    # Arabic text, Western digits: sizes and pixels read as 1920, not ١٩٢٠.
    QLocale.setDefault(QLocale("en_US"))
    app.setApplicationName("Eshab")
    app.setApplicationDisplayName(i18n.tr("app.name"))
    app.setApplicationVersion(paths.APP_VERSION)
    app.setOrganizationName("Eshab")
    app.setWindowIcon(QIcon(str(paths.assets_dir() / "icon.ico")))
    app.setQuitOnLastWindowClosed(False)
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    if request is not None:
        # Started by a click in Explorer, this process may bring a window to
        # the front; the running Eshab may not, unless it is lent that right.
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1 & 0xFFFFFFFF)
        except Exception:
            pass
    if request is not None and forward_request(request, 300):
        return 0
    if request is not None and request.get("action") == "quit":
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("No system tray available")
        return 1

    lock = QLockFile(str(paths.data_dir() / "eshab.lock"))
    # A restart waits for the Eshab it replaces to finish quitting.
    if not lock.tryLock(10_000 if restarted else 0):
        request = request or parse_request(["--welcome"])
        for _ in range(6):
            if forward_request(request, 500):
                return 0
            QThread.msleep(150)
        _show_error(i18n.tr("pdf.instance.old"))
        return 2
    # The lock is ours, yet another Eshab may still be answering requests
    # (one whose lock file went away under it). Two would each open a wheel,
    # one over the other: let the running one carry on.
    if request is None and not restarted and forward_request(parse_request(["--welcome"]), 400):
        return 0

    server = RequestServer(app)
    if not server.listen():
        raise RuntimeError(server.server.errorString())
    controller = App(app)
    server.received.connect(controller.handle_request)
    if request is not None:
        QTimer.singleShot(0, lambda: controller.handle_request(request))
    elif not settings.get("welcomeShown", False):
        def first_run() -> None:
            controller.open_guide()
            settings.set("welcomeShown", True)
            settings.save()

        QTimer.singleShot(400, first_run)
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
