"""The file actions wheel: copy or move somewhere, copy the path, open a
terminal there, or park files on the floating shelf.

Nothing here ever deletes a file; *move* refuses to overwrite.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from . import i18n

#: (key, i18n key) in wheel order.
ACTIONS = [
    ("file.copy", "file.copy"),
    ("file.move", "file.move"),
    ("file.path", "file.path"),
    ("file.terminal", "file.terminal"),
    ("file.shelf", "file.shelf"),
]


def _unique(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem} {counter}{suffix}"
        counter += 1
    return target


def run(key: str, files, parent=None) -> str | None:
    """Run action *key*; returns a short confirmation to show, if any."""
    paths = [Path(f) for f in files if Path(f).exists()]
    if not paths:
        return None
    if key == "file.path":
        QApplication.clipboard().setText("\r\n".join(str(p) for p in paths))
        return i18n.tr("action.copied_path")
    if key == "file.terminal":
        folder = paths[0] if paths[0].is_dir() else paths[0].parent
        subprocess.Popen(["powershell.exe", "-NoLogo", "-NoExit"], cwd=str(folder),
                         creationflags=0x00000010)
        return None
    if key == "file.shelf":
        return None             # the tray parks them on the island's shelf (eshab/activity.py)
    if key in ("file.copy", "file.move"):
        destination = QFileDialog.getExistingDirectory(parent, i18n.tr("action.pick_folder"),
                                                       str(paths[0].parent))
        if not destination:
            return None
        folder = Path(destination)
        for path in paths:
            if key == "file.move" and (folder == path or path in folder.parents or folder == path.parent):
                continue
            target = _unique(folder, path.name)
            if key == "file.copy":
                if path.is_dir():
                    shutil.copytree(path, target)
                else:
                    shutil.copy2(path, target)
            else:
                shutil.move(str(path), str(target))
        message = "action.copied_to" if key == "file.copy" else "action.moved_to"
        return i18n.tr(message, name=folder.name or str(folder))
    return None


def show_shelf(files=()):
    """The only entry point that presents the new shelf island."""
    from .island import get_island
    island = get_island()
    island.add(files)
    return island
