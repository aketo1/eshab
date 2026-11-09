"""DrawingML, the language of Office drawings, drawn as SVG.

Colours through the theme and its transforms, fills, lines with arrow heads,
and the preset shapes. Lengths are points and one SVG unit is one point, so a
drawing scales with its viewBox. Word's shapes, SmartArt and charts all come
through here; nothing in this module knows about Word.
"""
from __future__ import annotations

import colorsys
import html
import itertools
import math
import re

from .preset_outlines import OUTLINES, TEXT_AREAS
from .preset_shapes import CORNERED, more_presets, scaled_outline

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
EMU_PER_PT = 12700.0

OFFICE_SCHEME = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6", "accent1": "4472C4",
                 "accent2": "ED7D31", "accent3": "A5A5A5", "accent4": "FFC000", "accent5": "5B9BD5",
                 "accent6": "70AD47", "hlink": "0563C1", "folHlink": "954F72"}
DEFAULT_MAP = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
PRESET_COLORS = {"black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000", "lime": "00FF00",
                 "blue": "0000FF", "yellow": "FFFF00", "cyan": "00FFFF", "magenta": "FF00FF", "gray": "808080",
                 "grey": "808080", "silver": "C0C0C0", "orange": "FFA500", "navy": "000080", "maroon": "800000",
                 "purple": "800080", "teal": "008080", "olive": "808000", "brown": "A52A2A", "pink": "FFC0CB",
                 "gold": "FFD700", "indigo": "4B0082", "violet": "EE82EE", "ltGray": "D3D3D3", "dkGray": "A9A9A9",
                 "transparent": "FFFFFF"}
SYSTEM_COLORS = {"windowText": "000000", "window": "FFFFFF", "btnFace": "F0F0F0", "btnText": "000000",
                 "highlight": "0078D7", "highlightText": "FFFFFF", "grayText": "6D6D6D", "menu": "F0F0F0",
                 "menuText": "000000", "activeCaption": "99B4D1", "background": "000000"}
DASHES = {"dot": (1, 3), "sysDot": (1, 1), "dash": (4, 3), "sysDash": (3, 1), "lgDash": (8, 3), "dashDot": (4, 3, 1, 3),
          "sysDashDot": (3, 1, 1, 1), "lgDashDot": (8, 3, 1, 3), "lgDashDotDot": (8, 3, 1, 3, 1, 3),
          "sysDashDotDot": (3, 1, 1, 1, 1, 1)}
#: Each preset pattern as eight rows of eight dots (the high bit is the left dot). Word
#: draws a dot as 0.75pt, so a tile is 6pt square. The first group was read from Word's
#: own PDFs; the rest are the same Windows hatches.
PATTERNS = {
    "pct5": "8000000008000000", "pct20": "8800220088002200", "pct50": "AA55AA55AA55AA55", "pct75": "77FFDDFF77FFDDFF",
    "ltHorz": "FF000000FF000000", "dkVert": "CCCCCCCCCCCCCCCC", "ltUpDiag": "1122448811224488", "dkDnDiag": "CC663399CC663399",
    "wdUpDiag": "83070E1C3870E0C1", "smGrid": "FF888888FF888888", "lgGrid": "FF80808080808080", "smCheck": "9966669999666699",
    "lgCheck": "F0F0F0F00F0F0F0F", "dotGrid": "AA00800080008000", "horzBrick": "FF808080FF080808", "weave": "8854224588142251",
    "divot": "0010081000800180", "plaid": "AA55AA55F0F0F0F0", "sphere": "77898F8F7798F8F8", "shingle": "038448300C020101",
    "trellis": "FF66FF99FF66FF99", "zigZag": "8142241881422418", "wave": "001825C0001825C0", "solidDmnd": "10387CFE7C381000",
    "pct10": "8000080080000800", "pct25": "8822882288228822", "pct30": "8855225588552255", "pct40": "AA55A255AA552A55",
    "pct60": "BB55EE55BB55EE55", "pct70": "77DD77DD77DD77DD", "pct80": "F7FF7FFFF7FF7FFF", "pct90": "F7FFFFFF7FFFFFFF",
    "dkHorz": "FFFF0000FFFF0000", "ltVert": "8888888888888888", "narHorz": "FF00FF00FF00FF00", "narVert": "AAAAAAAAAAAAAAAA",
    "ltDnDiag": "8844221188442211", "dnDiag": "8040201008040201", "upDiag": "0102040810204080", "dkUpDiag": "3366CC993366CC99",
    "wdDnDiag": "C1E070381C0E0783", "dashDnDiag": "8844221100000000", "dashUpDiag": "1122448800000000",
    "dashHorz": "F00000000F000000", "dashVert": "8080808008080808", "horz": "FF00000000000000", "vert": "8080808080808080",
    "cross": "FF80808080808080", "diagCross": "8142241818244281", "smConfetti": "8004400220011008",
    "lgConfetti": "B130031BD8C00C8D", "openDmnd": "8041221408142241", "dotDmnd": "8000220008002200",
    "diagBrick": "0102040818244281",
}

#: The lighter and darker parts of a shape: what goes over its fill, and how strongly.
SHADES = {"lighten": ("#FFFFFF", ".4"), "lightenLess": ("#FFFFFF", ".2"), "darken": ("#000000", ".4"), "darkenLess": ("#000000", ".2")}
_IDS = itertools.count(1)


def emu(value, default: float = 0.0) -> float:
    """EMU to points."""
    try:
        return float(value) / EMU_PER_PT
    except (TypeError, ValueError):
        return default


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class Palette:
    """A theme's colours and looks. ``scheme`` holds dk1, lt1 and so on;
    ``mapping`` the document's colour map; ``formats`` the theme's fill, line
    and effect lists, which shapes pick from through their style."""

    def __init__(self, scheme=None, mapping=None, fills=(), lines=(), fonts=None, effects=None):
        self.scheme = {**OFFICE_SCHEME, **(scheme or {})}
        self.mapping = {**DEFAULT_MAP, **(mapping or {})}
        self.fills = list(fills)
        self.lines = list(lines)
        self.fonts = fonts or {}
        # Office's own effect styles, for a document without a theme: the third casts a shadow.
        self.effects = list(effects) if effects is not None else [None, None, _office_shadow()]

    def font(self, typeface, slot: str = "minor") -> str:
        """A font name, resolving theme references such as +mn-lt."""
        if not typeface:
            return self.fonts.get(slot + "Latin", "")
        if typeface.startswith("+"):
            kind = "major" if typeface[1:3] == "mj" else "minor"
            return self.fonts.get(kind + ("Bidi" if typeface.endswith("cs") else "Latin"), "")
        return typeface

    def scheme_color(self, name: str, placeholder=None) -> str:
        if name == "phClr" and placeholder:
            return placeholder
        return self.scheme.get(self.mapping.get(name, name), "000000")

    def color(self, element, placeholder=None):
        """(RRGGBB, alpha) of any DrawingML colour element."""
        tag = element.tag[len(A):] if element.tag.startswith(A) else element.tag
        value = element.get("val") or ""
        if tag == "srgbClr":
            base = value.upper() if len(value) == 6 else "000000"
        elif tag == "schemeClr":
            base = self.scheme_color(value, placeholder)
        elif tag == "sysClr":
            base = element.get("lastClr") or SYSTEM_COLORS.get(value, "000000")
        elif tag == "prstClr":
            base = PRESET_COLORS.get(value, "000000")
        elif tag == "scrgbClr":
            base = "%02X%02X%02X" % tuple(int(_clamp(_number(element.get(k)) / 100000.0) * 255)
                                          for k in ("r", "g", "b"))
        elif tag == "hslClr":
            r, g, b = colorsys.hls_to_rgb(_number(element.get("hue")) / 21600000.0, _number(element.get("lum")) / 100000.0,
                                          _number(element.get("sat")) / 100000.0)
            base = "%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))
        else:
            return "000000", 1.0
        return _transform(base, element)

    def first_color(self, parent, placeholder=None):
        """The colour element directly inside ``parent``."""
        if parent is None:
            return None
        for child in parent:
            if child.tag[len(A):] in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr", "hslClr"):
                return self.color(child, placeholder)
        return None


_SHADOW: list = []


def _office_shadow():
    """The third of Office's own effect styles: a soft shadow below the shape."""
    if not _SHADOW:
        from lxml import etree

        _SHADOW.append(etree.fromstring(
            f'<a:effectStyle xmlns:a="{A[1:-1]}"><a:effectLst>'
            '<a:outerShdw blurRad="57150" dist="19050" dir="5400000" algn="ctr" rotWithShape="0">'
            '<a:srgbClr val="000000"><a:alpha val="63000"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle>'))
    return _SHADOW[0]


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    c = _clamp(c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _transform(base: str, element):
    r, g, b = (int(base[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    alpha = 1.0
    for change in element:
        kind = change.tag[len(A):]
        amount = _number(change.get("val")) / 100000.0
        if kind == "alpha":
            alpha = amount
        elif kind == "alphaMod":
            alpha *= amount
        elif kind == "alphaOff":
            alpha += amount
        elif kind == "shade":       # these two work on light, not on the stored values
            r, g, b = (_gamma(_linear(c) * amount) for c in (r, g, b))
        elif kind == "tint":
            r, g, b = (_gamma(_linear(c) * amount + 1 - amount) for c in (r, g, b))
        elif kind in ("lumMod", "lumOff", "satMod", "satOff", "hueMod", "hueOff"):
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            if kind == "lumMod":
                l *= amount
            elif kind == "lumOff":
                l += amount
            elif kind == "satMod":
                s *= amount
            elif kind == "satOff":
                s += amount
            elif kind == "hueMod":
                h = (h * amount) % 1.0
            else:
                h = (h + _number(change.get("val")) / 21600000.0) % 1.0
            r, g, b = colorsys.hls_to_rgb(h, _clamp(l), _clamp(s))
        elif kind == "gray":
            r = g = b = 0.299 * r + 0.587 * g + 0.114 * b
        elif kind == "comp":
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            r, g, b = colorsys.hls_to_rgb((h + 0.5) % 1.0, l, s)
        elif kind == "inv":
            r, g, b = 1 - r, 1 - g, 1 - b
    return "%02X%02X%02X" % tuple(int(round(_clamp(c) * 255)) for c in (r, g, b)), _clamp(alpha)


class Canvas:
    """One drawing's paints: it collects the gradients and arrow heads the
    drawn paths refer to, and writes them out as SVG definitions."""

    def __init__(self, palette: Palette, picture=None):
        self.palette = palette
        self.picture = picture          # relationship id -> data URI
        self.defs: list[str] = []
        self.patterns: dict = {}        # pattern id -> (rows, fore, back), to draw them crisply

    def definitions(self) -> str:
        return "<defs>" + "".join(self.defs) + "</defs>" if self.defs else ""

    # -- fills ----------------------------------------------------------------------

    def fill_of(self, parent):
        """The fill element directly inside ``parent``, if any."""
        if parent is None:
            return None
        for child in parent:
            if child.tag[len(A):] in ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"):
                return child
        return None

    def paint(self, fill, placeholder=None, size=None) -> str:
        """SVG attributes for a fill element (fill="..." and its opacity). With the
        shape's size, gradients run as Word runs them in that shape."""
        if fill is None:
            return 'fill="none"'
        kind = fill.tag[len(A):] if fill.tag.startswith(A) else fill.tag
        if kind == "noFill":
            return 'fill="none"'
        if kind == "solidFill":
            found = self.palette.first_color(fill, placeholder)
            return _solid(found) if found else 'fill="none"'
        if kind == "gradFill":
            return self._gradient(fill, placeholder, size)
        if kind == "pattFill":
            return self._pattern(fill, placeholder)
        if kind == "blipFill":
            return self._blip(fill)
        return 'fill="none"'

    def _gradient(self, fill, placeholder, size=None) -> str:
        stops = []
        for stop in fill.iter(A + "gs"):
            found = self.palette.first_color(stop, placeholder)
            if found:
                stops.append((_number(stop.get("pos")) / 100000.0, found))
        if not stops:
            return 'fill="none"'
        stops.sort(key=lambda item: item[0])
        marks = "".join(f'<stop offset="{at:.4f}" stop-color="#{c}"' + (f' stop-opacity="{a:.3f}"' if a < 1 else "") + "/>"
                        for at, (c, a) in stops)
        name = f"g{next(_IDS)}"
        w, h = size if size else (1.0, 1.0)
        units = ' gradientUnits="userSpaceOnUse"' if size else ""
        path = fill.find(A + "path")
        if path is not None:
            area = path.find(A + "fillToRect")
            left, top, right, bottom = (_number(area.get(k)) / 100000.0 if area is not None else 0.5
                                        for k in ("l", "t", "r", "b"))
            x0, y0, x1, y1 = left, top, max(left, 1 - right), max(top, 1 - bottom)
            if path.get("path") in ("rect", "shape"):
                return self._rect_gradient(name, stops, (x0, y0, x1, y1))
            # From the focus to the farthest corner, round in the shape as it stands.
            cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
            radius = max(math.hypot(cx - x, cy - y) for x in (0, w) for y in (0, h))
            self.defs.append(f'<radialGradient id="{name}"{units} cx="{cx:.4f}" cy="{cy:.4f}" r="{radius:.4f}">{marks}</radialGradient>')
            return f'fill="url(#{name})"'
        line = fill.find(A + "lin")
        angle = math.radians(_number(line.get("ang")) / 60000.0 if line is not None else 90.0)
        dx, dy = math.cos(angle), math.sin(angle)
        if line is not None and line.get("scaled") in ("1", "true"):
            reach = abs(dx) + abs(dy)                     # drawn in a square, then stretched
            ux, uy = dx * w * reach / 2, dy * h * reach / 2
        else:
            reach = abs(dx) * w + abs(dy) * h            # the corners land on the first and last stop
            ux, uy = dx * reach / 2, dy * reach / 2
        self.defs.append(f'<linearGradient id="{name}"{units} x1="{w / 2 - ux:.4f}" y1="{h / 2 - uy:.4f}" '
                         f'x2="{w / 2 + ux:.4f}" y2="{h / 2 + uy:.4f}">{marks}</linearGradient>')
        return f'fill="url(#{name})"'

    def _rect_gradient(self, name, stops, focus) -> str:
        """A gradient from a rectangle out to the shape's edges, in rings parallel to them:
        four sides, each a plain gradient, in a tile the size of the shape."""
        x0, y0, x1, y1 = focus
        marks = "".join(f'<stop offset="{at:.4f}" stop-color="#{c}"' + (f' stop-opacity="{a:.3f}"' if a < 1 else "") + "/>"
                        for at, (c, a) in stops)
        sides = (((0, 0), (1, 0), (x1, y0), (x0, y0), (0, y0, 0, 0)), ((1, 0), (1, 1), (x1, y1), (x1, y0), (x1, 0, 1, 0)),
                 ((1, 1), (0, 1), (x0, y1), (x1, y1), (0, y1, 0, 1)), ((0, 1), (0, 0), (x0, y0), (x0, y1), (x0, 0, 0, 0)))
        parts = []
        for index, (a, b, c, d, (gx1, gy1, gx2, gy2)) in enumerate(sides):
            ramp = f"{name}s{index}"
            parts.append(f'<linearGradient id="{ramp}" gradientUnits="userSpaceOnUse" x1="{gx1:.4f}" y1="{gy1:.4f}" '
                         f'x2="{gx2:.4f}" y2="{gy2:.4f}">{marks}</linearGradient>')
        shapes = "".join(f'<path d="M{a[0]} {a[1]}L{b[0]} {b[1]}L{c[0]:.4f} {c[1]:.4f}L{d[0]:.4f} {d[1]:.4f}Z" fill="url(#{name}s{index})"/>'
                         for index, (a, b, c, d, _) in enumerate(sides))
        first = stops[0][1]
        middle = (f'<rect x="{x0:.4f}" y="{y0:.4f}" width="{x1 - x0:.4f}" height="{y1 - y0:.4f}" fill="#{first[0]}"/>'
                  if x1 > x0 and y1 > y0 else "")
        self.defs.append("".join(parts) + f'<pattern id="{name}" patternContentUnits="objectBoundingBox" width="1" height="1">'
                         f"{shapes}{middle}</pattern>")
        return f'fill="url(#{name})"'

    def _pattern(self, fill, placeholder) -> str:
        """A preset pattern as Word prints it: a crisp tile of dots, 6pt square."""
        fore = self.palette.first_color(fill.find(A + "fgClr"), placeholder) or ("000000", 1.0)
        back = self.palette.first_color(fill.find(A + "bgClr"), placeholder) or ("FFFFFF", 1.0)
        name = f"p{next(_IDS)}"
        rows = PATTERNS.get(fill.get("prst") or "", PATTERNS["pct50"])
        self.patterns[name] = (rows, fore, back)
        tile = _pattern_tile(rows, fore, back)
        self.defs.append(f'<pattern id="{name}" width="6" height="6" patternUnits="userSpaceOnUse">'
                         f'<image href="{tile}" width="6" height="6" preserveAspectRatio="none" style="image-rendering:pixelated"/></pattern>')
        return f'fill="url(#{name})"'

    def _blip(self, fill) -> str:
        blip = fill.find(A + "blip")
        rid = None
        if blip is not None:
            rid = next((v for k, v in blip.attrib.items() if k.endswith("}embed")), None)
        uri = self.picture(rid) if rid and self.picture else None
        if not uri:
            return 'fill="#D9D9D9"'
        name = f"b{next(_IDS)}"
        self.defs.append(f'<pattern id="{name}" patternContentUnits="objectBoundingBox" width="1" height="1">'
                         f'<image href="{uri}" width="1" height="1" preserveAspectRatio="none"/></pattern>')
        return f'fill="url(#{name})"'

    # -- lines ----------------------------------------------------------------------

    def stroke(self, line, placeholder=None, default_width: float = 0.75, default_color=None) -> str:
        """SVG attributes for an a:ln element (and arrow heads on its ends)."""
        if line is None:
            if default_color:
                return f'stroke="#{default_color}" stroke-width="{default_width:.3f}"'
            return 'stroke="none"'
        if line.find(A + "noFill") is not None:
            return 'stroke="none"'
        width = emu(line.get("w"), default_width) or default_width
        found = None
        fill = line.find(A + "solidFill")
        if fill is not None:
            found = self.palette.first_color(fill, placeholder)
        elif line.find(A + "gradFill") is not None:
            stop = next(line.find(A + "gradFill").iter(A + "gs"), None)
            found = self.palette.first_color(stop, placeholder) if stop is not None else None
        if found is None and default_color:
            found = (default_color, 1.0)
        if found is None:
            return 'stroke="none"'
        color, alpha = found
        out = [f'stroke="#{color}"', f'stroke-width="{width:.3f}"']
        if alpha < 1:
            out.append(f'stroke-opacity="{alpha:.3f}"')
        dash = line.find(A + "prstDash")
        pattern = DASHES.get(dash.get("val")) if dash is not None else None
        if pattern:
            out.append('stroke-dasharray="' + " ".join(f"{step * width:.2f}" for step in pattern) + '"')
        cap = {"rnd": "round", "sq": "square"}.get(line.get("cap") or "")
        if cap:
            out.append(f'stroke-linecap="{cap}"')
        if line.find(A + "round") is not None:
            out.append('stroke-linejoin="round"')
        elif line.find(A + "miter") is not None:
            out.append('stroke-linejoin="miter"')
        for tag, attribute in (("headEnd", "marker-start"), ("tailEnd", "marker-end")):
            end = line.find(A + tag)
            if end is not None and end.get("type") not in (None, "none"):
                out.append(f'{attribute}="url(#{self._arrow(end, color, width)})"')
        return " ".join(out)

    @staticmethod
    def _head(end, width: float) -> tuple:
        """An arrow head's (kind, length, breadth, how far before its tip the line stops)."""
        kind = end.get("type")
        base = max(width, 2.0)        # thin lines get heads as if they were 2pt
        size = {"sm": 2.0, "lg": 5.0}
        long = size.get(end.get("len") or "", 3.0) * base
        wide = size.get(end.get("w") or "", 3.0) * base
        if kind == "stealth":
            cut = long - base * (2.0 if end.get("len") == "lg" else 1.0)
        elif kind in ("diamond", "oval"):
            cut = 0.0
        elif kind == "arrow":
            cut = 0.94 * width
        else:
            cut = long - base / 2
        return kind, long, wide, cut

    def arrow_cuts(self, line, width: float) -> tuple:
        """How much shorter the line is at its start and its end, under its arrow heads."""
        cuts = []
        for tag in ("headEnd", "tailEnd"):
            end = line.find(A + tag) if line is not None else None
            cuts.append(self._head(end, width)[3] if end is not None and end.get("type") not in (None, "none") else 0.0)
        return tuple(cuts)

    def _arrow(self, end, color: str, width: float = 0.75) -> str:
        name = f"a{next(_IDS)}"
        kind, long, wide, cut = self._head(end, width)
        half = wide / 2
        if kind == "stealth":
            shape, paint = f"M0 0L{long:.3f} {half:.3f}L0 {wide:.3f}L{long - cut:.3f} {half:.3f}Z", f'fill="#{color}"'
        elif kind == "diamond":
            shape, paint = f"M0 {half:.3f}L{long / 2:.3f} 0L{long:.3f} {half:.3f}L{long / 2:.3f} {wide:.3f}Z", f'fill="#{color}"'
        elif kind == "oval":
            shape = (f"M0 {half:.3f}A{long / 2:.3f} {half:.3f} 0 1 1 {long:.3f} {half:.3f}"
                     f"A{long / 2:.3f} {half:.3f} 0 1 1 0 {half:.3f}Z")
            paint = f'fill="#{color}"'
        elif kind == "arrow":
            shape = f"M0 0L{long:.3f} {half:.3f}L0 {wide:.3f}"
            paint = f'fill="none" stroke="#{color}" stroke-width="{width:.3f}" stroke-linejoin="round" stroke-linecap="round"'
        else:
            shape, paint = f"M0 0L{long:.3f} {half:.3f}L0 {wide:.3f}Z", f'fill="#{color}"'
        refer = long / 2 if kind in ("diamond", "oval") else long - cut
        self.defs.append(f'<marker id="{name}" viewBox="0 0 {long:.3f} {wide:.3f}" refX="{refer:.3f}" refY="{half:.3f}" '
                         f'markerWidth="{long:.3f}" markerHeight="{wide:.3f}" markerUnits="userSpaceOnUse" '
                         f'orient="auto-start-reverse" overflow="visible"><path d="{shape}" {paint}/></marker>')
        return name

    # -- a whole shape ----------------------------------------------------------------

    def shape_paths(self, sp_pr, style, width: float, height: float, default_line=None) -> str:
        """The SVG of one shape's outline, filled and stroked as Word draws it."""
        fill_el = self.fill_of(sp_pr)
        placeholder = None
        fill_ref = style.find(A + "fillRef") if style is not None else None
        line_ref = style.find(A + "lnRef") if style is not None else None
        if fill_el is None and fill_ref is not None:
            found = self.palette.first_color(fill_ref)
            placeholder = found[0] if found else None
            index = int(_number(fill_ref.get("idx")))
            if index >= 1001 and index - 1001 < 3:
                index -= 1000
            fill_el = self.palette.fills[index - 1] if 0 < index <= len(self.palette.fills) else None
            if fill_el is None and index > 0 and found:
                paint = _solid(found)
            else:
                paint = self.paint(fill_el, placeholder, (width, height))
        else:
            paint = self.paint(fill_el, size=(width, height))
        line_el = sp_pr.find(A + "ln") if sp_pr is not None else None
        line_placeholder = None
        base_line = None
        if line_ref is not None:
            found = self.palette.first_color(line_ref)
            line_placeholder = found[0] if found else None
            index = int(_number(line_ref.get("idx")))
            base_line = self.palette.lines[index - 1] if 0 < index <= len(self.palette.lines) else None
        stroke = self._merged_stroke(line_el, base_line, line_placeholder, default_line)
        out = []
        pieces = geometry(sp_pr, width, height)
        found = re.search('stroke-width="([0-9.]+)"', stroke)
        line_width = float(found.group(1)) if found else 0.0
        cuts = self.arrow_cuts(line_el, line_width)
        if any(cuts):
            pieces = [(_shortened(d, cuts) if mode == "nofill" else d, mode) for d, mode in pieces]
        shadow, shadow_color = self._shadow_of(sp_pr, style)
        if shadow is not None and shadow_color:
            dist, angle = emu(shadow.get("dist")), math.radians(_number(shadow.get("dir")) / 60000.0)
            dx, dy = dist * math.cos(angle), dist * math.sin(angle)
            body = " ".join(d for d, mode in pieces if mode != "nofill") or " ".join(d for d, _ in pieces)
            blur = emu(shadow.get("blurRad")) / 2
            soft = ""
            if blur > 0.05:
                name = f"f{next(_IDS)}"
                self.defs.append(f'<filter id="{name}" filterUnits="userSpaceOnUse" x="{-width - blur * 3:.2f}" y="{-height - blur * 3:.2f}" '
                                 f'width="{width * 3 + blur * 6:.2f}" height="{height * 3 + blur * 6:.2f}">'
                                 f'<feGaussianBlur stdDeviation="{blur:.3f}"/></filter>')
                soft = f' filter="url(#{name})"'
            out.append(f'<g transform="translate({dx:.2f} {dy:.2f})"{soft}><path d="{body}" fill="#{shadow_color[0]}" '
                       f'fill-opacity="{shadow_color[1]:.3f}" stroke="none"/></g>')
        found = re.fullmatch('fill="url[(]#(p[0-9]+)[)]"', paint)
        if found and found.group(1) in self.patterns:
            # Edge would print a pattern blurred: the dots go in as one image, cut to the outline.
            rows, fore, back = self.patterns[found.group(1)]
            clip = f"c{next(_IDS)}"
            body = " ".join(d for d, mode in pieces if mode != "nofill")
            self.defs.append(f'<clipPath id="{clip}"><path d="{body}" clip-rule="evenodd"/></clipPath>')
            out.append(f'<image href="{_pattern_tile(rows, fore, back, size=(width, height))}" width="{width:.3f}" height="{height:.3f}" '
                       f'preserveAspectRatio="none" style="image-rendering:pixelated" clip-path="url(#{clip})"/>')
            paint = 'fill="none"'
        compound = self._compound(line_el, base_line)
        if compound and line_width > 0:
            return "".join(out) + painted_pieces(pieces, paint, 'stroke="none"') + self._compound_lines(pieces, stroke, line_width, compound)
        return "".join(out) + painted_pieces(pieces, paint, stroke)

    def _shadow_of(self, sp_pr, style):
        """A shape's outer shadow and its colour: its own effects, or else the theme's
        effect style its style picks."""
        effects = sp_pr.find(A + "effectLst") if sp_pr is not None else None
        placeholder = None
        if effects is None and style is not None:
            ref = style.find(A + "effectRef")
            index = int(_number(ref.get("idx"))) if ref is not None else 0
            if 0 < index <= len(self.palette.effects) and self.palette.effects[index - 1] is not None:
                found = self.palette.first_color(ref)
                placeholder = found[0] if found else None
                effects = self.palette.effects[index - 1].find(A + "effectLst")
        shadow = effects.find(A + "outerShdw") if effects is not None else None
        if shadow is None:
            return None, None
        return shadow, self.palette.first_color(shadow, placeholder)

    @staticmethod
    def _compound(line, base) -> str:
        for source in (line, base):
            if source is not None and source.get("cmpd"):
                return "" if source.get("cmpd") == "sng" else source.get("cmpd")
        return ""

    @staticmethod
    def _compound_lines(pieces, stroke: str, width: float, kind: str) -> str:
        """A double or triple line: thinner lines side by side across the line's width,
        each at its offset from the middle (to the left of the way the line runs)."""
        bands = {"dbl": ((1 / 3, 1 / 3), (-1 / 3, 1 / 3)), "thickThin": ((0.2, 0.6), (-0.4, 0.2)),
                 "thinThick": ((0.4, 0.2), (-0.2, 0.6)), "tri": ((5 / 12, 1 / 6), (0.0, 1 / 3), (-5 / 12, 1 / 6))}.get(kind)
        if not bands:
            return ""
        out = []
        base = re.sub(' (marker-start|marker-end)="[^"]*"', "", stroke)
        for d, mode in pieces:
            if mode == "nostroke" or mode in SHADES:
                continue
            for points, closed in _subpaths(d):
                for offset, share in bands:
                    moved = _offset_line(points, closed, offset * width)
                    if len(moved) < 2:
                        continue
                    path = "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in moved) + ("Z" if closed else "")
                    out.append(f'<path d="{path}" fill="none" ' + re.sub('stroke-width="[0-9.]+"', f'stroke-width="{share * width:.3f}"', base) + "/>")
        return "".join(out)

    def _merged_stroke(self, line, base, placeholder, default_line) -> str:
        """A shape's own line settings over the line its style picks."""
        if line is None and base is None:
            return self.stroke(None, default_color=default_line)
        if line is None:
            return self.stroke(base, placeholder, default_color=None)
        if line.find(A + "noFill") is not None:
            return 'stroke="none"'
        if base is not None and line.find(A + "solidFill") is None and line.find(A + "gradFill") is None:
            colored = self.palette.first_color(base.find(A + "solidFill"), placeholder) if base.find(A + "solidFill") is not None else None
            fallback = colored[0] if colored else None
            width = emu(base.get("w"), 0.75)
            return self.stroke(line, placeholder, default_width=width, default_color=fallback)
        return self.stroke(line, placeholder)


def _shortened(d: str, cuts: tuple) -> str:
    """A line made of straight pieces, pulled back from its ends by ``cuts``."""
    if any(c in d for c in "CQAZ") or d.count("M") != 1:
        return d
    numbers = [float(v) for v in re.findall("-?[0-9]*[.]?[0-9]+", d)]
    points = [(numbers[i], numbers[i + 1]) for i in range(0, len(numbers) - 1, 2)]
    if len(points) < 2:
        return d
    for at, cut in ((0, cuts[0]), (-1, cuts[1])):
        if cut <= 0:
            continue
        ends = (points[0], points[1]) if at == 0 else (points[-1], points[-2])
        (x0, y0), (x1, y1) = ends
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= cut:
            continue
        moved = (x0 + (x1 - x0) * cut / length, y0 + (y1 - y0) * cut / length)
        points[at] = moved
    return "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points)


def _subpaths(d: str) -> list:
    """A path's pieces as (points, closed), its curves sampled."""
    out = []
    for part in re.split("(?=M)", d):
        if not part.strip():
            continue
        closed = "Z" in part
        points = outline_points([(part.replace("Z", "") + "Z", None)], keep_short=True)
        if points:
            out.append((points[0], closed))
    return out


def _offset_line(points, closed: bool, distance: float) -> list:
    """A polyline moved sideways by ``distance`` (to the left of its direction), mitred."""
    count = len(points)
    if count < 2 or not distance:
        return list(points)
    normals = []
    for i in range(count - (0 if closed else 1)):
        (x0, y0), (x1, y1) = points[i], points[(i + 1) % count]
        length = math.hypot(x1 - x0, y1 - y0) or 1.0
        normals.append(((y1 - y0) / length, -(x1 - x0) / length))
    out = []
    for i in range(count):
        before = normals[i - 1] if (closed or i > 0) else None
        after = normals[i] if i < len(normals) else None
        if before is None:
            nx, ny = after
        elif after is None:
            nx, ny = before
        else:
            nx, ny = before[0] + after[0], before[1] + after[1]
            size = math.hypot(nx, ny)
            if size < 1e-6:
                nx, ny = after
            else:
                nx, ny = nx / size, ny / size
                cos = nx * after[0] + ny * after[1]
                scale = 1.0 / max(cos, 0.25)
                nx, ny = nx * scale, ny * scale
        out.append((points[i][0] + nx * distance, points[i][1] + ny * distance))
    return out


def _pattern_tile(rows: str, fore, back, scale: int = 4, size=None) -> str:
    """An 8 by 8 pattern as a PNG data URI, each dot ``scale`` pixels square: one tile,
    or with ``size`` (in points) the whole of a shape that size, a dot to 0.75pt."""
    import base64
    import struct
    import zlib

    def rgba(found):
        color, alpha = found
        return bytes(int(color[i:i + 2], 16) for i in (0, 2, 4)) + bytes([int(round(alpha * 255))])
    ink, paper = rgba(fore), rgba(back)
    across, down = 8, 8
    if size:
        across, down = max(1, int(math.ceil(size[0] / 0.75))), max(1, int(math.ceil(size[1] / 0.75)))
        scale = 2 if across * down * 4 <= 4000000 else 1
    lines = []
    for y in range(down):
        bits = int(rows[(y % 8) * 2:(y % 8) * 2 + 2], 16)
        line = b"".join((ink if bits & (0x80 >> (x % 8)) else paper) * scale for x in range(across))
        lines.extend([bytes([0]) + line] * scale)
    wide, tall = across * scale, down * scale

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    png = (bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + chunk(b"IHDR", struct.pack(">IIBBBBB", wide, tall, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(lines))) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def painted_pieces(pieces, paint: str, stroke: str) -> str:
    """The parts of an outline as SVG: each says how it takes the shape's fill and line."""
    out = []
    for d, mode in pieces:
        if mode == "nofill":
            out.append(f'<path d="{d}" fill="none" {stroke}/>')
        elif mode == "nostroke":
            out.append(f'<path d="{d}" {paint} fill-rule="evenodd" stroke="none"/>')
        elif mode in ("evenodd", "both"):
            out.append(f'<path d="{d}" {paint} fill-rule="evenodd" {stroke}/>')
        elif mode and mode.removesuffix("+s") in SHADES:
            shade, opacity = SHADES[mode.removesuffix("+s")]
            edge = stroke if mode.endswith("+s") else 'stroke="none"'
            out.append(f'<path d="{d}" {paint} fill-rule="evenodd" stroke="none"/>'
                       f'<path d="{d}" fill="{shade}" fill-opacity="{opacity}" fill-rule="evenodd" {edge}/>')
        else:
            out.append(f'<path d="{d}" {paint} {stroke}/>')
    return "".join(out)


def _solid(found) -> str:
    color, alpha = found
    return f'fill="#{color}"' + (f' fill-opacity="{alpha:.3f}"' if alpha < 1 else "")


def _shadow(sp_pr):
    if sp_pr is None:
        return None
    effects = sp_pr.find(A + "effectLst")
    return effects.find(A + "outerShdw") if effects is not None else None


# -- geometry ----------------------------------------------------------------------------

def geometry(sp_pr, width: float, height: float) -> list:
    """A shape's outline as [(SVG path, mode)], from its preset or custom geometry."""
    if sp_pr is not None:
        custom = sp_pr.find(A + "custGeom")
        if custom is not None:
            found = _custom_geometry(custom, width, height)
            if found:
                return found
        preset = sp_pr.find(A + "prstGeom")
        if preset is not None:
            return preset_paths(preset.get("prst") or "rect", width, height, _adjustments(preset))
    return preset_paths("rect", width, height, {})


def _adjustments(geometry_el) -> dict:
    values = {}
    for guide in geometry_el.iter(A + "gd"):
        parts = (guide.get("fmla") or "").split()
        if len(parts) == 2 and parts[0] == "val":
            values[guide.get("name")] = _number(parts[1])
    return values


def _pts(points) -> str:
    return "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points) + "Z"


def _open(points) -> str:
    return "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points)


def _ellipse(cx, cy, rx, ry) -> str:
    return (f"M{cx - rx:.3f} {cy:.3f}A{rx:.3f} {ry:.3f} 0 1 1 {cx + rx:.3f} {cy:.3f}"
            f"A{rx:.3f} {ry:.3f} 0 1 1 {cx - rx:.3f} {cy:.3f}Z")


def _round_rect(w, h, r, x=0.0, y=0.0) -> str:
    return (f"M{x + r:.3f} {y:.3f}L{x + w - r:.3f} {y:.3f}A{r:.3f} {r:.3f} 0 0 1 {x + w:.3f} {y + r:.3f}"
            f"L{x + w:.3f} {y + h - r:.3f}A{r:.3f} {r:.3f} 0 0 1 {x + w - r:.3f} {y + h:.3f}"
            f"L{x + r:.3f} {y + h:.3f}A{r:.3f} {r:.3f} 0 0 1 {x:.3f} {y + h - r:.3f}"
            f"L{x:.3f} {y + r:.3f}A{r:.3f} {r:.3f} 0 0 1 {x + r:.3f} {y:.3f}Z")


def _regular(n, w, h, start=-90.0, hf=1.0, vf=1.0, low=1.0) -> str:
    """A regular polygon; ``low`` moves its centre down with a stretched height."""
    cx, cy = w / 2, h / 2
    return _pts((cx + cx * hf * math.cos(math.radians(start + 360.0 * i / n)),
                 cy * low + cy * vf * math.sin(math.radians(start + 360.0 * i / n))) for i in range(n))


def _star(n, w, h, inner, hf=1.0, vf=1.0, cy_factor=1.0) -> str:
    cx, cy = w / 2, h / 2 * cy_factor
    rx, ry = w / 2 * hf, h / 2 * vf
    points = []
    for i in range(2 * n):
        angle = math.radians(-90.0 + 180.0 * i / n)
        scale = 1.0 if i % 2 == 0 else inner
        points.append((cx + rx * scale * math.cos(angle), cy + ry * scale * math.sin(angle)))
    return _pts(points)


def _arc_point(cx, cy, rx, ry, degrees):
    """A point on an ellipse, at DrawingML's visual angle."""
    t = math.radians(degrees)
    t = math.atan2(rx * math.sin(t), ry * math.cos(t))
    return cx + rx * math.cos(t), cy + ry * math.sin(t)


def _callout_rect(w, h, a1, a2, radius=0.0) -> str:
    x, y = w / 2 + w * a1 / 100000.0, h / 2 + h * a2 / 100000.0
    dx, dy = w * a1 / 100000.0, h * a2 / 100000.0
    vertical = abs(dy) - abs(dx * h / w if w else 0) > 0
    r = radius
    d = [f"M{r:.3f} 0"]
    if vertical and dy < 0:
        a, b = (w * 7 / 12, w * 10 / 12) if dx > 0 else (w * 2 / 12, w * 5 / 12)
        d.append(f"L{a:.3f} 0L{x:.3f} {y:.3f}L{b:.3f} 0")
    d.append(f"L{w - r:.3f} 0")
    if r:
        d.append(f"A{r:.3f} {r:.3f} 0 0 1 {w:.3f} {r:.3f}")
    if not vertical and dx > 0:
        a, b = (h * 7 / 12, h * 10 / 12) if dy > 0 else (h * 2 / 12, h * 5 / 12)
        d.append(f"L{w:.3f} {a:.3f}L{x:.3f} {y:.3f}L{w:.3f} {b:.3f}")
    d.append(f"L{w:.3f} {h - r:.3f}")
    if r:
        d.append(f"A{r:.3f} {r:.3f} 0 0 1 {w - r:.3f} {h:.3f}")
    if vertical and dy > 0:
        a, b = (w * 10 / 12, w * 7 / 12) if dx > 0 else (w * 5 / 12, w * 2 / 12)
        d.append(f"L{a:.3f} {h:.3f}L{x:.3f} {y:.3f}L{b:.3f} {h:.3f}")
    d.append(f"L{r:.3f} {h:.3f}")
    if r:
        d.append(f"A{r:.3f} {r:.3f} 0 0 1 0 {h - r:.3f}")
    if not vertical and dx <= 0:
        a, b = (h * 10 / 12, h * 7 / 12) if dy > 0 else (h * 5 / 12, h * 2 / 12)
        d.append(f"L0 {a:.3f}L{x:.3f} {y:.3f}L0 {b:.3f}")
    d.append(f"L0 {r:.3f}")
    if r:
        d.append(f"A{r:.3f} {r:.3f} 0 0 1 {r:.3f} 0")
    d.append("Z")
    return "".join(d)


def preset_paths(name: str, w: float, h: float, adj: dict) -> list:
    """A preset shape's outline at this size, as [(SVG path, how it is painted)]."""
    w, h = max(w, 0.01), max(h, 0.01)
    found = more_presets(name, w, h, adj)
    if found is not None:
        return found
    outline = OUTLINES.get(name)
    if outline and not adj:
        return scaled_outline(outline, w, h, name in CORNERED)
    found = _parametric(name, w, h, adj)
    if found is not None:
        return found
    if outline:
        return scaled_outline(outline, w, h, name in CORNERED)
    return [(_pts([(0, 0), (w, 0), (w, h), (0, h)]), None)]


def _parametric(name: str, w: float, h: float, adj: dict):
    """The plainer presets, from ECMA-376's definitions, with their adjustments."""
    ss = min(w, h)
    hc, vc = w / 2, h / 2

    def a(key="adj", default=50000.0, low=0.0, high=100000.0):
        return max(low, min(high, adj.get(key, adj.get("adj1" if key == "adj" else key, default))))

    if name in ("rect", "flowChartProcess"):
        return [(_pts([(0, 0), (w, 0), (w, h), (0, h)]), None)]
    if name in ("roundRect", "flowChartAlternateProcess"):
        r = ss * (a("adj", 16667.0, 0, 50000) if name == "roundRect" else 16667.0) / 100000.0
        return [(_round_rect(w, h, r), None)]
    if name == "round1Rect":
        r = ss * a("adj", 16667.0, 0, 50000) / 100000.0
        return [(f"M0 0L{w - r:.3f} 0A{r:.3f} {r:.3f} 0 0 1 {w:.3f} {r:.3f}L{w:.3f} {h:.3f}L0 {h:.3f}Z", None)]
    if name in ("snip1Rect", "flowChartPunchedCard"):
        x = ss * (a("adj", 16667.0, 0, 50000) if name == "snip1Rect" else 20000.0) / 100000.0
        if name == "flowChartPunchedCard":
            return [(_pts([(x, 0), (w, 0), (w, h), (0, h), (0, x)]), None)]
        return [(_pts([(0, 0), (w - x, 0), (w, x), (w, h), (0, h)]), None)]
    if name == "snip2SameRect":
        x = ss * a("adj1", 16667.0, 0, 50000) / 100000.0
        return [(_pts([(x, 0), (w - x, 0), (w, x), (w, h), (0, h), (0, x)]), None)]
    if name in ("ellipse", "flowChartConnector"):
        return [(_ellipse(hc, vc, hc, vc), None)]
    if name == "flowChartOr":
        return [(_ellipse(hc, vc, hc, vc), None), (f"M{hc:.3f} 0V{h:.3f}M0 {vc:.3f}H{w:.3f}", "nofill")]
    if name == "flowChartSummingJunction":
        dx, dy = hc * math.cos(math.radians(45)), vc * math.sin(math.radians(45))
        return [(_ellipse(hc, vc, hc, vc), None),
                (f"M{hc - dx:.3f} {vc - dy:.3f}L{hc + dx:.3f} {vc + dy:.3f}M{hc + dx:.3f} {vc - dy:.3f}L{hc - dx:.3f} {vc + dy:.3f}", "nofill")]
    if name == "triangle":
        x = w * a("adj", 50000.0) / 100000.0
        return [(_pts([(0, h), (x, 0), (w, h)]), None)]
    if name == "flowChartExtract":
        return [(_pts([(0, h), (hc, 0), (w, h)]), None)]
    if name == "flowChartMerge":
        return [(_pts([(0, 0), (w, 0), (hc, h)]), None)]
    if name == "rtTriangle":
        return [(_pts([(0, 0), (w, h), (0, h)]), None)]
    if name in ("diamond", "flowChartDecision"):
        return [(_pts([(hc, 0), (w, vc), (hc, h), (0, vc)]), None)]
    if name == "flowChartSort":
        return [(_pts([(hc, 0), (w, vc), (hc, h), (0, vc)]), None), (f"M0 {vc:.3f}H{w:.3f}", "nofill")]
    if name == "flowChartCollate":
        return [(_pts([(0, 0), (w, 0), (0, h), (w, h)]), None)]
    if name == "parallelogram":
        x = ss * a("adj", 25000.0, 0, 100000.0 * w / ss) / 100000.0
        return [(_pts([(0, h), (x, 0), (w, 0), (w - x, h)]), None)]
    if name == "flowChartInputOutput":
        return [(_pts([(0, h), (w / 5, 0), (w, 0), (w * 4 / 5, h)]), None)]
    if name == "trapezoid":
        x = ss * a("adj", 25000.0, 0, 50000.0 * w / ss) / 100000.0
        return [(_pts([(0, h), (x, 0), (w - x, 0), (w, h)]), None)]
    if name == "flowChartManualOperation":
        return [(_pts([(0, 0), (w, 0), (w * 4 / 5, h), (w / 5, h)]), None)]
    if name == "flowChartManualInput":
        return [(_pts([(0, h / 5), (w, 0), (w, h), (0, h)]), None)]
    if name == "flowChartOffpageConnector":
        return [(_pts([(0, 0), (w, 0), (w, h * 4 / 5), (hc, h), (0, h * 4 / 5)]), None)]
    if name == "pentagon":
        return [(_regular(5, w, h, hf=1.05146, vf=1.10557, low=1.10557), None)]
    if name in ("hexagon", "flowChartPreparation"):
        x = ss * (a("adj", 25000.0, 0, 50000.0 * w / ss) if name == "hexagon" else 20000.0 * w / ss) / 100000.0
        return [(_pts([(0, vc), (x, 0), (w - x, 0), (w, vc), (w - x, h), (x, h)]), None)]
    if name == "heptagon":
        return [(_regular(7, w, h, hf=1.02572, vf=1.05210, low=1.05210), None)]
    if name == "octagon":
        x = ss * a("adj", 29289.0, 0, 50000) / 100000.0
        return [(_pts([(0, x), (x, 0), (w - x, 0), (w, x), (w, h - x), (w - x, h), (x, h), (0, h - x)]), None)]
    if name == "decagon":
        return [(_regular(10, w, h, start=0.0, vf=1.05146), None)]
    if name == "dodecagon":
        return [(_regular(12, w, h, start=-75.0, hf=1.03528, vf=1.03528), None)]
    if name == "plus":
        x = ss * a("adj", 25000.0, 0, 50000) / 100000.0
        return [(_pts([(x, 0), (w - x, 0), (w - x, x), (w, x), (w, h - x), (w - x, h - x), (w - x, h), (x, h), (x, h - x),
                       (0, h - x), (0, x), (x, x)]), None)]
    stars = {"star4": (4, 12500.0, 1, 1, 1), "star5": (5, 19098.0, 1.05146, 1.10557, 1.10557), "star6": (6, 28868.0, 1.1547, 1, 1),
             "star7": (7, 34601.0, 1.02572, 1.0521, 1.0521), "star8": (8, 37500.0, 1, 1, 1), "star10": (10, 42533.0, 1.05146, 1, 1),
             "star12": (12, 37500.0, 1, 1, 1), "star16": (16, 37500.0, 1, 1, 1), "star24": (24, 37500.0, 1, 1, 1), "star32": (32, 37500.0, 1, 1, 1)}
    if name in stars:
        n, default, hf, vf, cy = stars[name]
        return [(_star(n, w, h, a("adj", default, 0, 50000) / 50000.0, hf, vf, cy), None)]
    if name in ("rightArrow", "leftArrow"):
        a1 = a("adj1", 50000.0)
        dx = ss * a("adj2", 50000.0, 0, 100000.0 * w / ss) / 100000.0
        dy = h * a1 / 200000.0
        pts = [(0, vc - dy), (w - dx, vc - dy), (w - dx, 0), (w, vc), (w - dx, h), (w - dx, vc + dy), (0, vc + dy)]
        if name == "leftArrow":
            pts = [(w - x, y) for x, y in pts]
        return [(_pts(pts), None)]
    if name in ("downArrow", "upArrow"):
        a1 = a("adj1", 50000.0)
        dy = ss * a("adj2", 50000.0, 0, 100000.0 * h / ss) / 100000.0
        dx = w * a1 / 200000.0
        pts = [(hc - dx, 0), (hc + dx, 0), (hc + dx, h - dy), (w, h - dy), (hc, h), (0, h - dy), (hc - dx, h - dy)]
        if name == "upArrow":
            pts = [(x, h - y) for x, y in pts]
        return [(_pts(pts), None)]
    if name == "leftRightArrow":
        dx = ss * a("adj2", 50000.0, 0, 50000.0 * w / ss) / 100000.0
        dy = h * a("adj1", 50000.0) / 200000.0
        return [(_pts([(0, vc), (dx, 0), (dx, vc - dy), (w - dx, vc - dy), (w - dx, 0), (w, vc), (w - dx, h), (w - dx, vc + dy),
                       (dx, vc + dy), (dx, h)]), None)]
    if name == "upDownArrow":
        dy = ss * a("adj2", 50000.0, 0, 50000.0 * h / ss) / 100000.0
        dx = w * a("adj1", 50000.0) / 200000.0
        return [(_pts([(hc, 0), (w, dy), (hc + dx, dy), (hc + dx, h - dy), (w, h - dy), (hc, h), (0, h - dy), (hc - dx, h - dy),
                       (hc - dx, dy), (0, dy)]), None)]
    if name == "notchedRightArrow":
        dx = ss * a("adj2", 50000.0, 0, 100000.0 * w / ss) / 100000.0
        dy = h * a("adj1", 50000.0) / 200000.0
        notch = dy * dx / vc
        return [(_pts([(0, vc - dy), (w - dx, vc - dy), (w - dx, 0), (w, vc), (w - dx, h), (w - dx, vc + dy), (0, vc + dy), (notch, vc)]), None)]
    if name == "chevron":
        x = ss * a("adj", 50000.0, 0, 100000.0 * w / ss) / 100000.0
        return [(_pts([(0, 0), (w - x, 0), (w, vc), (w - x, h), (0, h), (x, vc)]), None)]
    if name == "homePlate":
        x = ss * a("adj", 50000.0, 0, 100000.0 * w / ss) / 100000.0
        return [(_pts([(0, 0), (w - x, 0), (w, vc), (w - x, h), (0, h)]), None)]
    if name in ("line", "straightConnector1", "lineInv"):
        if name == "lineInv":
            return [(_open([(0, h), (w, 0)]), "nofill")]
        return [(_open([(0, 0), (w, h)]), "nofill")]
    if name == "bentConnector2":
        return [(_open([(0, 0), (w, 0), (w, h)]), "nofill")]
    if name == "bentConnector3":
        x = w * adj.get("adj1", 50000.0) / 100000.0
        return [(_open([(0, 0), (x, 0), (x, h), (w, h)]), "nofill")]
    if name == "bentConnector4":
        x = w * adj.get("adj1", 50000.0) / 100000.0
        y = h * adj.get("adj2", 50000.0) / 100000.0
        return [(_open([(0, 0), (x, 0), (x, y), (w, y), (w, h)]), "nofill")]
    if name == "bentConnector5":
        x1, y, x2 = w * adj.get("adj1", 50000.0) / 100000.0, h * adj.get("adj2", 50000.0) / 100000.0, w * adj.get("adj3", 50000.0) / 100000.0
        return [(_open([(0, 0), (x1, 0), (x1, y), (x2, y), (x2, h), (w, h)]), "nofill")]
    if name == "curvedConnector2":
        return [(f"M0 0C{hc:.3f} 0 {w:.3f} {vc:.3f} {w:.3f} {h:.3f}", "nofill")]
    if name == "curvedConnector3":
        x = w * adj.get("adj1", 50000.0) / 100000.0
        return [(f"M0 0C{x / 2:.3f} 0 {x:.3f} {h / 4:.3f} {x:.3f} {vc:.3f}C{x:.3f} {h * 3 / 4:.3f} {(x + w) / 2:.3f} {h:.3f} {w:.3f} {h:.3f}", "nofill")]
    if name == "wedgeRectCallout":
        return [(_callout_rect(w, h, adj.get("adj1", -20833.0), adj.get("adj2", 62500.0)), None)]
    if name == "wedgeRoundRectCallout":
        return [(_callout_rect(w, h, adj.get("adj1", -20833.0), adj.get("adj2", 62500.0), ss * adj.get("adj3", 16667.0) / 100000.0), None)]
    if name == "wedgeEllipseCallout":
        x, y = hc + w * adj.get("adj1", -20833.0) / 100000.0, vc + h * adj.get("adj2", 62500.0) / 100000.0
        angle = math.degrees(math.atan2(y - vc, x - hc))
        one = _arc_point(hc, vc, hc, vc, angle - 11)
        two = _arc_point(hc, vc, hc, vc, angle + 11)
        return [(f"M{one[0]:.3f} {one[1]:.3f}L{x:.3f} {y:.3f}L{two[0]:.3f} {two[1]:.3f}A{hc:.3f} {vc:.3f} 0 1 1 {one[0]:.3f} {one[1]:.3f}Z", None)]
    if name == "flowChartPredefinedProcess":
        return [(_pts([(0, 0), (w, 0), (w, h), (0, h)]), None), (f"M{w / 8:.3f} 0V{h:.3f}M{w * 7 / 8:.3f} 0V{h:.3f}", "nofill")]
    if name == "flowChartInternalStorage":
        return [(_pts([(0, 0), (w, 0), (w, h), (0, h)]), None), (f"M{w / 8:.3f} 0V{h:.3f}M0 {h / 8:.3f}H{w:.3f}", "nofill")]
    if name == "flowChartDocument":
        y = h * 17322 / 21600
        return [(f"M0 0H{w:.3f}V{y:.3f}C{w / 2:.3f} {y:.3f} {w / 2:.3f} {h * 23922 / 21600:.3f} 0 {h * 20172 / 21600:.3f}Z", None)]
    if name == "flowChartMultidocument":
        y = h * 0.78
        body = f"M0 {h * .15:.3f}H{w * .85:.3f}V{y:.3f}C{w * .45:.3f} {y:.3f} {w * .4:.3f} {h * 1.08:.3f} 0 {h * .93:.3f}Z"
        back = f"M{w * .07:.3f} {h * .15:.3f}V{h * .07:.3f}H{w * .93:.3f}V{h * .72:.3f}H{w * .85:.3f}M{w * .15:.3f} {h * .07:.3f}V0H{w:.3f}V{h * .65:.3f}H{w * .93:.3f}"
        return [(body, None), (back, "nofill")]
    if name == "flowChartTerminator":
        rx, ry = w * 3475 / 21600, vc
        return [(f"M{rx:.3f} 0H{w - rx:.3f}A{rx:.3f} {ry:.3f} 0 0 1 {w - rx:.3f} {h:.3f}H{rx:.3f}A{rx:.3f} {ry:.3f} 0 0 1 {rx:.3f} 0Z", None)]
    if name == "flowChartDelay":
        return [(f"M0 0H{hc:.3f}A{hc:.3f} {vc:.3f} 0 0 1 {hc:.3f} {h:.3f}H0Z", None)]
    if name == "flowChartDisplay":
        return [(f"M0 {vc:.3f}L{w / 6:.3f} 0H{w * 5 / 6:.3f}A{w / 6:.3f} {vc:.3f} 0 0 1 {w * 5 / 6:.3f} {h:.3f}H{w / 6:.3f}Z", None)]
    if name == "flowChartPunchedTape":
        return [(f"M0 {h / 10:.3f}C{w / 4:.3f} {-h / 10:.3f} {w / 4:.3f} {h * 3 / 10:.3f} {hc:.3f} {h / 10:.3f}"
                 f"C{w * 3 / 4:.3f} {-h / 10:.3f} {w * 3 / 4:.3f} {h * 3 / 10:.3f} {w:.3f} {h / 10:.3f}"
                 f"V{h * 9 / 10:.3f}C{w * 3 / 4:.3f} {h * 11 / 10:.3f} {w * 3 / 4:.3f} {h * 7 / 10:.3f} {hc:.3f} {h * 9 / 10:.3f}"
                 f"C{w / 4:.3f} {h * 11 / 10:.3f} {w / 4:.3f} {h * 7 / 10:.3f} 0 {h * 9 / 10:.3f}Z", None)]
    if name == "heart":
        dx1, dx2 = w * 49 / 48, w * 10 / 48
        y1 = -h / 3
        return [(f"M{hc:.3f} {h / 4:.3f}C{hc + dx2:.3f} {y1:.3f} {hc + dx1:.3f} {h / 4:.3f} {hc:.3f} {h:.3f}"
                 f"C{hc - dx1:.3f} {h / 4:.3f} {hc - dx2:.3f} {y1:.3f} {hc:.3f} {h / 4:.3f}Z", None)]
    if name == "lightningBolt":
        pts = [(8472, 0), (12860, 6080), (11050, 6797), (16577, 12007), (14767, 12877), (21600, 21600), (10012, 14915),
               (12222, 13987), (5022, 9705), (7602, 8382), (0, 3890)]
        return [(_pts([(x * w / 21600, y * h / 21600) for x, y in pts]), None)]
    if name == "sun":
        rays, inner = [], a("adj", 25000.0, 12500, 46875) / 100000.0
        for i in range(8):
            angle = math.radians(45.0 * i)
            cos, sin = math.cos(angle), math.sin(angle)
            spread = 0.14
            base = 0.72
            rays.append((hc + hc * cos, vc + vc * sin))
            rays.append((hc + hc * base * math.cos(angle + spread), vc + vc * base * math.sin(angle + spread)))
            rays.append((hc + hc * base * math.cos(angle - spread), vc + vc * base * math.sin(angle - spread)))
        d = "".join(_pts(rays[i:i + 3]) for i in range(0, 24, 3))
        radius = 0.5 - inner + 0.1
        return [(d + _ellipse(hc, vc, w * radius, h * radius), None)]
    if name == "moon":
        x = ss * a("adj", 50000.0, 0, 87500) / 100000.0
        return [(f"M{w:.3f} {h:.3f}A{w:.3f} {vc:.3f} 0 0 1 {w:.3f} 0A{w - x:.3f} {vc:.3f} 0 0 0 {w:.3f} {h:.3f}Z", None)]
    if name == "cloud":
        bumps = [(0.22, 0.55, 0.18, 0.2), (0.32, 0.3, 0.16, 0.2), (0.52, 0.22, 0.2, 0.2), (0.74, 0.3, 0.18, 0.22), (0.84, 0.52, 0.16, 0.2),
                 (0.72, 0.74, 0.2, 0.2), (0.48, 0.8, 0.22, 0.2), (0.26, 0.74, 0.17, 0.17)]
        outline = "".join(_ellipse(x * w, y * h, rx * w, ry * h) for x, y, rx, ry in bumps) + _ellipse(hc, h * .52, w * .3, h * .28)
        return [(outline, None), (outline, "nostroke")]      # the fill on top hides the inner strokes
    if name == "donut":
        d = ss * a("adj", 25000.0, 0, 50000) / 100000.0
        return [(_ellipse(hc, vc, hc, vc) + _ellipse(hc, vc, hc - d, vc - d), "evenodd")]
    if name == "frame":
        d = ss * a("adj1", 12500.0, 0, 50000) / 100000.0
        return [(_pts([(0, 0), (w, 0), (w, h), (0, h)]) + _pts([(d, d), (d, h - d), (w - d, h - d), (w - d, d)]), "evenodd")]
    if name == "halfFrame":
        dx, dy = ss * a("adj2", 33333.0) / 100000.0, ss * a("adj1", 33333.0) / 100000.0
        return [(_pts([(0, 0), (w, 0), (w - dy, dy), (dx, dy), (dx, h - dx), (0, h)]), None)]
    if name == "corner":
        dx, dy = ss * a("adj2", 50000.0) / 100000.0, ss * a("adj1", 50000.0) / 100000.0
        return [(_pts([(0, 0), (dx, 0), (dx, h - dy), (w, h - dy), (w, h), (0, h)]), None)]
    if name == "diagStripe":
        d = a("adj", 50000.0) / 100000.0
        return [(_pts([(0, h * d), (w * d, 0), (w, 0), (0, h)]), None)]
    if name == "teardrop":
        return [(f"M0 {vc:.3f}A{hc:.3f} {vc:.3f} 0 0 1 {hc:.3f} 0H{w:.3f}V{vc:.3f}A{hc:.3f} {vc:.3f} 0 0 1 0 {vc:.3f}Z", None)]
    if name == "plaque":
        r = ss * a("adj", 16667.0, 0, 50000) / 100000.0
        return [(f"M0 {r:.3f}A{r:.3f} {r:.3f} 0 0 0 {r:.3f} 0H{w - r:.3f}A{r:.3f} {r:.3f} 0 0 0 {w:.3f} {r:.3f}V{h - r:.3f}"
                 f"A{r:.3f} {r:.3f} 0 0 0 {w - r:.3f} {h:.3f}H{r:.3f}A{r:.3f} {r:.3f} 0 0 0 0 {h - r:.3f}Z", None)]
    if name in ("pie", "arc", "chord", "blockArc"):
        return _arcs(name, w, h, adj)
    if name == "mathMinus":
        d = h * a("adj1", 23520.0) / 200000.0
        return [(_pts([(w * .13, vc - d), (w * .87, vc - d), (w * .87, vc + d), (w * .13, vc + d)]), None)]
    if name == "mathEqual":
        d, g = h * a("adj1", 23520.0) / 100000.0, h * a("adj2", 11760.0) / 200000.0
        return [(_pts([(w * .13, vc - g - d), (w * .87, vc - g - d), (w * .87, vc - g), (w * .13, vc - g)])
                 + _pts([(w * .13, vc + g), (w * .87, vc + g), (w * .87, vc + g + d), (w * .13, vc + g + d)]), None)]
    return None


def _arcs(name: str, w: float, h: float, adj: dict) -> list:
    defaults = {"pie": (0.0, 16200000.0), "arc": (16200000.0, 0.0), "chord": (2700000.0, 16200000.0), "blockArc": (10800000.0, 0.0)}
    first, second = defaults[name]
    start, end = adj.get("adj1", first) / 60000.0, adj.get("adj2", second) / 60000.0
    hc, vc = w / 2, h / 2
    x1, y1 = _arc_point(hc, vc, hc, vc, start)
    x2, y2 = _arc_point(hc, vc, hc, vc, end)
    sweep = (end - start) % 360.0
    large = 1 if sweep > 180 else 0
    outer = f"M{x1:.3f} {y1:.3f}A{hc:.3f} {vc:.3f} 0 {large} 1 {x2:.3f} {y2:.3f}"
    if name == "pie":
        return [(f"{outer}L{hc:.3f} {vc:.3f}Z", None)]
    if name == "chord":
        return [(f"{outer}Z", None)]
    if name == "arc":
        return [(f"{outer}L{hc:.3f} {vc:.3f}Z", "nostroke"), (outer, "nofill")]
    band = min(w, h) * adj.get("adj3", 25000.0) / 100000.0
    rx, ry = max(0.01, hc - band), max(0.01, vc - band)
    x3, y3 = _arc_point(hc, vc, rx, ry, end)
    x4, y4 = _arc_point(hc, vc, rx, ry, start)
    return [(f"{outer}L{x3:.3f} {y3:.3f}A{rx:.3f} {ry:.3f} 0 {large} 0 {x4:.3f} {y4:.3f}Z", None)]


def text_area(sp_pr, w: float, h: float) -> tuple:
    """The part of a shape text sits in: (left, top, right, bottom)."""
    name = "rect"
    adj = {}
    if sp_pr is not None and sp_pr.find(A + "prstGeom") is not None:
        preset = sp_pr.find(A + "prstGeom")
        name = preset.get("prst") or "rect"
        adj = _adjustments(preset)
    found = _text_formula(name, w, h, adj)
    if found is not None:
        return found
    area = TEXT_AREAS.get(name)
    if area is not None:
        return area[0] * w / 1000.0, area[1] * h / 1000.0, area[2] * w / 1000.0, area[3] * h / 1000.0
    return 0.0, 0.0, w, h


def _text_formula(name: str, w: float, h: float, adj: dict):
    """The text area of the shapes whose handles or proportions move it, from their
    definitions; ``TEXT_AREAS`` has the rest, as Word places them at their usual settings."""
    ss = max(min(w, h), 0.01)
    hc, vc = w / 2, h / 2

    def a(key="adj", default=50000.0):
        return adj.get(key, adj.get("adj1" if key == "adj" else key, default))

    if name in ("ellipse", "flowChartConnector", "flowChartOr", "flowChartSummingJunction", "wedgeEllipseCallout", "donut"):
        dx, dy = hc * (1 - 0.70711), vc * (1 - 0.70711)
        return dx, dy, w - dx, h - dy
    if name in ("roundRect", "flowChartAlternateProcess", "wedgeRoundRectCallout"):
        key, default = ("adj3", 16667.0) if name == "wedgeRoundRectCallout" else ("adj", 16667.0)
        d = ss * (16667.0 if name == "flowChartAlternateProcess" else a(key, default)) / 100000.0 * 0.29289
        return d, d, w - d, h - d
    if name == "round1Rect":
        return 0.0, 0.0, w - ss * a("adj", 16667.0) / 100000.0 * 0.29289, h
    if name == "round2SameRect":
        top, low = ss * a("adj1", 16667.0) / 100000.0 * 0.29289, ss * a("adj2", 0.0) / 100000.0 * 0.29289
        side = max(top, low)
        return side, top, w - side, h - low
    if name == "round2DiagRect":
        d = ss * max(a("adj1", 16667.0), a("adj2", 0.0)) / 100000.0 * 0.29289
        return d, d, w - d, h - d
    if name == "snip1Rect":
        d = ss * a("adj", 16667.0) / 200000.0
        return 0.0, d, w - d, h
    if name == "snip2SameRect":
        top, low = ss * a("adj1", 16667.0) / 200000.0, ss * a("adj2", 0.0) / 200000.0
        side = max(top, low)
        return side, top, w - side, h - low
    if name == "snip2DiagRect":
        d = ss * max(a("adj1", 0.0), a("adj2", 16667.0)) / 200000.0
        return d, d, w - d, h - d
    if name == "snipRoundRect":
        d = ss * a("adj1", 16667.0) / 100000.0 * 0.29289
        return d, d, w - ss * a("adj2", 16667.0) / 200000.0, h
    if name in ("diamond", "flowChartDecision", "flowChartSort", "flowChartCollate"):
        return w / 4, h / 4, w * 3 / 4, h * 3 / 4
    if name == "triangle":
        left = w * a("adj", 50000.0) / 200000.0
        return left, vc, left + hc, h
    if name == "flowChartExtract":
        return w / 4, vc, w * 3 / 4, h
    if name in ("flowChartMerge", "flowChartOfflineStorage"):
        return w / 4, 0.0, w * 3 / 4, vc
    if name == "rtTriangle":
        return w / 12, h * 7 / 12, w * 7 / 12, h * 11 / 12
    if name == "parallelogram":
        q = (1 + 5 * a("adj", 25000.0) / (100000.0 * w / ss)) / 12
        return q * w, q * h, w - q * w, h - q * h
    if name == "flowChartInputOutput":
        return w / 5, 0.0, w * 4 / 5, h
    if name == "flowChartManualOperation":
        return w / 5, 0.0, w * 4 / 5, h
    if name == "trapezoid":
        part = a("adj", 25000.0) / (50000.0 * w / ss) / 3
        return w * part, h * part, w - w * part, h
    if name == "hexagon":
        limit = 50000.0 * w / ss
        value = max(0.0, min(limit, a("adj", 25000.0)))
        half = -limit / 2
        above = value + half > 0
        q6 = (value + (half if above else 0.0)) / half
        part = ((4.0 if above else 2.0) - q6 * (3.0 if above else 2.0)) / 24.0
        return w * part, h * part, w - w * part, h - h * part
    if name == "octagon":
        d = ss * a("adj", 29289.0) / 200000.0
        return d, d, w - d, h - d
    if name == "plaque":
        d = ss * a("adj", 16667.0) / 100000.0 * 0.70711
        return d, d, w - d, h - d
    if name in ("rightArrow", "leftArrow"):
        head = ss * max(0.0, min(100000.0 * w / ss, a("adj2", 50000.0))) / 100000.0
        half = h * max(0.0, min(100000.0, a("adj1", 50000.0))) / 200000.0
        into = (vc - half) * head / vc
        if name == "rightArrow":
            return 0.0, vc - half, w - head + into, vc + half
        return head - into, vc - half, w, vc + half
    if name in ("downArrow", "upArrow"):
        head = ss * max(0.0, min(100000.0 * h / ss, a("adj2", 50000.0))) / 100000.0
        half = w * max(0.0, min(100000.0, a("adj1", 50000.0))) / 200000.0
        into = (hc - half) * head / hc
        if name == "downArrow":
            return hc - half, 0.0, hc + half, h - head + into
        return hc - half, head - into, hc + half, h
    if name == "leftRightArrow":
        head = ss * max(0.0, min(50000.0 * w / ss, a("adj2", 50000.0))) / 100000.0
        half = h * max(0.0, min(100000.0, a("adj1", 50000.0))) / 200000.0
        into = (vc - half) * head / vc
        return head - into, vc - half, w - head + into, vc + half
    if name == "upDownArrow":
        head = ss * max(0.0, min(50000.0 * h / ss, a("adj2", 50000.0))) / 100000.0
        half = w * max(0.0, min(100000.0, a("adj1", 50000.0))) / 200000.0
        into = (hc - half) * head / hc
        return hc - half, head - into, hc + half, h - head + into
    if name == "notchedRightArrow":
        head = ss * max(0.0, min(100000.0 * w / ss, a("adj2", 50000.0))) / 100000.0
        half = h * max(0.0, min(100000.0, a("adj1", 50000.0))) / 200000.0
        return half * head / vc, vc - half, w - head + (vc - half) * head / vc, vc + half
    if name == "chevron":
        x = ss * max(0.0, min(100000.0 * w / ss, a("adj", 50000.0))) / 100000.0
        return (x, 0.0, w - x, h) if w - x * 2 > 0 else (0.0, 0.0, w, h)
    if name == "homePlate":
        return 0.0, 0.0, w - ss * a("adj", 50000.0) / 200000.0, h
    if name == "flowChartTerminator":
        d = w * 1018 / 21600
        return d, h * 3163 / 21600, w - d, h * 18437 / 21600
    if name == "flowChartDocument":
        return 0.0, 0.0, w, h * 17322 / 21600
    if name == "flowChartPredefinedProcess":
        return w / 8, 0.0, w * 7 / 8, h
    if name == "flowChartInternalStorage":
        return w / 8, h / 8, w, h
    if name == "flowChartMagneticDisk":
        return 0.0, h / 3, w, h * 5 / 6
    if name == "can":
        y = ss * a("adj", 25000.0) / 200000.0
        return 0.0, y * 2, w, h - y
    if name == "cube":
        y = ss * a("adj", 25000.0) / 100000.0
        return 0.0, y, w - y, h
    if name == "frame":
        d = ss * a("adj1", 12500.0) / 100000.0
        return d, d, w - d, h - d
    if name == "bevel":
        d = ss * a("adj", 12500.0) / 100000.0
        return d, d, w - d, h - d
    if name == "foldedCorner":
        return 0.0, 0.0, w, h - ss * a("adj", 16667.0) / 100000.0
    if name == "plus":
        x = ss * a("adj", 25000.0) / 100000.0
        return x, 0.0, w - x, h
    if name in ("verticalScroll", "horizontalScroll"):
        d = ss * a("adj", 12500.0) / 100000.0
        if name == "verticalScroll":
            return d, d, w - d, h - d * 0.53
        return d, d, w - d * 0.53, h - d
    if name == "wave":
        y = h * a("adj1", 12500.0) / 100000.0 * 2
        return 0.0, y, w, h - y
    if name == "doubleWave":
        y = h * a("adj1", 6250.0) / 100000.0 * 2
        return 0.0, y, w, h - y
    return None


_PATH_TOKENS = re.compile("[MLHVCQAZ]|-?[0-9]*[.]?[0-9]+(?:e-?[0-9]+)?")


def outline_points(pieces, steps: int = 12, keep_short: bool = False) -> list:
    """The filled parts of an outline as polygons of points, curves and arcs sampled
    (with ``keep_short``, a piece of two points counts too)."""
    least = 1 if keep_short else 2
    polygons = []
    for d, mode in pieces:
        if mode == "nofill":
            continue
        tokens = _PATH_TOKENS.findall(d)
        index, command, current, start, points = 0, "M", (0.0, 0.0), (0.0, 0.0), []

        def take(count):
            nonlocal index
            values = [float(v) for v in tokens[index:index + count]]
            index += count
            return values
        while index < len(tokens):
            if tokens[index].isalpha():
                command = tokens[index]
                index += 1
                if command == "Z":
                    if len(points) > least:
                        polygons.append(points)
                    points, current = [], start
                    continue
            if command == "M":
                if len(points) > least:
                    polygons.append(points)
                current = start = tuple(take(2))
                points = [current]
                command = "L"
            elif command == "L":
                current = tuple(take(2))
                points.append(current)
            elif command == "H":
                current = (take(1)[0], current[1])
                points.append(current)
            elif command == "V":
                current = (current[0], take(1)[0])
                points.append(current)
            elif command in ("C", "Q"):
                values = take(6 if command == "C" else 4)
                controls = [current] + [tuple(values[i:i + 2]) for i in range(0, len(values), 2)]
                for step in range(1, steps + 1):
                    t = step / steps
                    layer = controls
                    while len(layer) > 1:
                        layer = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(layer, layer[1:])]
                    points.append(layer[0])
                current = controls[-1]
            elif command == "A":
                rx, ry, _, large, sweep, x, y = take(7)
                points.extend(_arc_samples(current, (x, y), rx, ry, bool(large), bool(sweep), steps))
                current = (x, y)
            else:
                index += 1
        if len(points) > least:
            polygons.append(points)
    return polygons


def _arc_samples(start, end, rx, ry, large, sweep, steps):
    """Points along an SVG arc (no turn of its axes, which these outlines never use)."""
    (x1, y1), (x2, y2) = start, end
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry or (x1, y1) == (x2, y2):
        return [end]
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    grow = (dx / rx) ** 2 + (dy / ry) ** 2
    if grow > 1:
        rx, ry = rx * math.sqrt(grow), ry * math.sqrt(grow)
    factor = math.sqrt(max(0.0, (rx * rx * ry * ry - rx * rx * dy * dy - ry * ry * dx * dx) / max(rx * rx * dy * dy + ry * ry * dx * dx, 1e-9)))
    if large == sweep:
        factor = -factor
    cx, cy = factor * rx * dy / ry + (x1 + x2) / 2, -factor * ry * dx / rx + (y1 + y2) / 2
    first = math.atan2((y1 - cy) / ry, (x1 - cx) / rx)
    last = math.atan2((y2 - cy) / ry, (x2 - cx) / rx)
    turn = last - first
    if sweep and turn < 0:
        turn += 2 * math.pi
    elif not sweep and turn > 0:
        turn -= 2 * math.pi
    count = max(2, int(steps * abs(turn) / (math.pi / 2)))
    return [(cx + rx * math.cos(first + turn * i / count), cy + ry * math.sin(first + turn * i / count)) for i in range(1, count + 1)]


def _custom_geometry(custom, width: float, height: float) -> list:
    # Guides work in the shape's EMU; a path with its own w and h scales from those.
    wide, tall = width * EMU_PER_PT, height * EMU_PER_PT
    guides = {"w": wide, "h": tall, "l": 0.0, "t": 0.0, "r": wide, "b": tall, "hc": wide / 2, "vc": tall / 2,
              "wd2": wide / 2, "hd2": tall / 2, "ss": min(wide, tall), "ls": max(wide, tall)}

    def value(token):
        try:
            return float(token)
        except (TypeError, ValueError):
            return guides.get(token, 0.0)

    for guide in custom.iter(A + "gd"):
        parts = (guide.get("fmla") or "").split()
        if not parts:
            continue
        op, args = parts[0], [value(p) for p in parts[1:]]
        try:
            result = {"val": lambda: args[0], "*/": lambda: args[0] * args[1] / args[2],
                      "+-": lambda: args[0] + args[1] - args[2], "+/": lambda: (args[0] + args[1]) / args[2],
                      "min": lambda: min(args[0], args[1]), "max": lambda: max(args[0], args[1]),
                      "abs": lambda: abs(args[0]), "sqrt": lambda: math.sqrt(args[0])}[op]()
        except (KeyError, IndexError, ZeroDivisionError):
            result = 0.0
        guides[guide.get("name")] = result

    out = []
    path_list = custom.find(A + "pathLst")
    for path in (path_list if path_list is not None else []):
        pw, ph = _number(path.get("w")), _number(path.get("h"))
        sx = width / pw if pw else 1.0 / EMU_PER_PT
        sy = height / ph if ph else 1.0 / EMU_PER_PT
        d, x, y = [], 0.0, 0.0

        def point(el):
            return value(el.get("x")) * sx, value(el.get("y")) * sy

        for step in path:
            kind = step.tag[len(A):]
            if kind == "moveTo":
                x, y = point(step.find(A + "pt"))
                d.append(f"M{x:.3f} {y:.3f}")
            elif kind == "lnTo":
                x, y = point(step.find(A + "pt"))
                d.append(f"L{x:.3f} {y:.3f}")
            elif kind == "cubicBezTo":
                pts = [point(p) for p in step.findall(A + "pt")]
                if len(pts) == 3:
                    d.append("C" + " ".join(f"{a:.3f} {b:.3f}" for a, b in pts))
                    x, y = pts[-1]
            elif kind == "quadBezTo":
                pts = [point(p) for p in step.findall(A + "pt")]
                if len(pts) == 2:
                    d.append("Q" + " ".join(f"{a:.3f} {b:.3f}" for a, b in pts))
                    x, y = pts[-1]
            elif kind == "arcTo":
                rx, ry = value(step.get("wR")) * sx, value(step.get("hR")) * sy
                start, sweep = value(step.get("stAng")) / 60000.0, value(step.get("swAng")) / 60000.0
                if rx and ry:
                    t0 = math.atan2(rx * math.sin(math.radians(start)), ry * math.cos(math.radians(start)))
                    t1 = math.atan2(rx * math.sin(math.radians(start + sweep)), ry * math.cos(math.radians(start + sweep)))
                    cx, cy = x - rx * math.cos(t0), y - ry * math.sin(t0)
                    end = (cx + rx * math.cos(t1), cy + ry * math.sin(t1))
                    d.append(f"A{rx:.3f} {ry:.3f} 0 {1 if abs(sweep) > 180 else 0} {1 if sweep > 0 else 0} {end[0]:.3f} {end[1]:.3f}")
                    x, y = end
            elif kind == "close":
                d.append("Z")
        if d:
            mode = None
            if path.get("fill") == "none":
                mode = "nofill"
            elif path.get("stroke") in ("0", "false"):
                mode = "nostroke"
            out.append(("".join(d), mode))
    return out


# -- DrawingML text (SmartArt and PowerPoint write their text this way) ----------------

def paragraphs_html(body, palette: Palette, unit, default_color=None, default_size: float = 18.0) -> str:
    """An a:txBody as HTML paragraphs. ``unit`` turns points into CSS lengths."""
    out = []
    list_style = body.find(A + "lstStyle")
    for paragraph in body.findall(A + "p"):
        props = paragraph.find(A + "pPr")
        attr = props.get if props is not None else (lambda *_: None)
        rtl = attr("rtl") == "1"
        spans, largest = [], 0.0
        factor = _spacing_factor(props)
        for run in paragraph:
            kind = run.tag[len(A):]
            if kind not in ("r", "fld", "br"):
                continue
            if kind == "br":
                spans.append("<br>")
                continue
            text = run.findtext(A + "t") or ""
            css, size = _run_css(run.find(A + "rPr"), paragraph, list_style, palette, unit, default_color, default_size, factor)
            largest = max(largest, size)
            spans.append(f'<span style="{css}">{html.escape(text, quote=False)}</span>')
        size = largest or default_size
        css = [f"line-height:0;font-size:{unit(size)}"]
        text_align = {"ctr": "center", "r": "end" if rtl else "right", "l": "start" if rtl else "left", "just": "justify"}.get(attr("algn") or "")
        if text_align:
            css.append("text-align:" + text_align)
        start = emu(attr("marL"))
        if start:
            css.append(f"margin-inline-start:{unit(start)}")
        hanging = emu(attr("indent"))
        if hanging:
            css.append(f"text-indent:{unit(hanging)}")
        for name, edge in (("spcBef", "top"), ("spcAft", "bottom")):
            space = _space_of(props, name, size)
            if space:
                css.append(f"margin-{edge}:{unit(space)}")
        if not spans:
            css.append(f"min-height:{unit(size * 1.2 * factor)}")
        bullet = props.find(A + "buChar") if props is not None else None
        if bullet is not None and spans:
            spans.insert(0, f'<span style="line-height:{1.2 * factor:.3f};font-size:{unit(size)}">{html.escape(bullet.get("char") or "", quote=False)} </span>')
        out.append(f'<div class="p" dir="{"rtl" if rtl else "auto"}" style="{";".join(css)}">{"".join(spans)}</div>')
    return "".join(out)


def _spacing_factor(props) -> float:
    """A paragraph's line spacing, as a share of single."""
    spacing = props.find(A + "lnSpc") if props is not None else None
    percent = spacing.find(A + "spcPct") if spacing is not None else None
    return _number(percent.get("val"), 100000.0) / 100000.0 if percent is not None else 1.0


def _space_of(props, name: str, size: float) -> float:
    """Space before or after a paragraph, in points."""
    holder = props.find(A + name) if props is not None else None
    if holder is None:
        return 0.0
    percent, points = holder.find(A + "spcPct"), holder.find(A + "spcPts")
    if percent is not None:
        return _number(percent.get("val")) / 100000.0 * size * 1.2
    return _number(points.get("val")) / 100.0 if points is not None else 0.0


def _run_css(props, paragraph, list_style, palette: Palette, unit, default_color, default_size, factor: float = 1.0):
    end = paragraph.find(A + "endParaRPr")
    level = list_style.find(A + "lvl1pPr") if list_style is not None else None
    level_props = level.find(A + "defRPr") if level is not None else None
    size = default_size
    bold = italic = False
    color = default_color
    underline = strike = False
    fonts = []
    for source in (level_props, end if props is None else None, props):
        if source is None:
            continue
        if source.get("sz"):
            size = _number(source.get("sz")) / 100.0
        if source.get("b") is not None:
            bold = source.get("b") == "1"
        if source.get("i") is not None:
            italic = source.get("i") == "1"
        if source.get("u") not in (None, "none"):
            underline = True
        if source.get("strike") not in (None, "noStrike"):
            strike = True
        fill = source.find(A + "solidFill")
        if fill is not None:
            found = palette.first_color(fill)
            if found:
                color = found[0]
        for slot in ("latin", "cs"):
            face = source.find(A + slot)
            if face is not None and face.get("typeface"):
                name = palette.font(face.get("typeface"))
                if name and name not in fonts:
                    fonts.append(name)
    fonts += [name for name in (palette.fonts.get("minorLatin"), palette.fonts.get("minorBidi"), "Arial") if name and name not in fonts]
    family = ", ".join("'" + name.replace("'", "") + "'" for name in fonts)
    css = [f"font-family:{family}", f"font-size:{unit(size)}", f"line-height:{1.2 * factor:.3f}"]
    if bold:
        css.append("font-weight:bold")
    if italic:
        css.append("font-style:italic")
    if underline or strike:
        css.append("text-decoration-line:" + " ".join(n for n, on in (("underline", underline), ("line-through", strike)) if on))
    if color:
        css.append(f"color:#{color}")
    return ";".join(css), size

