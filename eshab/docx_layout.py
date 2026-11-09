"""Word documents laid out as print-faithful HTML, for Edge to turn into PDF.

The document is read as Word stores it, not through a simplified reading:
page size and margins per section, columns, styles with their inheritance
and theme fonts, each paragraph's alignment, indents, spacing, direction,
borders, shading, tab stops and list number (counted the way Word counts
them), each run's fonts (Word keeps a Latin and an Arabic font apart),
size, weight, colour and decoration, tables with their grid, merged cells,
borders, shading and table-style regions (header row, banding), pictures
at their size, crop and wrapping, shapes, charts and SmartArt (docx_drawing),
page and section breaks, footnotes, and headers and footers (any content,
live page numbers).

Line heights come from each font's own metrics, the way Word measures
them. The HTML is one plain flow; docx_pages.js then lays it out inside Edge
into Word's pages, line by line, with footnotes at the foot of their page and
each section's own header and footer. Measured against PDFs from Word itself,
lines and page breaks land where Word puts them.

Free, local and printer-free: no Office, no LibreOffice, nothing to install.
"""
from __future__ import annotations

import base64
import html
import io
import json
import math
import re
from collections import namedtuple
from pathlib import Path

from docx import Document
from lxml import etree

from .docx_drawing import Drawings
from .drawingml import A as _A, Palette, geometry, outline_points
from .winfonts import font_info

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
EMU_PER_PT = 12700.0
ARABIC = re.compile("[" + chr(0x0590) + "-" + chr(0x08FF) + chr(0xFB1D) + "-" + chr(0xFDFF)
                    + chr(0xFE70) + "-" + chr(0xFEFF) + "]")
#: Stand-ins for a page break and a tab inside a paragraph's HTML. Neither
#: character may occur in a Word document's text.
PAGE, TAB = chr(12), chr(11)
SPLIT = re.compile("([" + PAGE + TAB + "])")
#: Edge sets lines and borders on whole screen pixels (0.75pt), which adds
#: up over a page. The page is laid out this many times larger and the PDF
#: shrunk back after printing, so that grid becomes this much finer.
SCALE = 4
SCALE_META = "eshab-print-scale"
#: Lays the flow out into Word's pages, inside Edge, before it prints.
PAGES_SCRIPT = Path(__file__).with_name("docx_pages.js")
#: In Arabic text Word draws Latin digits, and the separators inside a number,
#: in the run's Latin font. Tags and entities are matched to step over them.
DIGITS = re.compile("<[^>]+>|&[a-zA-Z0-9#]+;|[0-9]+(?:[.,:/][0-9]+)*")
FALLBACK_FONTS = "Arial, 'Segoe UI', sans-serif"
#: Fonts whose glyphs Word (and Edge) find in the private use area: a
#: Symbol bullet is U+F0B7 drawn in Symbol.
SYMBOL_FONTS = ("symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings")
HIGHLIGHT = {"yellow": "#FFFF00", "green": "#00FF00", "cyan": "#00FFFF", "magenta": "#FF00FF", "blue": "#0000FF",
             "red": "#FF0000", "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000",
             "darkMagenta": "#800080", "darkRed": "#800000", "darkYellow": "#808000", "darkGray": "#808080",
             "lightGray": "#C0C0C0", "black": "#000000", "white": "#FFFFFF"}
BORDER_STYLES = {"single": "solid", "thick": "solid", "double": "double", "triple": "double", "dotted": "dotted",
                 "dashed": "dashed", "dashSmallGap": "dashed", "dotDash": "dashed", "dotDotDash": "dotted",
                 "thinThickSmallGap": "double", "thickThinSmallGap": "double", "thinThickMediumGap": "double",
                 "thickThinMediumGap": "double", "inset": "inset", "outset": "outset"}
UNDERLINES = {"double": "double", "dotted": "dotted", "dottedHeavy": "dotted", "dash": "dashed",
              "dashedHeavy": "dashed", "dashLong": "dashed", "wave": "wavy", "wavyHeavy": "wavy", "wavyDouble": "wavy"}
LEADERS = {"dot": ".", "hyphen": "-", "underscore": "_", "heavy": "_", "middleDot": "·"}
ABJAD = "أبجدهوزحطيكلمنسعفصقرشتثخذضظغ"
ALPHA = "أبتثجحخدذرزسشصضطظعغفقكلمنهوي"

Marker = namedtuple("Marker", "text ppr rpr suffix bullet")


class _Object(str):
    """A piece of a run that is a drawing, not text."""


def _w(el, name):
    return el.find(W + name) if el is not None else None


def _val(el, name="val"):
    return el.get(W + name) if el is not None else None


def _on(value) -> bool:
    return value is not None and value.lower() in ("1", "true", "on")


def _toggle(el):
    if el is None:
        return None
    value = el.get(W + "val")
    return value is None or _on(value)


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pt(twips) -> float:
    return _num(twips) / 20.0


def _hex(value):
    return "#" + value if value and re.fullmatch("[0-9A-Fa-f]{6}", value) else None


def _fill(shading):
    """A shading element's fill colour (RRGGBB), when it paints one."""
    if shading is None:
        return None
    if _hex(shading.get(W + "fill")):
        return shading.get(W + "fill")
    if shading.get(W + "val") == "solid" and _hex(shading.get(W + "color")):
        return shading.get(W + "color")
    return None


def _edge(element):
    """A border edge as (width pt, css style, colour); None when it is off."""
    kind = element.get(W + "val") or "single"
    if kind in ("nil", "none"):
        return None
    width = max(0.25, _num(element.get(W + "sz"), 4) / 8.0)
    style = BORDER_STYLES.get(kind, "solid")
    if style == "double":
        width = max(width * 3, 2.25)
    return width, style, _hex(element.get(W + "color")) or "#000000"


def _edge_css(edge, k: float = 1.0) -> str:
    return f"{edge[0] * k:.3f}pt {edge[1]} {edge[2]}" if edge else "none"


def _color(color, theme):
    if not color:
        return None
    value, theme_name = color
    if _hex(value):
        return "#" + value
    if theme_name and theme is not None and theme.color(theme_name):
        return "#" + theme.color(theme_name)
    return None


def _family_css(family: str) -> str:
    return "'" + family.replace("'", "").replace('"', "") + "', " + FALLBACK_FONTS


def _plain(fragment: str) -> str:
    return html.unescape(re.sub("<[^>]+>", "", fragment))


def _blank(fragment: str) -> bool:
    """True when a piece of a paragraph shows nothing: no text, picture or box."""
    return not _plain(fragment) and "<img" not in fragment and 'class="box"' not in fragment and "<svg" not in fragment


def _objects_of(p) -> tuple:
    """(holds objects, holds one in its lines, has text of its own): text and
    drawings inside a text box, and the fallback copies, are not the paragraph's."""
    objects = inline = False
    for node in p.iter(W + "drawing", W + "pict", W + "object"):
        if next(node.iterancestors(W + "txbxContent", MC + "Fallback"), None) is not None:
            continue
        objects = True
        if node.tag == W + "drawing":
            inline = inline or node.find(WP + "inline") is not None
        else:
            style = next((c.get("style") for c in node if c.get("style")), "") or ""
            inline = inline or "position:absolute" not in style.replace(" ", "").lower()
    text = any((t.text or "").strip() and next(t.iterancestors(W + "txbxContent"), None) is None for t in p.iter(W + "t"))
    return objects, inline, text


def _inline_height(p) -> float:
    """The tallest object standing in a paragraph's lines, in points."""
    tallest = 0.0
    for node in p.iter(WP + "inline"):
        if next(node.iterancestors(W + "txbxContent", MC + "Fallback"), None) is not None:
            continue
        extent, extra = node.find(WP + "extent"), node.find(WP + "effectExtent")
        height = _num(extent.get("cy")) / EMU_PER_PT if extent is not None else 0.0
        if extra is not None:
            height += (_num(extra.get("t")) + _num(extra.get("b"))) / EMU_PER_PT
        tallest = max(tallest, height)
    for node in p.iter(W + "pict", W + "object"):
        if next(node.iterancestors(W + "txbxContent", MC + "Fallback"), None) is not None:
            continue
        style = next((c.get("style") for c in node if c.get("style")), "") or ""
        if "position:absolute" in style.replace(" ", "").lower():
            continue
        found = re.search("height:([0-9.]+)(pt|in|px)?", style.replace(" ", ""))
        if found:
            tallest = max(tallest, _num(found.group(1)) * {"pt": 1.0, "in": 72.0, "px": 0.75, None: 0.75}[found.group(2)])
    return tallest


#: Content that only newer Word can show draws from its fallback here.
_FALLBACK_FOR = ("am3d", "aink", "wpi")


def _alternate(element):
    """The branch of an mc:AlternateContent to read."""
    for choice in element.findall(MC + "Choice"):
        if not any(name in _FALLBACK_FOR for name in (choice.get("Requires") or "").split()):
            return choice
    return element.find(MC + "Fallback")


def _color_map(settings) -> dict:
    """The document's map from theme slots to colours (bg1 -> lt1...)."""
    mapping = _w(settings, "clrSchemeMapping")
    if mapping is None:
        return {}
    colours = {"dark1": "dk1", "light1": "lt1", "dark2": "dk2", "light2": "lt2", "hyperlink": "hlink",
               "followedHyperlink": "folHlink"}
    slots = {"t1": "tx1", "t2": "tx2"}
    out = {}
    for key, value in mapping.attrib.items():
        slot = key.split("}")[-1]
        out[slots.get(slot, slot)] = colours.get(value, value)
    return out


def _sibling(element, step: int):
    """The paragraph or table after ``element`` (step 1) or before it (-1)."""
    node = element.getnext() if step > 0 else element.getprevious()
    while node is not None and node.tag not in (W + "p", W + "tbl", W + "sdt"):
        node = node.getnext() if step > 0 else node.getprevious()
    if node is not None and node.tag == W + "sdt":
        content = _w(node, "sdtContent")
        inner = [c for c in content if c.tag in (W + "p", W + "tbl")] if content is not None else []
        if inner:
            return inner[0] if step > 0 else inner[-1]
    return node


# -- properties ---------------------------------------------------------------------

RUN_TOGGLES = ("b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "vanish", "rtl", "cs")


def merge_rpr(props: dict, rpr) -> dict:
    if rpr is None:
        return props
    fonts = _w(rpr, "rFonts")
    if fonts is not None:
        for slot, themed in (("ascii", "asciiTheme"), ("hAnsi", "hAnsiTheme"), ("cs", "cstheme"),
                             ("eastAsia", "eastAsiaTheme")):
            if fonts.get(W + themed):              # a theme font wins over a named one
                props["font_" + slot] = "@" + fonts.get(W + themed)
            elif fonts.get(W + slot):
                props["font_" + slot] = fonts.get(W + slot)
    for key in RUN_TOGGLES:
        flag = _toggle(_w(rpr, key))
        if flag is not None:
            props[key] = flag
    for key in ("sz", "szCs", "highlight", "vertAlign", "u", "spacing", "position", "kern"):
        value = _val(_w(rpr, key))
        if value:
            props[key] = value
    color = _w(rpr, "color")
    if color is not None:
        props["color"] = (color.get(W + "val"), color.get(W + "themeColor"))
    fill = _fill(_w(rpr, "shd"))
    if fill:
        props["shd"] = fill
    return props


def merge_ppr(props: dict, ppr) -> dict:
    if ppr is None:
        return props
    for key in ("jc", "outlineLvl"):
        value = _val(_w(ppr, key))
        if value:
            props[key] = value
    for key in ("bidi", "keepNext", "keepLines", "pageBreakBefore", "contextualSpacing", "widowControl"):
        flag = _toggle(_w(ppr, key))
        if flag is not None:
            props[key] = flag
    indent = _w(ppr, "ind")
    if indent is not None:
        for key, names in (("start", ("start", "left")), ("end", ("end", "right"))):
            value = next((indent.get(W + n) for n in names if indent.get(W + n) is not None), None)
            if value is not None:
                props["ind_" + key] = _num(value)
        # A first-line indent and a hanging one replace each other.
        if indent.get(W + "hanging") is not None:
            props.pop("ind_firstLine", None)
            props["ind_hanging"] = _num(indent.get(W + "hanging"))
        elif indent.get(W + "firstLine") is not None:
            props.pop("ind_hanging", None)
            props["ind_firstLine"] = _num(indent.get(W + "firstLine"))
    spacing = _w(ppr, "spacing")
    if spacing is not None:
        for key in ("before", "after", "line", "lineRule", "beforeAutospacing", "afterAutospacing"):
            value = spacing.get(W + key)
            if value is not None:
                props["sp_" + key] = value
    fill = _fill(_w(ppr, "shd"))
    if fill:
        props["shd"] = fill
    borders = _w(ppr, "pBdr")
    if borders is not None:
        for side in ("top", "bottom", "left", "right"):
            edge = _w(borders, side)
            if edge is not None:
                props["bdr_" + side] = (_edge(edge), _num(edge.get(W + "space")))
    numbering = _w(ppr, "numPr")
    if numbering is not None:
        if _val(_w(numbering, "numId")) is not None:
            props["numId"] = _val(_w(numbering, "numId"))
        if _val(_w(numbering, "ilvl")) is not None:
            props["ilvl"] = int(_num(_val(_w(numbering, "ilvl")), 0))
    tabs = _w(ppr, "tabs")
    if tabs is not None:
        stops = dict(props.get("tabs", {}))
        for tab in tabs.findall(W + "tab"):
            position = _num(tab.get(W + "pos"))
            if tab.get(W + "val") == "clear":
                stops.pop(position, None)
            else:
                stops[position] = (tab.get(W + "val") or "left", tab.get(W + "leader"))
        props["tabs"] = stops
    return props


def _take_indents(ppr: dict, source: dict) -> None:
    """Indents (and tab stops) of ``source`` over those already in ``ppr``."""
    for key in ("ind_start", "ind_end"):
        if key in source:
            ppr[key] = source[key]
    if "ind_hanging" in source or "ind_firstLine" in source:
        ppr.pop("ind_hanging", None)
        ppr.pop("ind_firstLine", None)
        ppr.update({k: source[k] for k in ("ind_hanging", "ind_firstLine") if k in source})
    if "tabs" in source:
        ppr["tabs"] = {**ppr.get("tabs", {}), **source["tabs"]}


class Styles:
    def __init__(self, document):
        root = document.styles.element
        self.by_id = {s.get(W + "styleId"): s for s in root.findall(W + "style")}
        self.default_r: dict = {}
        self.default_p: dict = {}
        defaults = _w(root, "docDefaults")
        if defaults is not None:
            merge_rpr(self.default_r, _w(_w(defaults, "rPrDefault"), "rPr"))
            merge_ppr(self.default_p, _w(_w(defaults, "pPrDefault"), "pPr"))
        self.default_para = self._default("paragraph")
        self.default_table = self._default("table")

    def _default(self, kind):
        return next((sid for sid, s in self.by_id.items()
                     if s.get(W + "type") == kind and _on(s.get(W + "default"))), None)

    def chain(self, style_id):
        chain, seen = [], set()
        while style_id and style_id in self.by_id and style_id not in seen and len(chain) < 20:
            seen.add(style_id)
            style = self.by_id[style_id]
            chain.append(style)
            style_id = _val(_w(style, "basedOn"))
        return list(reversed(chain))

    def name(self, style_id) -> str:
        style = self.by_id.get(style_id)
        return (_val(_w(style, "name")) or "").lower() if style is not None else ""

    def paragraph(self, style_id, table=None):
        """Paragraph and run properties of a paragraph style, over the
        document defaults and, inside a table, the table style's."""
        ppr, rpr = dict(self.default_p), dict(self.default_r)
        if table is not None:
            ppr.update(table[0])
            rpr.update(table[1])
        for style in self.chain(style_id):
            merge_ppr(ppr, _w(style, "pPr"))
            merge_rpr(rpr, _w(style, "rPr"))
        if table is not None and style_id == self.default_para:
            ppr.update(table[0])       # Word lets a table style win over Normal
            rpr.update(table[1])
        return ppr, rpr

    def indents(self, style_id) -> dict:
        props: dict = {}
        for style in self.chain(style_id):
            merge_ppr(props, _w(style, "pPr"))
        return {k: v for k, v in props.items() if k.startswith("ind_") or k == "tabs"}

    def character(self, style_id, rpr: dict) -> dict:
        for style in self.chain(style_id):
            merge_rpr(rpr, _w(style, "rPr"))
        return rpr


def _table_borders(borders: dict, element) -> dict:
    if element is None:
        return borders
    for side in ("top", "bottom", "left", "right", "start", "end", "insideH", "insideV"):
        edge = _w(element, side)
        if edge is not None:
            borders[{"start": "left", "end": "right"}.get(side, side)] = _edge(edge)
    return borders


def _cell_margins(margins: dict, element) -> dict:
    if element is None:
        return margins
    for side in ("top", "bottom", "left", "right", "start", "end"):
        edge = _w(element, side)
        if edge is not None:
            margins[{"left": "start", "right": "end"}.get(side, side)] = _pt(edge.get(W + "w"))
    return margins


def _look(element) -> dict:
    bits = 0
    if element is not None and element.get(W + "val"):
        try:
            bits = int(element.get(W + "val"), 16)
        except ValueError:
            bits = 0
    look = {}
    for name, bit in (("firstRow", 0x20), ("lastRow", 0x40), ("firstColumn", 0x80), ("lastColumn", 0x100),
                      ("noHBand", 0x200), ("noVBand", 0x400)):
        value = element.get(W + name) if element is not None else None
        look[name] = _on(value) if value is not None else bool(bits & bit)
    return look


class _Region:
    """What a table style gives one region of a table (the whole table, the
    header row, a band...): paragraph and run properties, fill, borders."""

    def __init__(self):
        self.ppr, self.rpr, self.fill, self.borders = {}, {}, None, {}

    def absorb(self, ppr, rpr, tcpr):
        merge_ppr(self.ppr, ppr)
        merge_rpr(self.rpr, rpr)
        self.fill = _fill(_w(tcpr, "shd")) or self.fill
        _table_borders(self.borders, _w(tcpr, "tcBorders"))


class TableStyle:
    ORDER = ("wholeTable", "band1Vert", "band2Vert", "band1Horz", "band2Horz", "firstCol", "lastCol",
             "firstRow", "lastRow", "neCell", "nwCell", "seCell", "swCell")

    def __init__(self, styles: Styles, style_id):
        self.borders, self.margins = {}, {}
        self.base, self.regions = _Region(), {}
        self.row_band = self.col_band = 1
        for style in styles.chain(style_id or styles.default_table):
            tblpr = _w(style, "tblPr")
            _table_borders(self.borders, _w(tblpr, "tblBorders"))
            _cell_margins(self.margins, _w(tblpr, "tblCellMar"))
            self.row_band = max(1, int(_num(_val(_w(tblpr, "tblStyleRowBandSize")), self.row_band)))
            self.col_band = max(1, int(_num(_val(_w(tblpr, "tblStyleColBandSize")), self.col_band)))
            self.base.absorb(_w(style, "pPr"), _w(style, "rPr"), _w(style, "tcPr"))
            for conditional in style.findall(W + "tblStylePr"):
                region = self.regions.setdefault(conditional.get(W + "type"), _Region())
                region.absorb(_w(conditional, "pPr"), _w(conditional, "rPr"), _w(conditional, "tcPr"))

    def regions_for(self, row, rows, column, span, columns, look) -> list:
        names = {"wholeTable"}
        last_col = column + span >= columns
        if not look["noVBand"]:
            band = column - (1 if look["firstColumn"] else 0)
            if band >= 0 and not (look["lastColumn"] and last_col):
                names.add("band1Vert" if (band // self.col_band) % 2 == 0 else "band2Vert")
        if not look["noHBand"]:
            band = row - (1 if look["firstRow"] else 0)
            if band >= 0 and not (look["lastRow"] and row == rows - 1):
                names.add("band1Horz" if (band // self.row_band) % 2 == 0 else "band2Horz")
        first_r, last_r = look["firstRow"] and row == 0, look["lastRow"] and row == rows - 1
        first_c, last_c = look["firstColumn"] and column == 0, look["lastColumn"] and last_col
        for name, on in (("firstCol", first_c), ("lastCol", last_c), ("firstRow", first_r), ("lastRow", last_r),
                         ("nwCell", first_r and first_c), ("neCell", first_r and last_c),
                         ("swCell", last_r and first_c), ("seCell", last_r and last_c)):
            if on:
                names.add(name)
        return [self.base] + [self.regions[n] for n in self.ORDER if n in names and n in self.regions]


class Theme:
    def __init__(self, document):
        self.fonts, self.colors = {}, {}
        self.fills, self.lines, self.effects = [], [], None
        part = next((p for p in document.part.package.iter_parts() if p.content_type.endswith("theme+xml")), None)
        if part is None:
            return
        root = etree.fromstring(part.blob)
        for kind in ("major", "minor"):
            font = root.find(f".//{A}{kind}Font")
            if font is None:
                continue
            latin, cs = font.find(A + "latin"), font.find(A + "cs")
            arabic = next((f.get("typeface") for f in font.findall(A + "font") if f.get("script") == "Arab"), "")
            self.fonts[kind + "Latin"] = latin.get("typeface") if latin is not None else ""
            self.fonts[kind + "Bidi"] = cs.get("typeface") if cs is not None and cs.get("typeface") else arabic
        scheme = root.find(f".//{A}clrScheme")
        for child in (scheme if scheme is not None else []):
            srgb, system = child.find(A + "srgbClr"), child.find(A + "sysClr")
            name = child.tag.split("}")[1]
            if srgb is not None:
                self.colors[name] = srgb.get("val")
            elif system is not None:
                self.colors[name] = system.get("lastClr")
        looks = root.find(f".//{A}fmtScheme")
        if looks is not None:
            fills, lines = looks.find(A + "fillStyleLst"), looks.find(A + "lnStyleLst")
            self.fills = list(fills) if fills is not None else []
            self.lines = list(lines) if lines is not None else []
            effects = looks.find(A + "effectStyleLst")
            self.effects = list(effects) if effects is not None else None

    def font(self, name: str) -> str:
        kind = "major" if name.startswith("major") else "minor"
        return self.fonts.get(kind + ("Bidi" if name.endswith("Bidi") else "Latin"), "")

    def color(self, name: str):
        mapping = {"text1": "dk1", "background1": "lt1", "text2": "dk2", "background2": "lt2", "dark1": "dk1",
                   "light1": "lt1", "dark2": "dk2", "light2": "lt2", "hyperlink": "hlink",
                   "followedHyperlink": "folHlink"}
        return self.colors.get(mapping.get(name, name))


# -- numbering ----------------------------------------------------------------------

class Numbering:
    """List numbers as Word counts them: lists built on one definition carry
    on each other's numbers unless one of them restarts."""

    def __init__(self, document, styles: Styles):
        self.styles = styles
        self.abstract: dict = {}
        self.links: dict = {}
        self.nums: dict = {}
        self.counters: dict = {}
        self.started: set = set()
        try:
            root = document.part.numbering_part.element
        except (KeyError, NotImplementedError):
            return
        for abstract in root.findall(W + "abstractNum"):
            key = abstract.get(W + "abstractNumId")
            self.abstract[key] = {int(_num(l.get(W + "ilvl"), 0)): l for l in abstract.findall(W + "lvl")}
            if _val(_w(abstract, "numStyleLink")):
                self.links[key] = _val(_w(abstract, "numStyleLink"))
        for num in root.findall(W + "num"):
            overrides = {}
            for override in num.findall(W + "lvlOverride"):
                start = _val(_w(override, "startOverride"))
                overrides[int(_num(override.get(W + "ilvl"), 0))] = (
                    _w(override, "lvl"), int(_num(start, 1)) if start is not None else None)
            self.nums[num.get(W + "numId")] = (_val(_w(num, "abstractNumId")), overrides)

    def _abstract(self, num_id):
        abstract_id, overrides = self.nums.get(num_id, (None, {}))
        seen = set()
        while abstract_id in self.links and abstract_id not in seen:   # a list that follows a list style
            seen.add(abstract_id)
            style = self.styles.by_id.get(self.links[abstract_id])
            linked = _val(_w(_w(_w(style, "pPr"), "numPr"), "numId"))
            if linked not in self.nums:
                break
            abstract_id = self.nums[linked][0]
        return abstract_id, overrides

    def level(self, num_id, ilvl):
        abstract_id, overrides = self._abstract(num_id)
        override = overrides.get(ilvl)
        if override is not None and override[0] is not None:
            return override[0]
        return self.abstract.get(abstract_id, {}).get(ilvl)

    def marker(self, num_id, ilvl):
        level = self.level(num_id, ilvl)
        if level is None:
            return None
        abstract_id, overrides = self._abstract(num_id)
        counts = self.counters.setdefault(abstract_id, {})
        if num_id not in self.started:
            self.started.add(num_id)
            for index, (_, start) in overrides.items():
                if start is not None:
                    counts[index] = start - 1
        counts[ilvl] = counts.get(ilvl, int(_num(_val(_w(level, "start")), 1)) - 1) + 1
        for deeper in [k for k in counts if k > ilvl]:
            del counts[deeper]
        fmt = _val(_w(level, "numFmt")) or "decimal"
        text = _val(_w(level, "lvlText")) or ""
        rpr = merge_rpr({}, _w(level, "rPr"))
        if fmt == "bullet":
            symbols = rpr.get("font_ascii", "").lower() in SYMBOL_FONTS
            shown = "".join(chr(ord(c) + 0xF000) if symbols and ord(c) < 0xF000 else c for c in text)
        else:
            def number(match):
                index = int(match.group(1)) - 1
                other = self.level(num_id, index)
                value = counts.get(index, int(_num(_val(_w(other, "start")), 1)) if other is not None else 1)
                kind = (_val(_w(other, "numFmt")) if other is not None else None) or "decimal"
                if _toggle(_w(level, "isLgl")):
                    kind = "decimal"
                return _format_number(value, kind)
            shown = re.sub("%([1-9])", number, text)
        return Marker(shown, merge_ppr({}, _w(level, "pPr")), rpr, _val(_w(level, "suff")) or "tab",
                      fmt == "bullet")


def _format_number(value: int, fmt: str) -> str:
    if fmt in ("lowerLetter", "upperLetter"):
        letters = chr(ord("a") + (value - 1) % 26) * ((value - 1) // 26 + 1)   # a..z, aa..zz
        return letters.upper() if fmt == "upperLetter" else letters
    if fmt in ("lowerRoman", "upperRoman"):
        out = ""
        for amount, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                                (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
            while value >= amount:
                out += letters
                value -= amount
        return out.upper() if fmt == "upperRoman" else out
    if fmt == "arabicAbjad":
        return ABJAD[(value - 1) % len(ABJAD)]
    if fmt == "arabicAlpha":
        return ALPHA[(value - 1) % len(ALPHA)]
    if fmt == "hindiNumbers":
        return "".join(chr(0x0660 + int(d)) for d in str(value))
    if fmt == "decimalZero":
        return f"{value:02d}"
    if fmt == "decimalEnclosedCircle" and 1 <= value <= 20:
        return chr(0x2460 + value - 1)
    if fmt == "none":
        return ""
    return str(value)


# -- pictures -------------------------------------------------------------------------

def _browser_image(blob: bytes, kind: str):
    """(blob, type) Edge can show; Word's EMF, WMF and TIFF become PNG."""
    if not (re.search("emf|wmf|tif", kind or "") or blob[40:44] == b" EMF"
            or blob[:4] == bytes((0xD7, 0xCD, 0xC6, 0x9A))):
        return blob, kind
    try:
        from PIL import Image

        with Image.open(io.BytesIO(blob)) as image:
            if image.format in ("WMF", "EMF"):
                image.load(dpi=150)
            out = io.BytesIO()
            image.convert("RGBA").save(out, "PNG")
            return out.getvalue(), "image/png"
    except Exception:
        return None


def _live_field(instruction: str):
    """(field, number format) of a page-number field, which only the finished
    pages can fill in; None for any other field."""
    words = instruction.split()
    if not words or words[0].upper() not in ("PAGE", "NUMPAGES", "SECTIONPAGES"):
        return None
    switch = instruction.split(chr(92) + "*")
    return words[0].upper(), switch[1].split()[0] if len(switch) > 1 and switch[1].split() else ""


def _field_span(instruction: str, shown: str) -> str:
    field, style = _live_field(instruction)
    return (f'<span class="field" data-field="{field}" data-style="{html.escape(style, quote=True)}">'
            f"{html.escape(shown, quote=False)}</span>")


# -- the layout ----------------------------------------------------------------------

class Layout(Drawings):
    def __init__(self, path: Path):
        self.path = Path(path)
        self.document = Document(str(path))
        self.part = self.document.part
        self.styles = Styles(self.document)
        self.theme = Theme(self.document)
        self.numbering = Numbering(self.document, self.styles)
        settings = self.document.settings.element
        self.palette = Palette(self.theme.colors, _color_map(settings), self.theme.fills, self.theme.lines, self.theme.fonts,
                               self.theme.effects)
        self.default_tab = _num(_val(_w(settings, "defaultTabStop")), 720) or 720
        mode = next((c.get(W + "val") for c in settings.iter(W + "compatSetting")
                     if c.get(W + "name") == "compatibilityMode"), None)
        self.compat = int(_num(mode, 12))
        self.even_odd = bool(_toggle(_w(settings, "evenAndOddHeaders")))
        # Word uses the larger of two facing paragraph spaces, unless this says to add them.
        self.additive = bool(_toggle(_w(_w(settings, "compat"), "doNotUseHTMLParagraphAutoSpacing")))
        self.notes: dict = {}
        self.note_parts: dict = {}
        self.separator = None
        self._read_notes()
        self.footnotes: list = []
        self.endnotes: list = []
        self._now = self.part              # the part whose pictures and links are being read
        self._note_label = ""
        self._parts: dict = {}
        self._images: dict = {}
        self._prev_after = 0.0
        self._started = False
        self._after_break = False
        self._sides = (72.0, 72.0)
        self._field: list = []
        self._line = ("auto", None)
        self._mark = ("Arial", 11.0)
        self._tallest = self._mark
        self._para_left = 0.0
        self._floats: list = []             # what the text wraps around, held for the paragraph's start
        self._waiting_tables: list = []     # floating tables, for the paragraph after them
        self.k = 1.0
        self._page = (595.3, 841.9, 72.0, 72.0, 72.0, 72.0)    # width, height, top, right, bottom, left

    # -- document --------------------------------------------------------------------

    def html(self) -> str:
        body = self.document.element.body
        final = _w(body, "sectPr")
        sections, current = [], []
        for child in body:
            if child.tag == W + "sectPr":
                continue
            current.append(child)
            inner = _w(_w(child, "pPr"), "sectPr") if child.tag == W + "p" else None
            if inner is not None:
                sections.append((inner, current))
                current = []
        sections.append((final, current))
        geometry = self._geometry(final)
        self._sides = (geometry[5], geometry[3])
        largest = max(max(self._geometry(sect)[:2]) for sect, _ in sections)
        self.k = float(max(1, min(SCALE, int(14400 // max(largest, 1.0)))))   # PDF pages stop at 200 inches
        rules = [self._page_rule(final) + " }"]
        out = []
        for index, (sect, blocks) in enumerate(sections):
            self._page = self._geometry(sect)
            style = [f"padding:0 {self._u(self._page[3])} 0 {self._u(self._page[5])}"]
            if self._page != geometry:
                rules.append(self._page_rule(sect, f"s{index}") + " }")
                style.append(f"page:s{index}")
            if index and self._started and _val(_w(sect, "type")) != "continuous":
                style.append("break-before:page")
                self._prev_after = 0.0
                self._after_break = False
            cols = _w(sect, "cols")
            count = int(_num(_val(cols, "num"), 1)) if cols is not None else 1
            if count > 1:
                style.append(f"column-count:{count};column-gap:{self._u(_pt(_val(cols, 'space') or 720))}")
                if _on(_val(cols, "sep")):
                    style.append(f"column-rule:{self._u(0.75)} solid #000")
            out.append(f'<div class="section" style="{";".join(style)}">' + "".join(self._blocks(blocks)) + "</div>")
        out.append(self._notes_html())
        data = {"k": self.k, "evenOdd": self.even_odd, "sections": self._section_data(sections)}
        out.append(self._templates())
        out.append('<script type="application/json" id="eshab-pages">' + json.dumps(data) + "</script>")
        out.append("<script>" + PAGES_SCRIPT.read_text("utf-8") + "</script>")
        rtl = bool(_toggle(_w(final, "bidi"))) or self._mostly_arabic()
        title = html.escape(self.document.core_properties.title or self.path.stem)
        base = re.sub("([0-9.]+)pt", lambda m: self._u(float(m.group(1))), BASE_CSS)
        return ('<!doctype html><html dir="' + ("rtl" if rtl else "ltr") + '" lang="' + ("ar" if rtl else "en")
                + f'"><head><meta charset="utf-8"><meta name="{SCALE_META}" content="{int(self.k)}"><title>'
                + title + '</title><style id="eshab-flow">' + "".join(rules) + "</style><style>" + base
                + "</style></head><body>" + "".join(out) + "</body></html>")

    def _u(self, points: float) -> str:
        """A length for the page, which is laid out ``k`` times larger."""
        return f"{points * self.k:.3f}pt"

    def _blocks(self, elements, table=None):
        for child in elements:
            tag = child.tag
            if tag == W + "p":
                yield self.paragraph(child, table)
            elif tag == W + "tbl":
                position = _w(_w(child, "tblPr"), "tblpPr")
                follows = _sibling(child, 1)
                if position is not None and follows is not None and follows.tag == W + "p" and table is None:
                    made = self._floating_table(child, position)       # its cells are paragraphs too
                    self._waiting_tables.append(made)
                else:
                    yield self.table(child)
            elif tag == W + "sdt":
                content = _w(child, "sdtContent")
                if content is not None:
                    yield from self._blocks(content, table)
            elif tag == W + "customXml":
                yield from self._blocks(child, table)

    def _mostly_arabic(self) -> bool:
        text = "".join(t.text or "" for t in self.document.element.body.iter(W + "t"))
        return len(ARABIC.findall(text)) > len(re.findall("[A-Za-z]", text))

    @staticmethod
    def _geometry(sect):
        size, margin = _w(sect, "pgSz"), _w(sect, "pgMar")
        return (_pt(_val(size, "w") or 11906), _pt(_val(size, "h") or 16838),
                abs(_pt(_val(margin, "top") or 1440)), _pt(_val(margin, "right") or 1440),
                abs(_pt(_val(margin, "bottom") or 1440)),
                _pt(_val(margin, "left") or 1440) + _pt(_val(margin, "gutter")))

    def _page_rule(self, sect, name: str = "") -> str:
        width, height, top, _, bottom, _ = self._geometry(sect)
        # No side margins on the page: the sections pad themselves instead,
        # so a table or picture reaching into the margin (as Word lets them)
        # does not make Edge shrink the whole page to fit it.
        return (f"@page{' ' + name if name else ''} {{ size: {self._u(width)} {self._u(height)}; "
                f"margin: {self._u(top)} 0 {self._u(bottom)} 0;")

    # -- headers, footers and what the pages need to know --------------------------------

    def _part_id(self, rid):
        """A header or footer as a template id; each part is written once."""
        part = self.part.related_parts.get(rid)
        if part is None:
            return None
        key = str(part.partname)
        if key not in self._parts:
            self._parts[key] = (len(self._parts), part)
        return self._parts[key][0]

    def _templates(self) -> str:
        out = []
        for number, part in self._parts.values():
            root = etree.fromstring(part.blob)
            out.append(f'<template id="eshab-part-{number}">{self._rendered(root, part)}</template>')
        return "".join(out)

    def _section_data(self, sections) -> list:
        """What the page script needs of each section, in points at layout scale."""
        k = self.k
        inherited = {"hdr": {}, "ftr": {}}
        out = []
        for sect, _ in sections:
            width, height, top, right, bottom, left = self._geometry(sect)
            margin = _w(sect, "pgMar")
            for kind, tag in (("hdr", "header"), ("ftr", "footer")):
                for reference in (sect.findall(W + tag + "Reference") if sect is not None else []):
                    inherited[kind][_val(reference, "type") or "default"] = self._part_id(reference.get(R + "id"))
            numbers = _w(sect, "pgNumType")
            start = _val(numbers, "start")
            out.append({
                "w": round(width * k, 3), "h": round(height * k, 3),
                "top": round(top * k, 3), "right": round(right * k, 3),
                "bottom": round(bottom * k, 3), "left": round(left * k, 3),
                "header": round(_pt(_val(margin, "header") or 720) * k, 3),
                "footer": round(_pt(_val(margin, "footer") or 720) * k, 3),
                "fixedTop": _num(_val(margin, "top"), 1) < 0, "fixedBottom": _num(_val(margin, "bottom"), 1) < 0,
                "cols": self._columns_of(sect, width - left - right),
                "sep": _on(_val(_w(sect, "cols"), "sep")),
                "type": _val(_w(sect, "type")) or "nextPage",
                "titlePg": bool(_toggle(_w(sect, "titlePg"))),
                "bidi": bool(_toggle(_w(sect, "bidi"))),
                "start": int(_num(start)) if start is not None else None,
                "fmt": _val(numbers, "fmt"),
                "hdr": dict(inherited["hdr"]), "ftr": dict(inherited["ftr"]),
            })
        return out

    def _columns_of(self, sect, inner: float) -> list:
        """A section's columns as [{w, gap}], in points at layout scale."""
        cols = _w(sect, "cols")
        k = self.k
        count = max(1, int(_num(_val(cols, "num"), 1))) if cols is not None else 1
        listed = cols.findall(W + "col") if cols is not None else []
        if listed and _val(cols, "equalWidth") is not None and not _on(_val(cols, "equalWidth")):
            return [{"w": round(_pt(_val(col, "w")) * k, 3), "gap": round(_pt(_val(col, "space")) * k, 3)}
                    for col in listed]
        gap = _pt(_val(cols, "space") or 720)
        width = (inner - gap * (count - 1)) / count
        return [{"w": round(width * k, 3), "gap": round(gap * k, 3)} for _ in range(count)]

    # -- paragraphs --------------------------------------------------------------------

    def paragraph(self, p, table=None) -> str:
        ppr_el = _w(p, "pPr")
        style_id = _val(_w(ppr_el, "pStyle")) or self.styles.default_para
        ppr, base = self.styles.paragraph(style_id, table)
        own = merge_ppr({}, ppr_el)
        num_id = own.get("numId", ppr.get("numId"))
        marker = None
        if num_id and num_id != "0":
            marker = self.numbering.marker(num_id, own.get("ilvl", ppr.get("ilvl", 0)))
            if marker is not None:
                _take_indents(ppr, marker.ppr)
                if "numId" not in own:      # numbered through its style: the style's indents win
                    _take_indents(ppr, self.styles.indents(style_id))
        merge_ppr(ppr, ppr_el)
        mark = merge_rpr(dict(base), _w(ppr_el, "rPr"))
        rtl = bool(ppr.get("bidi"))
        self._field = [f for f in self._field if f[0] != "code"]
        rule = ppr.get("sp_lineRule") or "auto"
        objects, in_line, has_text = _objects_of(p)
        pictured = rule == "auto" and in_line and not has_text   # Word spaces a picture's line singly
        floating = objects and not in_line and not has_text      # only the empty line stays in the text
        self._line = (rule, None if pictured else ppr.get("sp_line"))
        self._mark = self._font_of(mark, bool(mark.get("rtl") or mark.get("cs")))
        self._tallest = self._mark
        self._para_left = (ppr.get("ind_end", 0.0) if rtl else ppr.get("ind_start", 0.0)) / 20.0
        self._floats = []
        if table is None:                       # a floating table rides on the paragraph after it
            self._floats, self._waiting_tables = list(self._waiting_tables), []
        parts = "".join(self._content(p, base)).split(PAGE)
        floats, self._floats = "".join(self._floats), []
        painted = bool(ppr.get("shd")) or any(ppr.get("bdr_" + side, (None,))[0]
                                              for side in ("top", "bottom", "left", "right"))
        lift = 0.0 if pictured or painted or floating else self._lift()
        lifted = f' data-lift="{self._u(-lift)}"' if lift else ""
        # A page break that ends a paragraph keeps the paragraph mark on the
        # page it ends, and the next page starts without any space before.
        ends_page = len(parts) > 1 and _blank(parts[-1])
        if ends_page:
            parts.pop()

        before, after = self._space(ppr, "before"), self._space(ppr, "after")
        if ppr.get("contextualSpacing"):
            if self._style_of(_sibling(p, -1)) == style_id:
                before = 0.0
            if self._style_of(_sibling(p, 1)) == style_id:
                after = 0.0
        break_before = bool(ppr.get("pageBreakBefore")) and self._started
        top, bottom = before, 0.0 if ends_page else after      # facing margins collapse to the larger, as in Word
        if self.additive:
            follows = _sibling(p, 1)
            joined = (follows is not None and follows.tag == W + "p" and _w(ppr_el, "sectPr") is None
                      and not ends_page)
            top = before if break_before else before + self._prev_after
            bottom = 0.0 if joined or ends_page else after
            self._prev_after = after if joined else 0.0
        if self._after_break or break_before:      # a page begun by a break starts with no space before
            top = 0.0
        self._after_break = ends_page
        self._started = True

        tag = self._tag(style_id, ppr)
        start = ppr.get("ind_start", 0.0)
        names = "p pictured" if pictured else "p"
        # The extra of a multiple goes below a picture, measured on the paragraph's own font.
        spare = (_num(ppr.get("sp_line"), 240) / 240.0 - 1) * self._line_pt(*self._mark) if pictured else 0.0
        # A picture shorter than the font's line stands on the baseline of a line of that font.
        low = ""
        if pictured:
            metrics = font_info(self._mark[0])
            single = metrics.line * self._mark[1]
            tallest = _inline_height(p)
            if tallest < single:
                below = metrics.descent * self._mark[1] if tallest + metrics.descent * self._mark[1] <= single else 0.0
                low = (f'<span class="strut" style="height:{self._u(single)}"></span>', f"--below:{self._u(below)}")
                names += " low"
        out = []
        for index, part in enumerate(parts):
            first, last = index == 0, index == len(parts) - 1
            lead, x = "", start
            if first:
                x = start - ppr.get("ind_hanging", 0.0) + ppr.get("ind_firstLine", 0.0)
                if marker is not None and marker.text:
                    lead, x = self._marker_html(marker, mark, ppr, rtl, x)
            body = self._line_html(part, ppr, rtl, x)
            if low and first:
                body += low[0]
            if floating and first:             # the empty line the paragraph still has, which makes way for floats
                body += f'<span class="strut" style="height:{self._u(self._line_pt(*self._mark))}"></span>'
            # An empty line still takes its height (and so does one whose
            # text all sits on tab stops).
            floor = self._line_pt(*self._mark) if _blank(body) or 'class="at"' in body else 0.0
            if not first:
                out.append('<div class="page-break"></div>')
            css = self._paragraph_css(ppr, rtl, top if first else 0.0, bottom if last else 0.0, first,
                                      break_before and first, floor, lift, max(0.0, spare))
            tabs = ""
            if TAB in part or 'class="marker tabbed"' in lead:
                tabs = " data-tabs='" + html.escape(json.dumps(self._tab_data(ppr)), quote=False) + "'"
            if low:
                css += ";" + low[1]
            out.append(f'<{tag} class="{names}" dir="{"rtl" if rtl else "ltr"}"{lifted}{tabs} style="{css}">'
                       f'{floats if first else ""}{lead}{body}</{tag}>')
        if ends_page:
            out.append('<div class="page-break"></div>')
        return "".join(out)

    def _style_of(self, element):
        if element is None or element.tag != W + "p":
            return None
        return _val(_w(_w(element, "pPr"), "pStyle")) or self.styles.default_para

    def _tag(self, style_id, ppr) -> str:
        outline = ppr.get("outlineLvl")
        if outline is not None and outline.isdigit() and int(outline) < 6:
            return f"h{int(outline) + 1}"
        match = re.fullmatch("heading ([1-6])", self.styles.name(style_id))
        return f"h{match.group(1)}" if match else "div"

    @staticmethod
    def _space(ppr: dict, which: str) -> float:
        if _on(ppr.get(f"sp_{which}Autospacing")):
            return 14.0
        return max(0.0, _pt(ppr.get(f"sp_{which}", 0)))

    def _lift(self) -> float:
        """How far below Word's baseline Edge sets a line's text: Edge splits
        the extra space of a multiple (1.15, 1.5...) above and below the
        text, Word puts the font's leading above and all the rest below."""
        rule, value = self._line
        if rule != "auto":
            return 0.0
        family, size = self._tallest
        metrics = font_info(family)
        return size * ((_num(value, 240) / 240.0 - 1) * metrics.line / 2 - metrics.gap / 2)

    def _paragraph_css(self, ppr, rtl, top, bottom, first, page_break, floor=0.0, lift=0.0, spare=0.0) -> str:
        css = []
        jc = ppr.get("jc")
        if jc == "center":
            css.append("text-align:center")
        elif jc in ("both", "lowKashida", "mediumKashida", "highKashida", "thaiDistribute"):
            css.append("text-align:justify")
        elif jc == "distribute":
            css.append("text-align:justify;text-align-last:justify")
        elif jc in ("right", "end"):            # in a right-to-left paragraph Word's right is its end
            css.append("text-align:end" if rtl or jc == "end" else "text-align:right")
        elif jc in ("left", "start"):
            css.append("text-align:start" if rtl or jc == "start" else "text-align:left")
        css.append(f"margin-top:{self._u(top)};margin-bottom:{self._u(bottom)}")
        start, end = ppr.get("ind_start", 0.0) / 20.0, ppr.get("ind_end", 0.0) / 20.0
        if start:
            css.append(f"margin-inline-start:{self._u(start)}")
        if end:
            css.append(f"margin-inline-end:{self._u(end)}")
        if first and ppr.get("ind_hanging"):
            css.append(f"text-indent:{self._u(-ppr['ind_hanging'] / 20.0)}")
        elif first and ppr.get("ind_firstLine"):
            css.append(f"text-indent:{self._u(ppr['ind_firstLine'] / 20.0)}")
        if ppr.get("shd"):
            css.append(f"background:#{ppr['shd']}")
        for side, prop in (("top", "top"), ("bottom", "bottom"), ("left", "inline-start"), ("right", "inline-end")):
            border = ppr.get("bdr_" + side)
            if border and border[0]:
                css.append(f"border-{prop}:{_edge_css(border[0], self.k)};padding-{prop}:{self._u(border[1])}")
        if lift:
            css.append(f"top:{self._u(-lift)}")
        if page_break:
            css.append("break-before:page")
        if ppr.get("keepNext"):
            css.append("break-after:avoid")
        if ppr.get("keepLines"):
            css.append("break-inside:avoid")
        if ppr.get("widowControl") is False:
            css.append("orphans:1;widows:1")
        if floor:
            css.append(f"min-height:{self._u(floor)}")
        if spare:
            css.append(f"padding-bottom:{self._u(spare)}")
        # A line is as tall as the runs on it: the paragraph itself adds nothing.
        family, size = self._mark
        css.append(f"font-family:{_family_css(family)};font-size:{self._u(size)};line-height:0")
        return ";".join(css)

    def _line_pt(self, family: str, size: float) -> float:
        """A line's height in points, as Word spaces lines of this font."""
        rule, value = self._line
        factor = font_info(family).line
        if value is not None and rule == "exact":
            return abs(_pt(value))
        if value is not None and rule == "atLeast":
            return max(_pt(value), factor * size)
        return _num(value, 240) / 240.0 * factor * size

    def _line_height(self, family: str, size: float) -> str:
        rule, value = self._line
        if value is not None and rule in ("exact", "atLeast"):
            return self._u(self._line_pt(family, size))
        return f"{_num(value, 240) / 240.0 * font_info(family).line:.4f}"

    def _marker_html(self, marker, mark, ppr, rtl, x):
        rpr = dict(mark)
        rpr.update(marker.rpr)
        complex_script = False if marker.bullet else bool(rpr.get("rtl") or rpr.get("cs") or ARABIC.search(marker.text))
        css = self._run_css(rpr, marker.text, complex_script=complex_script)
        css += ";line-height:" + self._marker_line(*self._font_of(rpr, complex_script))
        text = html.escape(marker.text)
        if marker.suffix == "space":
            return f'<span class="marker" style="{css}">{text} </span>', x + self._estimate(marker.text + " ")
        if marker.suffix == "nothing":
            return f'<span class="marker" style="{css}">{text}</span>', x + self._estimate(marker.text)
        stop = self._next_stop(x + self._estimate(marker.text), ppr)[0]
        return f'<span class="marker tabbed" style="{css};min-width:{self._u((stop - x) / 20.0)}">{text}</span>', stop

    def _marker_line(self, family: str, size: float) -> str:
        """A list number makes its line taller only by what its font rises
        above the text's: the rest of the line stays as the text sets it."""
        rule, value = self._line
        if rule != "auto":
            return "0"
        ours, text_font = font_info(family), self._tallest
        text, text_size = font_info(text_font[0]), text_font[1]
        rise = (ours.ascent + ours.gap) * size - (text.ascent + text.gap) * text_size
        if rise <= 0:
            return "0"
        line = _num(value, 240) / 240.0 * text.line * text_size
        top = (line + (text.ascent - text.descent) * text_size) / 2.0 + rise
        return self._u(2.0 * top - (ours.ascent - ours.descent) * size)

    def _tab_data(self, ppr: dict) -> dict:
        """Tab stops for the page script: CSS pixels at layout scale, from the
        paragraph's start edge."""
        scale = self.k * 96.0 / 72.0 / 20.0
        start = ppr.get("ind_start", 0.0)
        return {"stops": [[round((position - start) * scale, 2), kind, LEADERS.get(leader)]
                          for position, kind, leader in self._stops(ppr)],
                "step": round(self.default_tab * scale, 2), "indent": round(start * scale, 2),
                "line": self._line_height(*self._mark)}

    # -- tabs ----------------------------------------------------------------------------

    def _estimate(self, fragment: str) -> float:
        """Rough width of some text, in twips (only used to pick tab stops)."""
        family, size = self._mark
        return len(_plain(fragment)) * font_info(family).average * size * 20.0

    def _stops(self, ppr):
        stops = []
        for position, (kind, leader) in ppr.get("tabs", {}).items():
            if kind not in ("clear", "bar", "num"):
                stops.append((position, {"left": "start", "right": "end"}.get(kind, kind), leader))
        if ppr.get("ind_hanging"):
            stops.append((ppr.get("ind_start", 0.0), "start", None))     # Word stops at a hanging indent
        return sorted(stops, key=lambda stop: stop[0])

    def _next_stop(self, x: float, ppr):
        for stop in self._stops(ppr):
            if stop[0] > x + 10:
                return stop
        return (math.floor(x / self.default_tab) + 1) * self.default_tab, "start", None

    def _line_html(self, part: str, ppr, rtl: bool, x: float) -> str:
        """A line with tabs: each piece starts, ends or centres on the stop
        Word would move it to."""
        if TAB not in part:
            return part
        segments = part.split(TAB)
        start = ppr.get("ind_start", 0.0)
        flowing = "<br>" in part or ppr.get("jc") in ("center", "both", "distribute")
        out, cursor = [segments[0]], x + self._estimate(segments[0])
        for segment in segments[1:]:
            position, kind, leader = self._next_stop(cursor, ppr)
            width = self._estimate(segment)
            if flowing:
                out.append(f'<span class="tab" style="width:{self._u(max(0.0, position - cursor) / 20.0)}"></span>')
                out.append(segment)
                cursor = max(position, cursor) + width
                continue
            shift = {"end": 100, "decimal": 100, "center": 50}.get(kind, 0)
            begin = position - width * shift / 100.0
            if leader in LEADERS and begin > cursor:
                out.append(f'<span class="leader" style="inset-inline-start:{self._u((cursor - start) / 20.0)};'
                           f'width:{self._u((begin - cursor) / 20.0)};'
                           f'line-height:{self._line_height(*self._mark)}">{LEADERS[leader] * 300}</span>')
            css = f"inset-inline-start:{self._u((position - start) / 20.0)}"
            if shift:
                css += f";transform:translateX({shift if rtl else -shift}%)"
            out.append(f'<span class="at" style="{css}">{segment}</span>')
            cursor = begin + width
        return "".join(out)

    # -- runs --------------------------------------------------------------------------

    def _content(self, element, base: dict):
        for child in element:
            tag = child.tag
            if tag == W + "r":
                yield self._run(child, base)
            elif tag == W + "hyperlink":
                inner = "".join(self._content(child, base))
                href = html.escape(self._href(child), quote=True)
                # Each piece between tabs and page breaks gets its own link.
                yield "".join(c if c in (PAGE, TAB) or not href else f'<a href="{href}">{c}</a>'
                              for c in SPLIT.split(inner) if c)
            elif tag == W + "fldSimple":
                instruction = child.get(W + "instr") or ""
                if _live_field(instruction):
                    self._field.append(["live", instruction])
                    yield from self._content(child, base)
                    self._field.pop()
                else:
                    yield from self._content(child, base)
            elif tag in (W + "ins", W + "moveTo", W + "smartTag", W + "customXml", W + "dir", W + "bdo"):
                yield from self._content(child, base)
            elif tag == W + "sdt":
                content = _w(child, "sdtContent")
                if content is not None:
                    yield from self._content(content, base)
            elif tag == W + "bookmarkStart":
                name = child.get(W + "name") or ""
                if name and name != "_GoBack":
                    yield f'<a id="{html.escape(name, quote=True)}"></a>'
            elif tag == MC + "AlternateContent":
                choice = _alternate(child)
                if choice is not None:
                    yield from self._content(choice, base)
            elif tag in (M + "oMath", M + "oMathPara"):
                yield self._math(child, base)

    def _href(self, link) -> str:
        if link.get(R + "id"):
            rel = self._now.rels.get(link.get(R + "id"))
            if rel is not None and rel.is_external:
                return rel.target_ref
        if link.get(W + "anchor"):
            return "#" + link.get(W + "anchor")
        return ""

    def _run(self, r, base: dict) -> str:
        rpr_el = _w(r, "rPr")
        rpr = dict(base)
        if _val(_w(rpr_el, "rStyle")):
            self.styles.character(_val(_w(rpr_el, "rStyle")), rpr)
        merge_rpr(rpr, rpr_el)
        pieces: list = []
        self._pieces(r, pieces)
        if rpr.get("vanish") or not pieces:       # hidden text is not printed
            return ""
        plain = _plain("".join(piece for piece in pieces if not isinstance(piece, _Object)))
        css = self._run_css(rpr, plain)
        complex_text = rpr.get("rtl") or rpr.get("cs") or ARABIC.search(plain)
        text = "".join(piece if isinstance(piece, _Object) or not complex_text else self._latin_digits(piece, rpr)
                       for piece in pieces)
        return "".join(c if c in (PAGE, TAB) else f'<span style="{css}">{c}</span>' for c in SPLIT.split(text) if c)

    def _latin_digits(self, text: str, rpr: dict) -> str:
        latin = self._font_of(rpr, False)[0]
        family, size = self._font_of(rpr, True)
        if latin.lower() == family.lower():
            return text
        css = f"font-family:{_family_css(latin)};line-height:{self._line_height(latin, size)}"

        def wrap(match):
            piece = match.group(0)
            return piece if piece[0] in "<&" else f'<span style="{css}">{piece}</span>'
        return DIGITS.sub(wrap, text)

    def _pieces(self, container, out: list) -> None:
        for child in container:
            tag = child.tag
            if tag == W + "fldChar":
                kind = child.get(W + "fldCharType")
                if kind == "begin":
                    self._field.append(["code", ""])
                elif kind == "separate" and self._field:
                    self._field[-1][0] = "live" if _live_field(self._field[-1][1]) else "result"
                elif kind == "end" and self._field:
                    state, code = self._field.pop()
                    if state == "code" and _live_field(code):
                        out.append(_field_span(code, "1"))
                continue
            if self._field and self._field[-1][0] == "code":
                if tag == W + "instrText":
                    self._field[-1][1] += child.text or ""
                continue
            if any(state == "code" for state, _ in self._field):
                continue                              # a field's code; its result follows
            live = next((f for f in reversed(self._field) if f[0] in ("live", "shown")), None)
            if live is not None:                      # a page number: the finished pages fill it in
                if tag == W + "t" and live[0] == "live":
                    live[0] = "shown"
                    out.append(_field_span(live[1], child.text or "1"))
                continue
            if tag == W + "t":
                out.append(html.escape(child.text or "", quote=False).replace(chr(9), TAB))
            elif tag in (W + "tab", W + "ptab"):
                out.append(TAB)
            elif tag in (W + "br", W + "cr"):
                out.append(PAGE if child.get(W + "type") == "page" else "<br>")
            elif tag == W + "noBreakHyphen":
                out.append("&#8209;")
            elif tag == W + "softHyphen":
                out.append("&shy;")
            elif tag == W + "sym":
                out.append(self._symbol(child))
            elif tag == W + "drawing":
                out.append(_Object(self._drawing(child)))
            elif tag in (W + "pict", W + "object"):
                out.append(_Object(self._vml(child)))
            elif tag in (W + "footnoteReference", W + "endnoteReference"):
                out.append(self._note_mark(tag[len(W):-len("Reference")], child.get(W + "id")))
            elif tag in (W + "footnoteRef", W + "endnoteRef"):
                out.append(html.escape(self._note_label))
            elif tag in (W + "separator", W + "continuationSeparator"):
                out.append('<span class="sep-line"></span>')
            elif tag == MC + "AlternateContent":
                choice = _alternate(child)
                if choice is not None:
                    self._pieces(choice, out)

    @staticmethod
    def _symbol(sym) -> str:
        code = int(sym.get(W + "char") or "20", 16)
        font = sym.get(W + "font") or ""
        if code < 0xF000 and font.lower() in SYMBOL_FONTS:
            code += 0xF000
        return '<span style="font-family:' + _family_css(font) + '">' + html.escape(chr(code)) + "</span>"

    def _math(self, element, base: dict) -> str:
        text = "".join(t.text or "" for t in element.iter(M + "t"))
        if not text:
            return ""
        css = self._run_css(dict(base), text) + ";font-family:'Cambria Math', serif"
        return f'<span style="{css}">{html.escape(text)}</span>'

    def _font_of(self, rpr: dict, complex_script: bool):
        if complex_script:
            name, half = rpr.get("font_cs"), rpr.get("szCs")
        else:
            name, half = rpr.get("font_ascii") or rpr.get("font_hAnsi"), rpr.get("sz")
        if name and name.startswith("@"):
            name = self.theme.font(name[1:])
        return name or "Times New Roman", _num(half, 20) / 2.0

    def _run_css(self, rpr: dict, text: str, complex_script=None, line: bool = True) -> str:
        if complex_script is None:
            complex_script = bool(rpr.get("rtl") or rpr.get("cs") or ARABIC.search(text))
        family, size = self._font_of(rpr, complex_script)
        bold = rpr.get("bCs") if complex_script else rpr.get("b")
        italic = rpr.get("iCs") if complex_script else rpr.get("i")
        shifted = rpr.get("vertAlign") in ("superscript", "subscript")
        # Word sets raised and lowered text at 65%, to the half point below.
        shown = math.floor(size * 0.65 * 2) / 2 if shifted else size
        css = [f"font-family:{_family_css(family)}", f"font-size:{self._u(shown)}"]
        if shifted:
            shift = 0.32 * size if rpr["vertAlign"] == "superscript" else -0.09 * size
            css.append(f"line-height:0;vertical-align:{self._u(shift)}")
        elif line:
            css.append("line-height:" + self._line_height(family, size))
            if size > self._tallest[1]:
                self._tallest = (family, size)
        if rpr.get("position") and not shifted:
            css.append(f"vertical-align:{self._u(_num(rpr['position']) / 2.0)}")
        if bold:
            css.append("font-weight:bold")
        if italic:
            css.append("font-style:italic")
        if not complex_script and not (rpr.get("kern") and size * 2 >= _num(rpr["kern"])):
            css.append("font-kerning:none;font-variant-ligatures:none")    # Word's defaults for Latin text
        decorations = []
        if rpr.get("u") and rpr["u"] != "none":
            decorations.append("underline")
        if rpr.get("strike") or rpr.get("dstrike"):
            decorations.append("line-through")
        if decorations:
            css.append("text-decoration-line:" + " ".join(decorations) + ";text-decoration-skip-ink:none")
            style = UNDERLINES.get(rpr.get("u") or "") or ("double" if rpr.get("dstrike") else "")
            if style:
                css.append("text-decoration-style:" + style)
        color = _color(rpr.get("color"), self.theme)
        if color:
            css.append("color:" + color)
        if line and rpr.get("highlight") in HIGHLIGHT:
            css.append("background:" + HIGHLIGHT[rpr["highlight"]])
        elif line and rpr.get("shd"):
            css.append("background:#" + rpr["shd"])
        if rpr.get("caps"):
            css.append("text-transform:uppercase")
        elif rpr.get("smallCaps"):
            css.append("font-variant-caps:small-caps")
        if rpr.get("spacing"):
            amount = _pt(rpr["spacing"])
            if not complex_script:
                css.append(f"letter-spacing:{self._u(amount)}")
            elif text.count(" "):             # spacing Arabic letters apart would break their joins:
                gaps = text.count(" ")        # the same width goes into the gaps between words
                css.append(f"word-spacing:{self._u(amount * (len(text) - gaps) / gaps)}")
        return ";".join(css)

    # -- pictures and text boxes ---------------------------------------------------------

    def _image_uri(self, rid):
        part = self._now
        key = (str(part.partname), rid)
        if key not in self._images:
            target = part.related_parts.get(rid) if rid else None
            converted = _browser_image(target.blob, target.content_type) if target is not None else None
            self._images[key] = (f"data:{converted[1]};base64," + base64.b64encode(converted[0]).decode("ascii")
                                 if converted else None)
        return self._images[key]

    def _picture(self, blip, holder, width, height) -> str:
        uri = self._image_uri(blip.get(R + "embed") or blip.get(R + "link"))
        if not uri:
            return ""
        described = holder.find(WP + "docPr")
        alt = html.escape((described.get("descr") or described.get("title") or "") if described is not None else "",
                          quote=True)
        transform = []
        xfrm = next(holder.iter(A + "xfrm"), None)
        if xfrm is not None:
            if _num(xfrm.get("rot")):
                transform.append(f"rotate({_num(xfrm.get('rot')) / 60000.0:.2f}deg)")
            if _on(xfrm.get("flipH")):
                transform.append("scaleX(-1)")
            if _on(xfrm.get("flipV")):
                transform.append("scaleY(-1)")
        turn = f";transform:{' '.join(transform)}" if transform else ""
        crop = next(holder.iter(A + "srcRect"), None)
        if crop is not None and any(crop.get(k) for k in ("l", "t", "r", "b")):
            left, top, right, bottom = (_num(crop.get(k)) / 100000.0 for k in ("l", "t", "r", "b"))
            full_w, full_h = width / max(0.01, 1 - left - right), height / max(0.01, 1 - top - bottom)
            return (f'<span class="crop" style="width:{self._u(width)};height:{self._u(height)}{turn}">'
                    f'<img alt="{alt}" src="{uri}" style="width:{self._u(full_w)};height:{self._u(full_h)};'
                    f'margin-left:{self._u(-left * full_w)};margin-top:{self._u(-top * full_h)}"></span>')
        return f'<img alt="{alt}" src="{uri}" style="width:{self._u(width)};height:{self._u(height)}{turn}">'

    def _rendered(self, elements, part, label: str = "", table=None) -> str:
        """Blocks of another story (a text box, header, footer or note)."""
        saved = (self._prev_after, self._after_break, self._started, self._field, self._line, self._mark,
                 self._tallest, self._para_left, self._now, self._note_label, self._floats)
        self._prev_after, self._after_break, self._started, self._field = 0.0, False, True, []
        self._now, self._note_label = part, label
        inner = "".join(self._blocks(elements, table))
        (self._prev_after, self._after_break, self._started, self._field, self._line, self._mark,
         self._tallest, self._para_left, self._now, self._note_label, self._floats) = saved
        return inner

    def _offset(self, place: tuple, size: float, horizontal: bool) -> float:
        """Where an anchored object sits: from the column's left edge, or
        from the top of its paragraph. ``place`` is (measured from, alignment, offset)."""
        width, height, top, right, bottom, left = self._page
        relative, align, offset = place
        if horizontal:
            frames = {"page": (-left, width), "leftMargin": (-left, left),
                      "rightMargin": (width - left - right, right)}
            origin, extent = frames.get(relative, (0.0, width - left - right))
        else:
            frames = {"page": (-top, height), "topMargin": (-top, top), "margin": (0.0, height - top - bottom),
                      "bottomMargin": (height - top - bottom, bottom)}
            origin, extent = frames.get(relative, (0.0, 0.0))
        if align in ("left", "top", "inside"):
            return origin
        if align == "center":
            return origin + (extent - size) / 2.0
        if align in ("right", "bottom", "outside"):
            return origin + extent - size
        return origin + offset

    @staticmethod
    def _place_of(position) -> tuple:
        if position is None:
            return "", "", 0.0
        return (position.get("relativeFrom") or "", position.findtext(WP + "align") or "",
                _num(position.findtext(WP + "posOffset")) / EMU_PER_PT)

    def _anchored(self, holder, content: str, width: float, height: float) -> str:
        wrap_el = next((c for c in holder if c.tag.startswith(WP + "wrap")), None)
        wrap = wrap_el.tag[len(WP):] if wrap_el is not None else "wrapNone"
        gap = {k: _num(holder.get(k)) / EMU_PER_PT for k in ("distT", "distB", "distL", "distR")}
        side = (wrap_el.get("wrapText") if wrap_el is not None else None) or "bothSides"
        outline = self._wrap_outline(holder, wrap_el, width, height) if wrap in ("wrapTight", "wrapThrough") else None
        return self._placed(content, width, height, wrap, gap, self._place_of(holder.find(WP + "positionH")),
                            self._place_of(holder.find(WP + "positionV")), _on(holder.get("behindDoc")), side, outline)

    @staticmethod
    def _wrap_outline(holder, wrap_el, width: float, height: float):
        """The outline text runs along in a tight wrap: the polygon the file keeps (Word
        uses it as it is), or else the shape's own outline."""
        polygon = wrap_el.find(WP + "wrapPolygon") if wrap_el is not None else None
        if polygon is not None:
            points = [(_num(node.get("x")) * width / 21600.0, _num(node.get("y")) * height / 21600.0)
                      for node in polygon if node.tag in (WP + "start", WP + "lineTo")]
            if len(points) > 2:
                return points
        shape = next(holder.iter("{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}spPr"), None)
        if shape is not None:
            xfrm = shape.find(_A + "xfrm")
            polygons = outline_points(geometry(shape, width, height))
            turn = math.radians(_num(xfrm.get("rot")) / 60000.0) if xfrm is not None else 0.0
            flip_h = xfrm is not None and xfrm.get("flipH") in ("1", "true")
            flip_v = xfrm is not None and xfrm.get("flipV") in ("1", "true")
            points = []
            for polygon in polygons:
                for x, y in polygon:
                    x, y = (width - x if flip_h else x), (height - y if flip_v else y)
                    if turn:
                        dx, dy = x - width / 2, y - height / 2
                        x = width / 2 + dx * math.cos(turn) - dy * math.sin(turn)
                        y = height / 2 + dx * math.sin(turn) + dy * math.cos(turn)
                    points.append((x, y))
            return points or None
        return None

    def _placed(self, content: str, width: float, height: float, wrap: str, gap: dict, across: tuple, down: tuple,
                behind_text: bool, side: str = "bothSides", outline=None) -> str:
        """Something anchored: standing in the text, floating beside it, or
        over or behind it, where the pages put it by what Word measures it from."""
        x, y = self._offset(across, width, True), self._offset(down, height, False)
        attrs = [f'data-w="{width * self.k:.3f}" data-h="{height * self.k:.3f}"']
        for key, (relative, align, offset) in (("h", across), ("v", down)):
            if relative or align or offset:
                attrs.append(f'data-{key}rel="{html.escape(relative, quote=True)}"')
                attrs.append(f'data-{key}align="{html.escape(align, quote=True)}"')
                attrs.append(f'data-{key}off="{offset * self.k:.3f}"')
        if wrap in ("wrapTopAndBottom", "wrapSquare", "wrapTight", "wrapThrough"):
            attrs.append(f'data-side="{html.escape(side, quote=True)}"')
            if outline:
                attrs.append('data-poly="' + " ".join(f"{x * self.k:.2f},{y * self.k:.2f}" for x, y in outline) + '"')
            self._floats.append(self._floated(content, width, height, wrap, gap, x, y, attrs))
            return ""
        behind = "z-index:-1;" if behind_text else "z-index:1;"
        return (f'<span class="anchor" {" ".join(attrs)} style="position:absolute;{behind}'
                f'left:{self._u(x - self._para_left)};top:{self._u(y)};text-indent:0;line-height:0">{content}</span>')

    def _floated(self, content: str, width: float, height: float, wrap: str, gap: dict, x: float, y: float, attrs: list) -> str:
        """Something the text wraps around, written at the start of its paragraph.
        It is a float reaching from the column's edge past the object, and only
        the object's own band keeps text away, so the lines above it stay above.
        The pages then measure it where it really falls (docx_pages.js)."""
        column = self._page[0] - self._page[3] - self._page[5]
        across = wrap == "wrapTopAndBottom"
        side = "left" if across or x + width / 2.0 <= column / 2.0 else "right"
        wide = column if across else (max(0.0, x + width + gap["distR"]) if side == "left" else max(0.0, column - x + gap["distL"]))
        left = x if side == "left" else gap["distL"]
        shift = f"margin-left:{self._u(-self._para_left)}" if side == "left" else "margin-right:0"
        data = " ".join(attrs + [f'data-wrap="{wrap}"', 'data-gap="' + " ".join(
            f"{gap[key] * self.k:.3f}" for key in ("distT", "distR", "distB", "distL")) + '"'])
        return (f'<span class="floated" {data} style="float:{side};{shift};width:{self._u(wide)};'
                f'height:{self._u(max(0.0, y + height + gap["distB"]))};'
                f'shape-outside:inset({self._u(max(0.0, y - gap["distT"]))} 0 0 0) border-box">'
                f'<span class="float-body" style="left:{self._u(left)};top:{self._u(y)}">{content}</span></span>')

    # -- notes --------------------------------------------------------------------------

    def _read_notes(self) -> None:
        for kind in ("footnote", "endnote"):
            part = next((p for p in self.part.package.iter_parts() if p.content_type.endswith(kind + "s+xml")), None)
            if part is None:
                continue
            self.note_parts[kind] = part
            for note in etree.fromstring(part.blob).findall(W + kind):
                role = note.get(W + "type")
                if role == "separator" and kind == "footnote":
                    self.separator = note
                elif role not in ("separator", "continuationSeparator", "continuationNotice"):
                    self.notes[(kind, note.get(W + "id"))] = note

    def _note_mark(self, kind: str, note_id) -> str:
        note = self.notes.get((kind, note_id))
        if note is None:
            return ""
        bucket = self.footnotes if kind == "footnote" else self.endnotes
        bucket.append(note)
        label = str(len(bucket)) if kind == "footnote" else _format_number(len(bucket), "lowerRoman")
        # As entities, so the digits of Arabic text (which go to the Latin font) leave it alone.
        shown = "".join(f"&#{ord(ch)};" for ch in label)
        return f'<span class="note-ref" data-note="{kind[0]}{len(bucket)}">{shown}</span>'

    def _notes_html(self) -> str:
        """The notes after the text. The pages move footnotes to the foot of
        the page that refers to them; endnotes stay at the end."""
        padding = f"padding:0 {self._u(self._sides[1])} 0 {self._u(self._sides[0])}"
        out = []
        for bucket, kind, number, holder in ((self.footnotes, "footnote", "decimal", "eshab-notes"),
                                             (self.endnotes, "endnote", "lowerRoman", "eshab-endnotes")):
            if not bucket:
                continue
            part = self.note_parts[kind]
            if self.separator is not None and kind == "footnote":
                line = self._rendered(self.separator, part)
            else:
                line = '<div class="p"><span class="sep-line"></span></div>'
            notes = "".join(f'<div class="note" data-note="{kind[0]}{index + 1}">'
                            f"{self._rendered(note, part, _format_number(index + 1, number))}</div>"
                            for index, note in enumerate(bucket))
            out.append(f'<div class="notes" id="{holder}" style="{padding}"><div class="note-sep">{line}</div>{notes}</div>')
        return "".join(out)

    # -- tables -------------------------------------------------------------------------

    def _floating_table(self, tbl, position) -> str:
        """A table text wraps around, as a float on the paragraph after it."""
        get = lambda name: _val(position, name)
        twips = lambda name: _pt(get(name)) if get(name) is not None else 0.0
        across = ({"text": "column", "margin": "margin", "page": "page"}.get(get("horzAnchor") or "text", "column"),
                  get("tblpXSpec") or "", twips("tblpX"))
        down = ({"text": "paragraph", "margin": "margin", "page": "page"}.get(get("vertAnchor") or "text", "paragraph"),
                (get("tblpYSpec") or "").replace("inline", ""), twips("tblpY"))
        gap = {"distT": twips("topFromText"), "distB": twips("bottomFromText"),
               "distL": twips("leftFromText"), "distR": twips("rightFromText")}
        html_table = self.table(tbl, floating=True)
        grid = _w(tbl, "tblGrid")
        width = sum(_pt(_val(col, "w")) for col in grid.findall(W + "gridCol")) if grid is not None else 0.0
        self._placed(html_table, width, 0.0, "wrapSquare", gap, across, down, False)
        made = self._floats.pop()
        return made.replace('class="floated" ', 'class="floated" data-measure="1" ', 1)

    def table(self, tbl, floating: bool = False) -> str:
        tblpr = _w(tbl, "tblPr")
        style = TableStyle(self.styles, _val(_w(tblpr, "tblStyle")))
        borders = _table_borders(dict(style.borders), _w(tblpr, "tblBorders"))
        margins = {"top": 0.0, "bottom": 0.0, "start": 5.4, "end": 5.4}
        margins.update(style.margins)
        _cell_margins(margins, _w(tblpr, "tblCellMar"))
        look = _look(_w(tblpr, "tblLook"))
        rtl = bool(_toggle(_w(tblpr, "bidiVisual")))
        grid_el = _w(tbl, "tblGrid")
        grid = [_pt(_val(col, "w")) for col in grid_el.findall(W + "gridCol")] if grid_el is not None else []
        layout = self._table_layout([tr for tr in tbl if tr.tag == W + "tr"])
        columns = max([len(grid)] + [c["column"] + c["colspan"] for _, cells in layout for c in cells])
        # Word measures columns from the middle of their borders; a collapsed
        # table's box reaches half a border further out on each side.
        half_start = (borders["left"][0] if borders.get("left") else 0.0) / 2.0
        half_end = (borders["right"][0] if borders.get("right") else 0.0) / 2.0
        wide = sum(grid) + half_start + half_end
        css = [f"table-layout:fixed;width:{self._u(wide)}" if grid and sum(grid) else "width:100%"]
        indent = _pt(_val(_w(tblpr, "tblInd"), "w"))
        jc = _val(_w(tblpr, "jc"))
        if jc == "center":
            css.append("margin-inline:auto")
        elif jc in ("right", "end"):
            css.append("margin-inline-start:auto")
        elif not floating:            # a floating table stands where its position says
            if self.compat < 15:      # before Word 2013 the first cell's text lines up with the margin
                indent -= margins["start"]
            indent -= half_start
            if indent:
                css.append(f"margin-inline-start:{self._u(indent)}")
        self._started = True
        self._after_break = False
        out = [f'<table dir="{"rtl" if rtl else "ltr"}" style="{";".join(css)}">']
        if grid:
            out.append("<colgroup>" + "".join(f'<col style="width:{self._u(w)}">' for w in grid) + "</colgroup>")
        heads = 0
        while heads < len(layout) and _toggle(_w(_w(layout[heads][0], "trPr"), "tblHeader")):
            heads += 1
        for index, (tr, cells) in enumerate(layout):
            if index == 0:
                out.append("<thead>" if heads else "<tbody>")
            elif index == heads:
                out.append("</thead><tbody>")
            trpr = _w(tr, "trPr")
            row_css = []
            height = _w(trpr, "trHeight")
            if height is not None and _num(_val(height)):
                row_css.append(f"height:{self._u(_pt(_val(height)))}")
            if _toggle(_w(trpr, "cantSplit")):
                row_css.append("break-inside:avoid")
            out.append(f'<tr style="{";".join(row_css)}">')
            before = int(_num(_val(_w(trpr, "gridBefore")), 0))
            if before:
                out.append(f'<td colspan="{before}" style="border:none;padding:0"></td>')
            for cell in cells:
                out.append(self._cell(cell, style, borders, margins, look, index, len(layout), columns))
            after = int(_num(_val(_w(trpr, "gridAfter")), 0))
            if after:
                out.append(f'<td colspan="{after}" style="border:none;padding:0"></td>')
            out.append("</tr>")
        if layout:
            out.append("</thead>" if heads >= len(layout) else "</tbody>")
        out.append("</table>")
        self._prev_after = 0.0
        return "".join(out)

    @staticmethod
    def _table_layout(rows):
        """Rows and their cells, with Word's vertical merges as row spans."""
        layout, open_cells = [], {}
        for tr in rows:
            column = int(_num(_val(_w(_w(tr, "trPr"), "gridBefore")), 0))
            cells = []
            for tc in [c for c in tr if c.tag == W + "tc"]:
                tcpr = _w(tc, "tcPr")
                span = max(1, int(_num(_val(_w(tcpr, "gridSpan")), 1)))
                merge = _w(tcpr, "vMerge")
                if merge is not None and _val(merge) != "restart" and column in open_cells:
                    open_cells[column]["rowspan"] += 1
                    column += span
                    continue
                cell = {"tc": tc, "column": column, "colspan": span, "rowspan": 1}
                for covered in range(column, column + span):
                    open_cells.pop(covered, None)
                if merge is not None:
                    open_cells[column] = cell
                cells.append(cell)
                column += span
            layout.append((tr, cells))
        return layout

    def _cell(self, cell, style: TableStyle, borders, margins, look, row, rows, columns) -> str:
        tc = cell["tc"]
        tcpr = _w(tc, "tcPr")
        column, span = cell["column"], cell["colspan"]
        ppr, rpr, fill, edges = {}, {}, None, {}
        for region in style.regions_for(row, rows, column, span, columns, look):
            ppr.update(region.ppr)
            rpr.update(region.rpr)
            fill = region.fill or fill
            edges.update(region.borders)
        own = _table_borders({}, _w(tcpr, "tcBorders"))
        at = {"top": row == 0, "bottom": row + cell["rowspan"] >= rows, "left": column == 0,
              "right": column + span >= columns}
        inner = {"top": "insideH", "bottom": "insideH", "left": "insideV", "right": "insideV"}
        css = []
        drawn = {}
        for side, prop in (("top", "border-top"), ("bottom", "border-bottom"), ("left", "border-inline-start"),
                           ("right", "border-inline-end")):
            if side in own:
                edge = own[side]
            elif side in edges:
                edge = edges[side]
            else:
                edge = borders.get(side) if at[side] else borders.get(inner[side])
            drawn[side] = edge[0] if edge else 0.0
            css.append(f"{prop}:{_edge_css(edge, self.k)}")
        pad = _cell_margins(dict(margins), _w(tcpr, "tcMar"))
        # Word's cell margins start at the middle of the border; half of a
        # collapsed border already sits inside the cell.
        css.append(f"padding:{self._u(pad['top'])} 0 {self._u(pad['bottom'])} 0;"
                   f"padding-inline-start:{self._u(max(0.0, pad['start'] - drawn['left'] / 2.0))};"
                   f"padding-inline-end:{self._u(max(0.0, pad['end'] - drawn['right'] / 2.0))}")
        fill = _fill(_w(tcpr, "shd")) or fill
        if fill:
            css.append(f"background:#{fill}")
        css.append("vertical-align:" + {"center": "middle", "bottom": "bottom"}.get(_val(_w(tcpr, "vAlign")), "top"))
        if _toggle(_w(tcpr, "noWrap")):
            css.append("white-space:nowrap")
        attrs = ((f' colspan="{span}"' if span > 1 else "")
                 + (f' rowspan="{cell["rowspan"]}"' if cell["rowspan"] > 1 else ""))
        self._prev_after = 0.0
        content = "".join(self._blocks(tc, (ppr, rpr)))
        self._prev_after = 0.0
        return f'<td{attrs} data-col="{column}" style="{";".join(css)}">{content}</td>'


BASE_CSS = """
html, body { margin: 0; padding: 0; }
body { font-family: Arial, 'Segoe UI', sans-serif; font-size: 10pt; color: #000; text-rendering: geometricPrecision;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.p { margin: 0; white-space: pre-wrap; overflow-wrap: break-word; font-weight: normal; position: relative; }
.page { position: relative; overflow: hidden; break-after: page; z-index: 0; }
.page:last-of-type { break-after: auto; }
.col, .hdr, .ftr, .notes-area { position: absolute; display: flow-root; }
.col-line { position: absolute; width: 0; border-left: 0.75pt solid #000; }
.marker, .at, .leader, .crop, .tab { text-indent: 0; }
.marker { display: inline-block; white-space: pre; }
.at { position: absolute; top: 0; white-space: pre; }
.leader { position: absolute; top: 0; overflow: hidden; white-space: nowrap; }
.pictured, .pictured > span, .pictured > a > span { line-height: 0 !important; }
.pictured img, .pictured .crop, .pictured .drawn { vertical-align: bottom; }
.drawn { display: inline-block; position: relative; text-indent: 0; line-height: 0; direction: ltr; color: #000; font-weight: normal;
         font-style: normal; letter-spacing: normal; word-spacing: normal; text-decoration: none; text-transform: none;
         font-kerning: auto; font-variant-ligatures: normal; font-variant-caps: normal; background: none; }
.floated { position: relative; text-indent: 0; line-height: 0; direction: ltr; }
.float-body { position: absolute; }
.strut { display: inline-block; width: 0.01pt; vertical-align: bottom; }
.pictured.low :is(.drawn, img, .crop):not(.drawn *) { margin-bottom: var(--below); }
.wrap-gap { display: inline-block; height: 0; text-indent: 0; }
.layer { display: block; position: absolute; }
.layer > img { display: block; }
.shape-text { position: absolute; display: flex; flex-direction: column; }
.text-flow { display: flow-root; min-width: 0; min-height: 0; }
.unwrapped .p { white-space: pre; }
.tab { display: inline-block; }
.page-break { display: block; break-before: page; height: 0; }
table { border-collapse: collapse; border-spacing: 0; }
td { overflow-wrap: break-word; }
.crop { display: inline-block; overflow: hidden; direction: ltr; }
.sep-line { display: inline-block; width: 144pt; border-top: 0.75pt solid #000; vertical-align: 2.5pt; }
a { color: inherit; text-decoration: none; }
"""


def document_html(path: Path) -> str:
    return Layout(Path(path)).html()
