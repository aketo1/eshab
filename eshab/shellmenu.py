"""«اسحب» in Explorer's right-click menu (per user, no admin rights).

A cascading entry on every file opens one of the three wheels under the
pointer for the selected files. Explorer starts ``Eshab --wheel <mode> <file>``
once per file; each forwards to the running Eshab, which gathers them into
one wheel. On Windows 11 the entry sits under «عرض المزيد من الخيارات»
(or Shift+right-click): the short menu only takes packaged apps.
"""
from __future__ import annotations

import logging

from . import i18n, startup

log = logging.getLogger("eshab")

ROOT = r"Software\Classes\*\shell\Eshab"
VERBS = (("1convert", "conversion", "wheel.convert"),
         ("2tools", "tools", "wheel.tools"),
         ("3actions", "actions", "wheel.actions"))


def _icon() -> str:
    program = startup.command().split('" ', 1)[0].strip('"')
    return f'"{program}",0'


def registered() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ROOT):
            return True
    except OSError:
        return False


def register() -> bool:
    try:
        import winreg

        def put(path: str, values: dict) -> None:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                for name, value in values.items():
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

        icon = _icon()
        put(ROOT, {"MUIVerb": i18n.tr("app.name"), "Icon": icon, "SubCommands": "",
                   "MultiSelectModel": "Player"})
        for name, mode, title in VERBS:
            verb = rf"{ROOT}\shell\{name}"
            put(verb, {"MUIVerb": i18n.tr(title), "MultiSelectModel": "Player"})
            put(rf"{verb}\command", {"": f'{startup.command()} --wheel {mode} "%1"'})
        return True
    except OSError:
        log.warning("Could not add Eshab to Explorer's menu", exc_info=True)
        return False


def unregister() -> bool:
    try:
        import winreg

        def drop(path: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                                    winreg.KEY_READ | winreg.KEY_WRITE) as key:
                    while True:
                        try:
                            child = winreg.EnumKey(key, 0)
                        except OSError:
                            break
                        drop(rf"{path}\{child}")
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass

        drop(ROOT)
        return True
    except OSError:
        log.warning("Could not remove Eshab from Explorer's menu", exc_info=True)
        return False


def sync() -> None:
    """Keep an existing entry pointing at this Eshab (moved, updated or relabelled)."""
    if registered():
        register()


def set_enabled(flag: bool) -> bool:
    return register() if flag else unregister()
