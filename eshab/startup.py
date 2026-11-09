"""Start Eshab with Windows (per-user Run key, no admin rights needed)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("eshab")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Eshab"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    root = Path(__file__).resolve().parent.parent
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" "{root / "main.py"}"'


def enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE)
            return bool(value)
    except OSError:
        return False


def set_enabled(flag: bool) -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if flag:
                winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.warning("Could not change the Windows startup entry", exc_info=True)
        return False
