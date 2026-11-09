"""The user's own order of the wheel cards, and the cards they hid.

Settings keep, per wheel, the keys moved to the front (``wheelOrder``) and
the keys hidden (``wheelHidden``). A wheel shows the cards that fit the
dragged files in that order; hiding can never leave a wheel empty.
"""
from __future__ import annotations

from . import catalog, i18n, icons, settings

MODES = ("conversion", "tools", "actions")
TOOL_IDS = ("img.compress", "img.edit", "img.crop", "img.background", "img.annotate", "img.redact", "img.metadata",
            "img.collage", "img.pdf", "qr.read", "pdf.edit", "pdf.compress", "pdf.merge", "pdf.split", "pdf.qr",
            "pdf.metadata", "doc.compress", "txt.compress", "arc.extract", "vid.trim", "vid.compress", "vid.crop",
            "vid.split", "vid.join", "vid.speed", "vid.snapshots", "vid.removeaudio", "vid.redact", "vid.metadata",
            "gif.metadata", "aud.trim", "aud.compress", "aud.normalize", "aud.channels", "aud.bleep",
            "aud.visualizer", "aud.metadata")


def _all_keys(mode: str) -> list[str]:
    if mode == "actions":
        from .file_actions import ACTIONS

        return [key for key, _ in ACTIONS]
    if mode == "tools":
        return list(TOOL_IDS)
    keys: list[str] = []
    groups = [catalog.IMAGE_TARGETS, catalog.PDF_TARGETS, catalog.TXT_TARGETS,
              *catalog.DOC_CONVERSIONS.values(), *catalog.SUB_TARGETS.values(),
              catalog.AUDIO_TARGETS, catalog.VIDEO_TARGETS, catalog.ARCHIVE_TARGETS]
    for group in groups:
        for key in group:
            if key not in keys:
                keys.append(key)
    return keys


def _stored(name: str, mode: str) -> list[str]:
    value = settings.get(name) or {}
    items = value.get(mode, []) if isinstance(value, dict) else []
    return [str(k) for k in items if isinstance(k, str)]


def _store(name: str, mode: str, keys: list[str]) -> None:
    value = settings.get(name) or {}
    value = dict(value) if isinstance(value, dict) else {}
    value[mode] = keys
    settings.set(name, value)
    settings.save()


def arrange(items: list[dict], mode: str) -> list[dict]:
    """The wheel's cards in the user's order, without the hidden ones."""
    hidden = set(_stored("wheelHidden", mode))
    rank = {key: index for index, key in enumerate(_stored("wheelOrder", mode))}
    shown = [item for item in items if item["key"] not in hidden] or list(items)
    return sorted(shown, key=lambda item: rank.get(item["key"], len(rank)))


def _label(mode: str, key: str) -> str:
    if mode == "conversion":
        return i18n.tr("conv." + key)
    if mode == "tools":
        return i18n.tr("tool." + key)
    return i18n.tr(key)


def cards(mode: str) -> list[dict]:
    """Every card a wheel can show, in the user's order, for the settings list."""
    if mode not in MODES:
        return []
    hidden = set(_stored("wheelHidden", mode))
    items = [{"key": key, "label": _label(mode, key), "glyph": icons.icon_for(key) or "",
              "text": key.upper() if mode == "conversion" else "", "hidden": key in hidden}
             for key in _all_keys(mode)]
    rank = {key: index for index, key in enumerate(_stored("wheelOrder", mode))}
    return sorted(items, key=lambda item: rank.get(item["key"], len(rank)))


def move(mode: str, key: str, delta: int) -> None:
    order = [item["key"] for item in cards(mode)]
    if key not in order:
        return
    index = order.index(key)
    target = max(0, min(len(order) - 1, index + delta))
    order.insert(target, order.pop(index))
    _store("wheelOrder", mode, order)


def toggle(mode: str, key: str) -> None:
    hidden = _stored("wheelHidden", mode)
    if key in hidden:
        hidden.remove(key)
    else:
        hidden.append(key)
    _store("wheelHidden", mode, hidden)


def reset(mode: str) -> None:
    _store("wheelOrder", mode, [])
    _store("wheelHidden", mode, [])
