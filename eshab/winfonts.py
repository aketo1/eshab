"""The fonts installed on this PC: their measures, as Windows reports them."""
from __future__ import annotations

import os
import re
import struct
from collections import namedtuple
from pathlib import Path

#: A font's measures per em: Word's single line, ascent, descent, the
#: external leading in that line, and the average character width.
FontMetrics = namedtuple("FontMetrics", "line ascent descent gap average")

_FONT_FILES: dict | None = None
_FONT_INFO: dict = {}
_MEASURING: dict = {}


def font_files() -> dict:
    """Installed font families (lower case) and their files, from the registry."""
    global _FONT_FILES
    if _FONT_FILES is not None:
        return _FONT_FILES
    _FONT_FILES = {}
    try:
        import winreg
    except ImportError:
        return _FONT_FILES
    key = chr(92).join(("SOFTWARE", "Microsoft", "Windows NT", "CurrentVersion", "Fonts"))
    folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            handle = winreg.OpenKey(root, key)
        except OSError:
            continue
        with handle:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(handle, index)
                except OSError:
                    break
                index += 1
                path = Path(value) if os.path.isabs(str(value)) else folder / str(value)
                label = re.sub("[ ]*[(](TrueType|OpenType)[)]$", "", name)
                for family in label.split(" & "):
                    _FONT_FILES.setdefault(family.strip().lower(), path)
    return _FONT_FILES


def _tables(handle) -> dict:
    """Where each table of an open font file starts."""
    offset = 0
    if handle.read(4) == b"ttcf":
        handle.seek(12)
        offset = struct.unpack(">I", handle.read(4))[0]
    handle.seek(offset + 4)
    count = struct.unpack(">H", handle.read(2))[0]
    handle.seek(offset + 12)
    directory = handle.read(16 * count)
    return {directory[i:i + 4]: struct.unpack(">I", directory[i + 8:i + 12])[0] for i in range(0, 16 * count, 16)}


def _read_metrics(path: Path):
    """A font's :class:`FontMetrics`, the way Windows measures them: a single
    line is win ascent + descent + external leading."""
    try:
        with open(path, "rb") as handle:
            tables = _tables(handle)
            handle.seek(tables[b"head"] + 18)
            units = struct.unpack(">H", handle.read(2))[0]
            handle.seek(tables[b"hhea"] + 4)
            ascender, descender, gap = struct.unpack(">hhh", handle.read(6))
            handle.seek(tables[b"OS/2"] + 2)
            average = struct.unpack(">h", handle.read(2))[0]
            handle.seek(tables[b"OS/2"] + 74)
            win_ascent, win_descent = struct.unpack(">HH", handle.read(4))
    except (OSError, KeyError, struct.error):
        return None
    if not units:
        return None
    height = win_ascent + win_descent
    leading = max(0, gap - (height - (ascender - descender)))
    return FontMetrics((height + leading) / units, win_ascent / units, win_descent / units, leading / units,
                       max(average, 1) / units)


def font_info(family: str) -> FontMetrics:
    key = (family or "arial").lower()
    if key not in _FONT_INFO:
        path = font_files().get(key)
        info = _read_metrics(path) if path is not None else None
        if info is None and key != "arial":
            info = font_info("arial")         # what Edge falls back to
        _FONT_INFO[key] = info or FontMetrics(1.15, 0.905, 0.212, 0.033, 0.45)
    return _FONT_INFO[key]


def _measuring_font(family: str, bold: bool):
    key = ((family or "arial").lower(), bold)
    if key not in _MEASURING:
        files = font_files()
        path = (files.get(key[0] + " bold") if bold else None) or files.get(key[0]) or files.get("arial")
        font = None
        if path is not None:
            try:
                import pymupdf

                font = pymupdf.Font(fontfile=str(path))
            except Exception:
                font = None
        _MEASURING[key] = font
    return _MEASURING[key]


#: Arabic letters: the first of their presentation forms (alone, last, first,
#: middle, in that order), and how many forms they have.
_ARABIC_FORMS = {0x0621: (0xFE80, 1), 0x0622: (0xFE81, 2), 0x0623: (0xFE83, 2), 0x0624: (0xFE85, 2), 0x0625: (0xFE87, 2), 0x0626: (0xFE89, 4),
                 0x0627: (0xFE8D, 2), 0x0628: (0xFE8F, 4), 0x0629: (0xFE93, 2), 0x062A: (0xFE95, 4), 0x062B: (0xFE99, 4), 0x062C: (0xFE9D, 4),
                 0x062D: (0xFEA1, 4), 0x062E: (0xFEA5, 4), 0x062F: (0xFEA9, 2), 0x0630: (0xFEAB, 2), 0x0631: (0xFEAD, 2), 0x0632: (0xFEAF, 2),
                 0x0633: (0xFEB1, 4), 0x0634: (0xFEB5, 4), 0x0635: (0xFEB9, 4), 0x0636: (0xFEBD, 4), 0x0637: (0xFEC1, 4), 0x0638: (0xFEC5, 4),
                 0x0639: (0xFEC9, 4), 0x063A: (0xFECD, 4), 0x0641: (0xFED1, 4), 0x0642: (0xFED5, 4), 0x0643: (0xFED9, 4), 0x0644: (0xFEDD, 4),
                 0x0645: (0xFEE1, 4), 0x0646: (0xFEE5, 4), 0x0647: (0xFEE9, 4), 0x0648: (0xFEED, 2), 0x0649: (0xFEEF, 2), 0x064A: (0xFEF1, 4)}
_LAM_ALEF = {0x0622: 0xFEF5, 0x0623: 0xFEF7, 0x0625: 0xFEF9, 0x0627: 0xFEFB}


def _joined(text: str) -> list:
    """A string's characters with Arabic letters in the forms they join in."""
    out, index = [], 0
    codes = [ord(c) for c in text if not 0x064B <= ord(c) <= 0x065F]
    joins_back = False
    while index < len(codes):
        code = codes[index]
        form = _ARABIC_FORMS.get(code)
        if form is None:
            out.append(code)
            joins_back = False
            index += 1
            continue
        following = codes[index + 1] if index + 1 < len(codes) else None
        if code == 0x0644 and following in _LAM_ALEF:      # lam and alef are one letter
            out.append(_LAM_ALEF[following] + (1 if joins_back else 0))
            joins_back = False
            index += 2
            continue
        joins_on = form[1] == 4 and following in _ARABIC_FORMS
        shape = (3 if joins_on else 1) if joins_back else (2 if joins_on else 0)
        out.append(form[0] + min(shape, form[1] - 1))
        joins_back = joins_on
        index += 1
    return out


def left_bearing(text: str, family: str, bold: bool = False) -> float:
    """How far a string's first letter stands from where it starts, in ems."""
    font = _measuring_font(family, bold)
    path = font_files().get((family or "arial").lower())
    glyph = font.has_glyph(ord(text[0])) if font is not None and text else 0
    if not glyph or path is None:
        return 0.0
    try:
        with open(path, "rb") as handle:
            tables = _tables(handle)
            handle.seek(tables[b"head"] + 18)
            units = struct.unpack(">H", handle.read(2))[0]
            handle.seek(tables[b"hhea"] + 34)
            metrics = struct.unpack(">H", handle.read(2))[0]
            place = 4 * glyph + 2 if glyph < metrics else 4 * metrics + 2 * (glyph - metrics)
            handle.seek(tables[b"hmtx"] + place)
            return struct.unpack(">h", handle.read(2))[0] / max(units, 1)
    except (OSError, KeyError, struct.error):
        return 0.0


def text_width(text: str, family: str, size: float, bold: bool = False) -> float:
    """How wide a string prints, in points; Arabic is measured in its joined
    letters, which is close enough for laying out labels."""
    font = _measuring_font(family, bold)
    if font is None:
        return len(text) * font_info(family).average * size
    fallback = None
    total = 0.0
    for code in _joined(text):
        if font.has_glyph(code):
            total += font.glyph_advance(code)
            continue
        if fallback is None:
            fallback = _measuring_font("arial", bold) or font
        total += fallback.glyph_advance(code)
    return total * size
