"""The tray icon: the mark next to the clock, and what it shows while working.

States: ``idle``; ``working`` (the page fills and empties, only while a job
runs); ``done`` (a tick, then idle); ``error`` (a red dot, then idle). The
glyphs are pre-rendered by scripts/make_brand.py, so nothing is drawn here.
"""
from __future__ import annotations

import winreg

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from . import paths

SIZES = (16, 20, 24, 32, 40)
WORK_FRAMES = 8
FRAME_MS = 110
HOLD_MS = {"done": 2200, "error": 6000}


def taskbar_tone() -> str:
    """``light`` when the taskbar is light (dark glyphs), otherwise ``dark``."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return "light" if int(value) else "dark"
    except OSError:
        return "dark"


class Tray(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(self)
        self._tone = taskbar_tone()
        self._cache: dict[tuple[str, str], QIcon] = {}
        self._state = "idle"
        self._frame = 0
        self._animator = QTimer(self)
        self._animator.setInterval(FRAME_MS)
        self._animator.timeout.connect(self._next_frame)
        self._revert = QTimer(self)
        self._revert.setSingleShot(True)
        self._revert.timeout.connect(lambda: self.set_state("idle"))
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._retone)
        self._show("idle")

    def set_state(self, state: str) -> None:
        self._state = state
        self._revert.stop()
        if state == "working":
            self._frame = 0
            self._show("work0")
            self._animator.start()
            return
        self._animator.stop()
        self._show(state)
        if state in HOLD_MS:
            self._revert.start(HOLD_MS[state])

    def _next_frame(self) -> None:
        self._frame = (self._frame + 1) % WORK_FRAMES
        self._show(f"work{self._frame}")

    def _show(self, glyph: str) -> None:
        self.icon.setIcon(self._glyph(glyph))

    def _glyph(self, glyph: str) -> QIcon:
        key = (self._tone, glyph)
        icon = self._cache.get(key)
        if icon is None:
            icon = QIcon()
            for size in SIZES:
                icon.addFile(str(paths.assets_dir() / "brand" / f"tray-{self._tone}-{glyph}-{size}.png"))
            self._cache[key] = icon
        return icon

    def _retone(self, *_args) -> None:
        tone = taskbar_tone()
        if tone != self._tone:
            self._tone = tone
            self.set_state(self._state)
