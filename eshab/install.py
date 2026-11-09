"""Installing and removing Eshab for one user (no admin rights).

The Setup (packaging/setup_stub.cs) unpacks Eshab into
%LOCALAPPDATA%\\Programs\\Eshab, then runs ``Eshab --setup-finish``: the
Start menu entry, an optional Desktop shortcut, the start-with-Windows entry,
Explorer's right-click menu, and the entry in Windows' installed apps whose
«إلغاء التثبيت» runs ``Eshab --uninstall``. Settings and recent files in
%APPDATA%\\Eshab stay when Eshab is removed.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from . import i18n, paths, shellmenu, startup

log = logging.getLogger("eshab")

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Eshab"
SHORTCUT_NAMES = ("اسحب.lnk", "Eshab.lnk")
CSIDL_PROGRAMS, CSIDL_DESKTOPDIRECTORY = 0x02, 0x10


def _folder(csidl: int) -> Path:
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    return Path(buffer.value)


def _program() -> Path:
    return Path(sys.executable).resolve()


def _shortcut(where: Path) -> None:
    program = _program()
    target = where / ("اسحب.lnk" if i18n.is_rtl() else "Eshab.lnk")
    try:
        import comtypes.client

        shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
        link = shell.CreateShortcut(str(target))
        link.TargetPath = str(program)
        link.WorkingDirectory = str(program.parent)
        link.IconLocation = f"{program},0"
        link.Description = i18n.tr("app.name")
        link.Save()
    except Exception:
        log.warning("Could not create the shortcut %s", target, exc_info=True)


def _folder_size_kb(folder: Path) -> int:
    total = 0
    for item in folder.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total // 1024


def _register_uninstall() -> None:
    import winreg

    program = _program()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name, value in (("DisplayName", f"{i18n.tr('app.name')} (Eshab)"),
                            ("DisplayVersion", paths.APP_VERSION),
                            ("Publisher", "Eshab"),
                            ("DisplayIcon", f"{program},0"),
                            ("InstallLocation", str(program.parent)),
                            ("UninstallString", f'"{program}" --uninstall')):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1),
                            ("EstimatedSize", _folder_size_kb(program.parent))):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def finish(arguments: list[str]) -> int:
    """After the Setup unpacked Eshab: register it with Windows."""
    try:
        _register_uninstall()
    except OSError:
        log.warning("Could not add Eshab to the installed apps", exc_info=True)
    _shortcut(_folder(CSIDL_PROGRAMS))
    if "--desktop" in arguments:
        _shortcut(_folder(CSIDL_DESKTOPDIRECTORY))
    if "--material" in arguments:
        index = arguments.index("--material")
        chosen = arguments[index + 1] if index + 1 < len(arguments) else ""
        if chosen in ("honey", "clear", "ink"):
            from . import settings

            settings.set("material", chosen)      # picked in the Setup by dipping the drop
            settings.save()
    startup.set_enabled("--startup" in arguments)
    shellmenu.set_enabled("--shellmenu" in arguments)
    return 0


def _ask(text: str) -> bool:
    MB_YESNO, MB_ICONQUESTION, MB_RTL = 0x04, 0x20, 0x00100000 | 0x00080000
    flags = MB_YESNO | MB_ICONQUESTION | (MB_RTL if i18n.is_rtl() else 0)
    return ctypes.windll.user32.MessageBoxW(None, text, i18n.tr("app.name"), flags) == 6


def _quit_running() -> None:
    try:
        from PySide6.QtCore import QCoreApplication

        from .requests import forward_request, parse_request

        app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # noqa: F841 - sockets need it
        forward_request(parse_request(["--quit"]), 1500)
        time.sleep(2.0)
    except Exception:
        log.warning("Could not ask the running Eshab to quit", exc_info=True)


def uninstall() -> int:
    if not _ask(i18n.tr("install.remove_ask")):
        return 0
    _quit_running()
    startup.set_enabled(False)
    shellmenu.unregister()
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    for folder in (_folder(CSIDL_PROGRAMS), _folder(CSIDL_DESKTOPDIRECTORY)):
        for name in SHORTCUT_NAMES:
            try:
                (folder / name).unlink()
            except OSError:
                pass
    # The program's own folder goes once this process has ended — only the
    # folder the Setup made, never a copy that lives somewhere else.
    home = _program().parent
    if home.name.lower() == "eshab" and (home / "_internal").is_dir() and (home / "Eshab.exe").is_file():
        subprocess.Popen(f'cmd.exe /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{home}"',
                         creationflags=0x08000000 | 0x00000008, close_fds=True)   # no window, detached
    return 0
