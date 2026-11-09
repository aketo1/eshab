"""Collision-safe sibling naming: cat.jpg, cat 2.jpg, cat 3.jpg ..."""

from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import re
import threading

_operation = ContextVar("eshab_output_operation", default=None)
_lock = threading.RLock()
_issued: set[Path] = set()
_edit_pattern = re.compile(r"^(.*?) - (?:تعديل|edit) (\d+) - .+$", re.IGNORECASE)


@contextmanager
def operation_scope(sources, descriptor):
    """Carry the operation's name into any background jobs it creates."""
    token = _operation.set((tuple(Path(p) for p in sources), str(descriptor)))
    try:
        yield
    finally:
        _operation.reset(token)


def edited_path(source: Path, descriptor: str, suffix: str | None = None,
                reserved: set[Path] | None = None, folder: Path | None = None) -> Path:
    """Original name + next edit number + operation, without overwriting.

    Numbering is shared by all operation types and formats for this original.
    Re-editing a generated copy continues the original's sequence.
    """
    from . import i18n

    source = Path(source)
    folder = Path(folder) if folder is not None else source.parent
    match = _edit_pattern.match(source.stem)
    base = match.group(1) if match else source.stem
    extension = source.suffix if suffix is None else suffix
    descriptor = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", descriptor)
    descriptor = re.sub(r"\s+", " ", descriptor).strip(" .-")[:65] or ("تعديل" if i18n.is_rtl() else "edited")
    word = "تعديل" if i18n.is_rtl() else "edit"
    with _lock:
        if len(_issued) > 4096:
            _issued.difference_update(p for p in tuple(_issued) if p.exists())
        number = int(match.group(2)) if match else 0
        candidates = list(folder.iterdir()) if folder.is_dir() else []
        candidates.extend(p for p in _issued if p.parent == folder)
        candidates.extend(p for p in (reserved or set()) if p.parent == folder)
        for candidate in candidates:
            parsed = _edit_pattern.match(candidate.stem if candidate.suffix else candidate.name)
            if parsed and parsed.group(1).casefold() == base.casefold():
                number = max(number, int(parsed.group(2)))
        while True:
            number += 1
            tail = f" - {word} {number} - {descriptor}{extension}"
            filename = base[:max(1, 245 - len(tail))] + tail
            output = folder / filename
            if not output.exists() and output not in _issued and output not in (reserved or set()):
                _issued.add(output)
                if reserved is not None:
                    reserved.add(output)
                return output


def unique_path(folder: Path, stem: str, suffix: str, reserved: set[Path] | None = None) -> Path:
    """Return a path inside *folder* that does not yet exist."""
    operation = _operation.get()
    if operation:
        sources, descriptor = operation
        source = next((p for p in sources if stem == p.stem or stem.startswith(p.stem + " ")), sources[0] if sources else folder / stem)
        extension = suffix if not suffix or suffix.startswith(".") else Path("file" + suffix).suffix
        return edited_path(source, descriptor, extension, reserved, folder)
    if reserved is None:
        reserved = set()
    suffix = suffix or ""
    candidate = folder / f"{stem}{suffix}"
    index = 2
    while candidate.exists() or candidate in reserved:
        candidate = folder / f"{stem} {index}{suffix}"
        index += 1
    reserved.add(candidate)
    return candidate


def tailored_name(source: Path, descriptor: str, suffix: str) -> str:
    """Descriptive sibling name such as 'Clip Cropped.mp4'."""
    base = source.stem
    if descriptor and descriptor.lower() not in base.lower():
        return f"{base} {descriptor}{suffix}"
    return f"{base}{suffix}"


def folder_name(source: Path, descriptor: str) -> str:
    operation = _operation.get()
    if operation:
        return edited_path(source, operation[1], "").name
    base = source.stem
    if descriptor:
        return f"{base} {descriptor}"
    return base


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
