"""What Word draws rather than types: shapes and the text inside them, groups,
drawing canvases, SmartArt, charts, and the VML shapes of older files.

Each one becomes a box in the line (or anchored on the page) holding SVG for
the outlines and ordinary paragraphs for the text, so text in a shape is laid
out by the same rules as the rest of the document.
"""
from __future__ import annotations

import html
import logging
import re

from lxml import etree

from .charts import chart_html
from .chartex import chartex_html
from .drawingml import A, DASHES, Canvas, PRESET_COLORS, emu, painted_pieces, paragraphs_html, preset_paths, text_area
from .winfonts import font_info, left_bearing, text_width

log = logging.getLogger(__name__)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
WPS = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
WPG = "{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}"
WPC = "{http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas}"
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
CHART = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
CHARTEX = "{http://schemas.microsoft.com/office/drawing/2014/chartex}"
DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
DSP = "{http://schemas.microsoft.com/office/drawing/2008/diagram}"
V = "{urn:schemas-microsoft-com:vml}"
W10 = "{urn:schemas-microsoft-com:office:word}"
SVG_NS = "http://www.w3.org/2000/svg"

ANCHORS = {"ctr": "center", "b": "flex-end", "just": "center", "dist": "center"}
WRITING_MODES = {"vert": "sideways-rl", "vert270": "sideways-lr", "wordArtVert": "vertical-rl", "eaVert": "vertical-rl",
                 "mongolianVert": "vertical-lr", "wordArtVertRtl": "vertical-lr"}
VML_KINDS = ("shape", "rect", "roundrect", "oval", "line", "polyline", "group", "image", "arc", "curve")
#: The shape numbers VML files name their preset outlines by.
VML_PRESETS = {1: "rect", 2: "roundRect", 3: "ellipse", 4: "diamond", 5: "triangle", 6: "rtTriangle",
               7: "parallelogram", 8: "trapezoid", 9: "hexagon", 10: "octagon", 11: "plus", 12: "star5",
               13: "rightArrow", 15: "homePlate", 16: "cube", 17: "wedgeRoundRectCallout", 18: "irregularSeal1",
               19: "arc", 20: "line", 21: "plaque", 22: "can", 23: "donut", 32: "straightConnector1",
               33: "bentConnector2", 34: "bentConnector3", 35: "bentConnector4", 36: "bentConnector5",
               37: "curvedConnector2", 38: "curvedConnector3", 39: "curvedConnector4", 40: "curvedConnector5",
               41: "borderCallout1", 42: "borderCallout2", 43: "borderCallout3", 44: "accentCallout1",
               45: "accentCallout2", 46: "accentCallout3", 47: "callout1", 48: "callout2", 49: "callout3",
               50: "accentBorderCallout1", 51: "accentBorderCallout2", 52: "accentBorderCallout3", 53: "ribbon",
               54: "ribbon2", 55: "chevron", 56: "pentagon", 57: "noSmoking", 58: "star8", 59: "star16",
               60: "star32", 61: "wedgeRectCallout", 62: "wedgeRoundRectCallout", 63: "wedgeEllipseCallout",
               64: "wave", 65: "foldedCorner", 66: "leftArrow", 67: "downArrow", 68: "upArrow", 69: "leftRightArrow",
               70: "upDownArrow", 71: "irregularSeal1", 72: "irregularSeal2", 73: "lightningBolt", 74: "heart",
               75: "frame", 76: "quadArrow", 77: "leftArrowCallout", 78: "rightArrowCallout", 79: "upArrowCallout",
               80: "downArrowCallout", 81: "leftRightArrowCallout", 82: "upDownArrowCallout", 83: "quadArrowCallout",
               84: "bevel", 85: "leftBracket", 86: "rightBracket", 87: "leftBrace", 88: "rightBrace",
               89: "leftUpArrow", 90: "bentUpArrow", 91: "bentArrow", 92: "star24", 93: "stripedRightArrow",
               94: "notchedRightArrow", 95: "blockArc", 96: "smileyFace", 97: "verticalScroll",
               98: "horizontalScroll", 99: "circularArrow", 101: "uturnArrow", 102: "curvedRightArrow",
               103: "curvedLeftArrow", 104: "curvedUpArrow", 105: "curvedDownArrow", 106: "cloudCallout",
               107: "ellipseRibbon", 108: "ellipseRibbon2", 109: "flowChartProcess", 110: "flowChartDecision",
               111: "flowChartInputOutput", 112: "flowChartPredefinedProcess", 113: "flowChartInternalStorage",
               114: "flowChartDocument", 115: "flowChartMultidocument", 116: "flowChartTerminator",
               117: "flowChartPreparation", 118: "flowChartManualInput", 119: "flowChartManualOperation",
               120: "flowChartConnector", 121: "flowChartPunchedCard", 122: "flowChartPunchedTape",
               123: "flowChartSummingJunction", 124: "flowChartOr", 125: "flowChartCollate", 126: "flowChartSort",
               127: "flowChartExtract", 128: "flowChartMerge", 129: "flowChartOfflineStorage",
               130: "flowChartOnlineStorage", 131: "flowChartMagneticTape", 132: "flowChartMagneticDisk",
               133: "flowChartMagneticDrum", 134: "flowChartDisplay", 135: "flowChartDelay",
               176: "flowChartAlternateProcess", 177: "flowChartOffpageConnector", 182: "leftRightUpArrow",
               183: "sun", 184: "moon", 185: "bracketPair", 186: "bracePair", 187: "star4", 188: "doubleWave",
               189: "actionButtonBlank", 190: "actionButtonHome", 191: "actionButtonHelp",
               192: "actionButtonInformation", 193: "actionButtonForwardNext", 194: "actionButtonBackPrevious",
               195: "actionButtonEnd", 196: "actionButtonBeginning", 197: "actionButtonReturn",
               198: "actionButtonDocument", 199: "actionButtonSound", 200: "actionButtonMovie", 202: "rect"}
VML_ARROWS = {"block": "triangle", "classic": "stealth", "open": "arrow", "diamond": "diamond", "oval": "oval"}
VML_DASHES = {"dot": "dot", "shortdot": "sysDot", "dash": "dash", "shortdash": "sysDash", "longdash": "lgDash", "dashdot": "dashDot",
              "longdashdot": "lgDashDot", "longdashdotdot": "lgDashDotDot", "shortdashdot": "sysDashDot",
              "shortdashdotdot": "sysDashDotDot"}


def _flag(value) -> bool:
    return value in ("1", "true", "on", "t")


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _moved(rotation: float = 0.0, flip_h: bool = False, flip_v: bool = False) -> str:
    """The CSS that turns a layer, or nothing."""
    steps = []
    if rotation:
        steps.append(f"rotate({rotation:.3f}deg)")
    if flip_h or flip_v:
        steps.append(f"scale({-1 if flip_h else 1},{-1 if flip_v else 1})")
    return ";transform:" + " ".join(steps) if steps else ""


def _xfrm(xfrm) -> tuple:
    """(x, y, width, height, degrees, flipped across, flipped down) of an a:xfrm."""
    if xfrm is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0, False, False
    off, ext = xfrm.find(A + "off"), xfrm.find(A + "ext")
    return (emu(off.get("x")) if off is not None else 0.0, emu(off.get("y")) if off is not None else 0.0,
            emu(ext.get("cx")) if ext is not None else 0.0, emu(ext.get("cy")) if ext is not None else 0.0,
            _number(xfrm.get("rot")) / 60000.0, _flag(xfrm.get("flipH")), _flag(xfrm.get("flipV")))


def vml_length(style: str, name: str):
    """A length in a VML style, in points."""
    match = re.search("(?:^|;)" + name + ":([-0-9.]+)(pt|in|px|cm|mm)?", style.replace(" ", ""))
    if not match:
        return None
    scale = {"pt": 1.0, "in": 72.0, "px": 0.75, "cm": 72 / 2.54, "mm": 72 / 25.4}.get(match.group(2) or "px", 0.75)
    return _number(match.group(1)) * scale


def _vml_measure(value, default: float = 0.0) -> float:
    """One VML length on its own; a bare number is in EMU."""
    match = re.fullmatch("([-0-9.]+)(pt|in|px|cm|mm)?", (value or "").strip())
    if not match:
        return default
    if not match.group(2):
        return _number(match.group(1)) / 12700.0
    return _number(match.group(1)) * {"pt": 1.0, "in": 72.0, "px": 0.75, "cm": 72 / 2.54, "mm": 72 / 25.4}[match.group(2)]


def _vml_raw(style: str, name: str, default: float = 0.0) -> float:
    match = re.search("(?:^|;)" + name + ":([-0-9.]+)", style.replace(" ", ""))
    return _number(match.group(1), default) if match else default


def _vml_word(style: str, name: str) -> str:
    match = re.search("(?:^|;)" + name + ":([^;]+)", style.replace(" ", ""))
    return match.group(1).lower() if match else ""


def _vml_color(value):
    """RRGGBB from a VML colour ("#ff0", "#4472c4 [3204]", "red"), or None."""
    if not value:
        return None
    word = value.split()[0].strip()
    if word.startswith("#"):
        digits = word[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return digits.upper() if re.fullmatch("[0-9A-Fa-f]{6}", digits) else None
    return PRESET_COLORS.get(word) or PRESET_COLORS.get(word.lower())


def _vml_fraction(value, default: float = 1.0) -> float:
    if not value:
        return default
    value = value.strip()
    if value.endswith("f"):
        return _number(value[:-1], default * 65536.0) / 65536.0
    if value.endswith("%"):
        return _number(value[:-1], default * 100.0) / 100.0
    return _number(value, default)


class Drawings:
    """The drawing half of the Word layout; docx_layout.Layout is built on it."""

    def _drawing(self, drawing) -> str:
        inline = drawing.find(WP + "inline")
        holder = inline if inline is not None else drawing.find(WP + "anchor")
        if holder is None:
            return ""
        extent = holder.find(WP + "extent")
        width = emu(extent.get("cx")) if extent is not None else 0.0
        height = emu(extent.get("cy")) if extent is not None else 0.0
        try:
            content = self._graphic(next(holder.iter(A + "graphicData"), None), holder, width, height)
        except Exception:               # one broken drawing must not cost the whole document
            log.exception("could not draw an object in %s", self.path.name)
            content = self._frame(width, height, "")
        if not content or inline is not None:
            return content
        return self._anchored(holder, content, width, height)

    def _graphic(self, data, holder, width: float, height: float) -> str:
        """What an a:graphicData holds, at the given size."""
        if data is None:
            return ""
        for node in data:
            tag = node.tag
            if tag == PIC + "pic":
                blip = next(node.iter(A + "blip"), None)
                return self._picture(blip, holder, width, height) if blip is not None else ""
            if tag == WPS + "wsp":
                _, _, _, _, rotation, flip_h, flip_v = _xfrm(_find(node.find(WPS + "spPr"), A + "xfrm"))
                return self._frame(width, height, self._shape(node, width, height, rotation, flip_h, flip_v))
            if tag == WPG + "wgp":
                _, _, _, _, rotation, flip_h, flip_v = _xfrm(_find(node.find(WPG + "grpSpPr"), A + "xfrm"))
                inner = self._group(node, WPG + "grpSpPr", width, height, flip_h, flip_v)
                return self._frame(width, height, self._layer(0.0, 0.0, width, height, inner, rotation))
            if tag == WPC + "wpc":
                return self._frame(width, height, self._drawing_canvas(node, width, height))
            if tag == CHART + "chart":
                return self._frame(width, height, self._chart(node, width, height))
            if tag == CHARTEX + "chart":
                return self._frame(width, height, self._chart(node, width, height, chartex_html))
            if tag == DGM + "relIds":
                return self._frame(width, height, self._diagram(node, width, height))
        blip = next(data.iter(A + "blip"), None)
        return self._picture(blip, holder, width, height) if blip is not None else ""

    def _frame(self, width: float, height: float, inner: str) -> str:
        return f'<span class="drawn" style="width:{self._u(width)};height:{self._u(height)}">{inner}</span>'

    def _layer(self, x: float, y: float, width: float, height: float, inner: str, rotation: float = 0.0) -> str:
        return (f'<span class="layer" style="left:{self._u(x)};top:{self._u(y)};width:{self._u(width)};'
                f'height:{self._u(height)}{_moved(rotation)}">{inner}</span>')

    def _svg(self, canvas, paths: str, width: float, height: float, rotation=0.0, flip_h=False, flip_v=False) -> str:
        w, h = max(width, 0.1), max(height, 0.1)
        return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w:.3f} {h:.3f}" preserveAspectRatio="none" '
                f'style="position:absolute;left:0;top:0;width:{self._u(w)};height:{self._u(h)};overflow:visible'
                f'{_moved(rotation, flip_h, flip_v)}">{canvas.definitions()}{paths}</svg>')

    # -- shapes ---------------------------------------------------------------------------

    def _shape(self, sp, width, height, rotation=0.0, flip_h=False, flip_v=False) -> str:
        """A wps shape's outline and text, in a box of its size."""
        sp_pr, style = sp.find(WPS + "spPr"), sp.find(WPS + "style")
        canvas = Canvas(self.palette, self._image_uri)
        out = self._svg(canvas, canvas.shape_paths(sp_pr, style, width, height), width, height, rotation, flip_h, flip_v)
        box = sp.find(f"{WPS}txbx/{W}txbxContent")
        if box is not None:
            font = style.find(A + "fontRef") if style is not None else None
            found = self.palette.first_color(font) if font is not None else None
            table = ({}, {"color": (found[0], None)}) if found else None
            inner = self._rendered(box, self._now, table=table)
            out += self._shape_text(inner, sp_pr, sp.find(WPS + "bodyPr"), width, height, rotation, flip_v)
        return out

    def _shape_text(self, inner: str, sp_pr, body, width, height, rotation=0.0, flip_v=False) -> str:
        """Text placed in a shape's text area, inside its insets."""
        attr = body.get if body is not None else (lambda *_: None)
        left, top, right, bottom = text_area(sp_pr, width, height)
        left += emu(attr("lIns"), 7.2)
        top += emu(attr("tIns"), 3.6)
        right -= emu(attr("rIns"), 7.2)
        bottom -= emu(attr("bIns"), 3.6)
        turn = 0.0 if _flag(attr("upright")) else rotation
        turn += _number(attr("rot")) / 60000.0 + (180.0 if flip_v else 0.0)
        return self._text_area(inner, left, top, max(0.0, right - left), max(0.0, bottom - top), ANCHORS.get(attr("anchor"), "flex-start"),
                               WRITING_MODES.get(attr("vert")), attr("wrap") == "none", width, height, turn)

    def _text_area(self, inner, x, y, w, h, justify, mode, unwrapped, width, height, turn=0.0) -> str:
        css = [f"left:{self._u(x)}", f"top:{self._u(y)}", f"width:{self._u(w)}", f"height:{self._u(h)}",
               f"justify-content:{justify}"]
        if mode:
            css.append("writing-mode:" + mode)
        names = "shape-text unwrapped" if unwrapped else "shape-text"
        text = f'<span class="{names}" style="{";".join(css)}"><span class="text-flow">{inner}</span></span>'
        return self._layer(0.0, 0.0, width, height, text, turn) if turn else text

    # -- groups and canvases ---------------------------------------------------------------

    def _group(self, group, props_tag, width, height, flip_h=False, flip_v=False) -> str:
        """A group's members, in a box of its size. Their positions are in the
        group's own coordinates, which ``chOff`` and ``chExt`` map onto the box."""
        xfrm = _find(group.find(props_tag), A + "xfrm")
        ox = oy = wide = tall = 0.0
        if xfrm is not None:
            child_off, child_ext = xfrm.find(A + "chOff"), xfrm.find(A + "chExt")
            if child_off is not None:
                ox, oy = emu(child_off.get("x")), emu(child_off.get("y"))
            if child_ext is not None:
                wide, tall = emu(child_ext.get("cx")), emu(child_ext.get("cy"))
        sx = width / wide if wide else 1.0
        sy = height / tall if tall else 1.0
        return "".join(self._member(node, ox, oy, sx, sy, width, height, flip_h, flip_v) for node in group)

    def _member(self, node, ox, oy, sx, sy, width, height, flip_h, flip_v) -> str:
        tag = node.tag
        if tag == WPS + "wsp":
            xfrm = _find(node.find(WPS + "spPr"), A + "xfrm")
        elif tag == PIC + "pic":
            xfrm = _find(node.find(PIC + "spPr"), A + "xfrm")
        elif tag in (WPG + "grpSp", WPG + "wgp"):
            xfrm = _find(node.find(WPG + "grpSpPr"), A + "xfrm")
        elif tag == WPG + "graphicFrame":
            xfrm = node.find(WPG + "xfrm")
        elif tag == WPC + "graphicFrame":
            xfrm = node.find(WPC + "xfrm")
        else:
            return ""
        x, y, cx, cy, rotation, own_h, own_v = _xfrm(xfrm)
        x, y, cx, cy = (x - ox) * sx, (y - oy) * sy, cx * sx, cy * sy
        if flip_h:                       # a flipped group mirrors where its members sit
            x, own_h, rotation = width - x - cx, not own_h, -rotation
        if flip_v:
            y, own_v, rotation = height - y - cy, not own_v, -rotation
        if tag == WPS + "wsp":
            return self._layer(x, y, cx, cy, self._shape(node, cx, cy, rotation, own_h, own_v))
        if tag == PIC + "pic":
            blip = next(node.iter(A + "blip"), None)
            return self._layer(x, y, cx, cy, self._picture(blip, node, cx, cy)) if blip is not None else ""
        if tag in (WPG + "grpSp", WPG + "wgp"):
            return self._layer(x, y, cx, cy, self._group(node, WPG + "grpSpPr", cx, cy, own_h, own_v), rotation)
        return self._layer(x, y, cx, cy, self._graphic(next(node.iter(A + "graphicData"), None), node, cx, cy))

    def _drawing_canvas(self, canvas_el, width, height) -> str:
        out = []
        background, whole = canvas_el.find(WPC + "bg"), canvas_el.find(WPC + "whole")
        if background is not None or whole is not None:
            canvas = Canvas(self.palette, self._image_uri)
            paint = canvas.paint(canvas.fill_of(background)) if background is not None else 'fill="none"'
            stroke = canvas.stroke(whole.find(A + "ln")) if whole is not None else 'stroke="none"'
            out.append(self._svg(canvas, f'<rect width="{width:.3f}" height="{height:.3f}" {paint} {stroke}/>', width, height))
        out += [self._member(node, 0.0, 0.0, 1.0, 1.0, width, height, False, False) for node in canvas_el]
        return "".join(out)

    # -- charts ------------------------------------------------------------------------------

    def _chart(self, node, width, height, draw=chart_html) -> str:
        part = self._now.related_parts.get(node.get(R + "id")) if node.get(R + "id") else None
        if part is None:
            return ""
        saved, self._now = self._now, part       # pictures in a chart are the chart part's own
        try:
            return draw(etree.fromstring(part.blob), self.palette, width, height, self._u, self._image_uri, self._absent_means_yes())
        finally:
            self._now = saved

    def _absent_means_yes(self) -> bool:
        """Office reads a yes-or-no setting left out of a chart as yes, unless the
        file comes from Word 2007, which simply didn't write its noes."""
        for part in self.part.package.iter_parts():
            if str(part.partname).endswith("/docProps/app.xml"):
                return not re.search(b"<AppVersion>12[.]", part.blob or b"")
        return True

    # -- SmartArt --------------------------------------------------------------------------

    def _diagram(self, rel_ids, width, height) -> str:
        """SmartArt as Word last drew it, which the file keeps as plain shapes.
        Files from elsewhere may only hold its text: that is laid out as a list."""
        parts = self._now.related_parts
        data_part = parts.get(rel_ids.get(R + "dm")) if rel_ids.get(R + "dm") else None
        if data_part is None:
            return ""
        data = etree.fromstring(data_part.blob)
        note = next(data.iter(DSP + "dataModelExt"), None)
        drawing_part = parts.get(note.get("relId")) if note is not None and note.get("relId") else None
        if drawing_part is not None:
            tree = next(etree.fromstring(drawing_part.blob).iter(DSP + "spTree"), None)
            if tree is not None:
                return "".join(self._diagram_node(node) for node in tree)
        return self._diagram_list(data, width, height)

    def _diagram_node(self, node) -> str:
        if node.tag == DSP + "grpSp":
            return "".join(self._diagram_node(child) for child in node)
        if node.tag != DSP + "sp":
            return ""
        sp_pr, style = node.find(DSP + "spPr"), node.find(DSP + "style")
        x, y, width, height, rotation, flip_h, flip_v = _xfrm(_find(sp_pr, A + "xfrm"))
        canvas = Canvas(self.palette, self._image_uri)
        out = self._layer(x, y, width, height, self._svg(canvas, canvas.shape_paths(sp_pr, style, width, height), width, height,
                                                         rotation, flip_h, flip_v))
        body = node.find(DSP + "txBody")
        if body is None or not any((t.text or "").strip() for t in body.iter(A + "t")):
            return out
        font = style.find(A + "fontRef") if style is not None else None
        found = self.palette.first_color(font) if font is not None else None
        inner = paragraphs_html(body, self.palette, self._u, found[0] if found else None)
        tx, ty, tw, th, turn, _, _ = _xfrm(node.find(DSP + "txXfrm"))
        if not tw or not th:
            tx, ty, tw, th, turn = x, y, width, height, 0.0
        props = body.find(A + "bodyPr")
        attr = props.get if props is not None else (lambda *_: None)
        left, top = emu(attr("lIns"), 7.2), emu(attr("tIns"), 3.6)
        right, bottom = emu(attr("rIns"), 7.2), emu(attr("bIns"), 3.6)
        text = self._text_area(inner, left, top, max(0.0, tw - left - right), max(0.0, th - top - bottom),
                               ANCHORS.get(attr("anchor"), "flex-start"), WRITING_MODES.get(attr("vert")), False, tw, th)
        return out + self._layer(tx, ty, tw, th, text, rotation + turn)

    def _diagram_list(self, data, width, height) -> str:
        items = []
        for point in data.iter(DGM + "pt"):
            if point.get("type") not in (None, "node"):
                continue
            text = "".join(t.text or "" for t in point.iter(A + "t")).strip()
            if text:
                items.append(text)
        if not items:
            return ""
        gap = min(6.0, height * 0.04)
        step = (height - gap * (len(items) - 1)) / len(items)
        color = self.palette.scheme_color("accent1")
        out = []
        for index, text in enumerate(items):
            y = index * (step + gap)
            shape = f'<rect width="{width:.3f}" height="{step:.3f}" rx="{min(step, width) * .1:.3f}" fill="#{color}"/>'
            canvas = Canvas(self.palette)
            size = min(14.0, step * 0.5)
            label = (f'<div class="p" dir="auto" style="text-align:center;line-height:1.2;font-size:{self._u(size)};color:#FFF;'
                     f"font-family:'{self.palette.fonts.get('minorLatin') or 'Arial'}', '{self.palette.fonts.get('minorBidi') or 'Arial'}', Arial\">"
                     f"{html.escape(text, quote=False)}</div>")
            area = self._text_area(label, 6.0, 0.0, max(0.0, width - 12.0), step, "center", None, False, width, step)
            out.append(self._layer(0.0, y, width, step, self._svg(canvas, shape, width, step) + area))
        return "".join(out)

    # -- VML ------------------------------------------------------------------------------------

    def _vml(self, element) -> str:
        node = next((c for c in element if isinstance(c.tag, str) and c.tag.startswith(V) and c.tag[len(V):] in VML_KINDS), None)
        if node is None:
            return ""
        try:
            return self._vml_shape(node)
        except Exception:
            log.exception("could not draw an old shape in %s", self.path.name)
            return ""

    def _vml_shape(self, node) -> str:
        style = node.get("style") or ""
        box = self._vml_box(node, 1.0, 1.0, 0.0, 0.0, points=True)
        width, height = box[2], box[3]
        data = node.find(V + "imagedata")
        if data is not None:
            uri = self._image_uri(data.get(R + "id"))
            # A picture watermark is washed out through these two settings.
            faded = ";opacity:.35" if data.get("gain") and data.get("blacklevel") else ""
            content = (f'<img alt="" src="{uri}" style="width:{self._u(width)};height:{self._u(height)}{_moved(box[4], box[5], box[6])}{faded}">'
                       if uri else "")
        else:
            inner = self._vml_inner(node, width, height, box[4], box[5], box[6])
            content = self._frame(width, height, inner) if inner else ""
        if not content or _vml_word(style, "position") != "absolute":
            return content
        wrap = next(node.iter(W10 + "wrap"), None)
        kind = {"square": "wrapSquare", "tight": "wrapTight", "through": "wrapThrough", "topandbottom": "wrapTopAndBottom"}.get(
            (wrap.get("type") or "").lower() if wrap is not None else "", "wrapNone")
        across = {"page": "page", "margin": "margin", "left-margin-area": "leftMargin", "right-margin-area": "rightMargin",
                  "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin"}
        down = {"page": "page", "margin": "margin", "top-margin-area": "topMargin", "bottom-margin-area": "bottomMargin",
                "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin"}
        left = vml_length(style, "margin-left") or vml_length(style, "left") or 0.0
        top = vml_length(style, "margin-top") or vml_length(style, "top") or 0.0
        h_place = (across.get(_vml_word(style, "mso-position-horizontal-relative"), "column"),
                   _vml_word(style, "mso-position-horizontal").replace("absolute", ""), left)
        v_place = (down.get(_vml_word(style, "mso-position-vertical-relative"), "paragraph"),
                   _vml_word(style, "mso-position-vertical").replace("absolute", ""), top)
        gap = {"distT": vml_length(style, "mso-wrap-distance-top") or 0.0, "distB": vml_length(style, "mso-wrap-distance-bottom") or 0.0,
               "distL": vml_length(style, "mso-wrap-distance-left") or 9.0, "distR": vml_length(style, "mso-wrap-distance-right") or 9.0}
        return self._placed(content, width, height, kind, gap, h_place, v_place, _vml_raw(style, "z-index") < 0)

    def _vml_box(self, node, sx, sy, ox, oy, points=False) -> tuple:
        """(x, y, width, height, degrees, flipped across, flipped down) of a VML
        shape; inside a group its lengths are in the group's own units."""
        style = node.get("style") or ""
        measure = (lambda name: vml_length(style, name) or 0.0) if points else (lambda name: _vml_raw(style, name))
        x, y = measure("left"), measure("top")
        width, height = measure("width"), measure("height")
        flip = _vml_word(style, "flip")
        flip_h, flip_v = "x" in flip, "y" in flip
        if node.tag == V + "line":
            start = [_vml_measure_raw(p, points) for p in (node.get("from") or "0,0").split(",")]
            end = [_vml_measure_raw(p, points) for p in (node.get("to") or "0,0").split(",")]
            if len(start) == 2 and len(end) == 2:
                x, y = min(start[0], end[0]), min(start[1], end[1])
                width, height = abs(end[0] - start[0]), abs(end[1] - start[1])
                flip_h, flip_v = end[0] < start[0], end[1] < start[1]
        return (x - ox) * sx, (y - oy) * sy, width * sx, height * sy, _vml_raw(style, "rotation"), flip_h, flip_v

    def _vml_inner(self, node, width, height, rotation=0.0, flip_h=False, flip_v=False) -> str:
        kind = node.tag[len(V):]
        if kind == "group":
            size = (node.get("coordsize") or "").split(",")
            origin = (node.get("coordorigin") or "0,0").split(",")
            wide, tall = _number(size[0]) if size[0] else 0.0, _number(size[1]) if len(size) > 1 else 0.0
            ox, oy = _number(origin[0]), _number(origin[1]) if len(origin) > 1 else 0.0
            sx, sy = width / wide if wide else 1.0, height / tall if tall else 1.0
            out = []
            for child in node:
                if not isinstance(child.tag, str) or not child.tag.startswith(V) or child.tag[len(V):] not in VML_KINDS:
                    continue
                x, y, w, h, turn, across, down = self._vml_box(child, sx, sy, ox, oy)
                data = child.find(V + "imagedata")
                if data is not None:
                    uri = self._image_uri(data.get(R + "id"))
                    inner = f'<img alt="" src="{uri}" style="width:{self._u(w)};height:{self._u(h)}">' if uri else ""
                else:
                    inner = self._vml_inner(child, w, h, turn, across, down)
                if inner:
                    out.append(self._layer(x, y, w, h, inner))
            return self._layer(0.0, 0.0, width, height, "".join(out), rotation) if rotation else "".join(out)
        canvas = Canvas(self.palette, self._image_uri)
        paint = self._vml_paint(node)
        stroke = self._vml_stroke(node, canvas)
        words = node.find(V + "textpath")
        if words is not None and words.get("string"):      # WordArt, as in a DRAFT watermark
            return self._svg(canvas, self._vml_word_art(words, paint, stroke, width, height), width, height, rotation, flip_h, flip_v)
        pieces = preset_paths(self._vml_outline(node), width, height, self._vml_adjust(node))
        out = self._svg(canvas, painted_pieces(pieces, paint, stroke), width, height, rotation, flip_h, flip_v)
        text = node.find(V + "textbox")
        box = text.find(W + "txbxContent") if text is not None else None
        if box is not None:
            sides = (text.get("inset") or "").split(",")
            values = [_vml_measure(sides[i], d) if i < len(sides) and sides[i].strip() else d
                      for i, d in enumerate((7.2, 3.6, 7.2, 3.6))]
            style = node.get("style") or ""
            middle = {"middle": "center", "bottom": "flex-end"}.get(_vml_word(style, "v-text-anchor"), "flex-start")
            inner = self._rendered(box, self._now)
            out += self._text_area(inner, values[0], values[1], max(0.0, width - values[0] - values[2]),
                                   max(0.0, height - values[1] - values[3]), middle, None, False, width, height,
                                   rotation)
        return out

    @staticmethod
    def _vml_word_art(words, paint, stroke, width, height) -> str:
        """Text stretched to fill its shape."""
        text = words.get("string")
        found = re.search("font-family:[ ]*&?(?:quot;)?[\"']?([^\"';&]+)", words.get("style") or "")
        family = found.group(1).strip() if found else "Arial"
        metrics = font_info(family)
        # The shape's height is the font's size, and the letters are squeezed to its width from
        # the edge of the first letter's ink. Word's baseline sits a little under the font's.
        size = height
        baseline = size * (metrics.ascent / (metrics.ascent + metrics.descent) + 0.009)
        if re.search("[" + chr(0x0590) + "-" + chr(0x08FF) + "]", text):
            place = f'x="{width / 2:.3f}" text-anchor="middle" direction="rtl"'
        else:
            squeeze = width / max(text_width(text, family, size), 0.01)
            place = f'x="{-left_bearing(text, family) * size * squeeze:.3f}" text-anchor="start"'
        return (f'<text {place} y="{baseline:.3f}" font-size="{size:.3f}" font-family="\'{family}\', Arial" '
                f'textLength="{width:.3f}" lengthAdjust="spacingAndGlyphs" {paint} {stroke if "none" not in stroke else ""}>'
                f"{html.escape(text, quote=False)}</text>")

    @staticmethod
    def _vml_outline(node) -> str:
        kind = node.tag[len(V):]
        if kind in ("rect", "image"):
            return "rect"
        if kind == "roundrect":
            return "roundRect"
        if kind == "oval":
            return "ellipse"
        if kind == "line":
            return "line"
        match = re.search("t([0-9]+)$", node.get("type") or "")
        return VML_PRESETS.get(int(match.group(1)), "rect") if match else "rect"

    @staticmethod
    def _vml_adjust(node) -> dict:
        if node.get("arcsize"):
            return {"adj": _vml_fraction(node.get("arcsize"), 1 / 6) * 100000.0}
        return {}

    @staticmethod
    def _vml_paint(node) -> str:
        fill = node.find(V + "fill")
        shown = (node.get("filled") or "t") not in ("f", "false")
        color = _vml_color(node.get("fillcolor")) or "FFFFFF"
        opacity = 1.0
        if fill is not None:
            if fill.get("on") in ("f", "false"):
                shown = False
            color = _vml_color(fill.get("color")) or color
            opacity = _vml_fraction(fill.get("opacity"), 1.0)
        if not shown:
            return 'fill="none"'
        return f'fill="#{color}"' + (f' fill-opacity="{opacity:.3f}"' if opacity < 1 else "")

    @staticmethod
    def _vml_stroke(node, canvas) -> str:
        line = node.find(V + "stroke")
        if (node.get("stroked") or "t") in ("f", "false") or (line is not None and line.get("on") in ("f", "false")):
            return 'stroke="none"'
        color = _vml_color(node.get("strokecolor")) or "000000"
        weight = _vml_measure(node.get("strokeweight"), 0.75) if node.get("strokeweight") else 0.75
        out = []
        if line is not None:
            color = _vml_color(line.get("color")) or color
            if line.get("weight"):
                weight = _vml_measure(line.get("weight"), weight)
            dash = VML_DASHES.get((line.get("dashstyle") or "").lower())
            if dash:
                out.append('stroke-dasharray="' + " ".join(f"{step * weight:.2f}" for step in DASHES[dash]) + '"')
            for key, attribute in (("startarrow", "marker-start"), ("endarrow", "marker-end")):
                kind = VML_ARROWS.get((line.get(key) or "").lower())
                if kind:
                    end = etree.Element("end", type=kind)
                    out.append(f'{attribute}="url(#{canvas._arrow(end, color)})"')
        return " ".join([f'stroke="#{color}"', f'stroke-width="{weight:.3f}"'] + out)


def _vml_measure_raw(value, points: bool) -> float:
    if not points:
        return _number((value or "").replace("pt", "").strip())
    return _vml_measure(value if re.search("[a-z]", value or "") else (value or "0") + "pt")


def _find(parent, tag):
    return parent.find(tag) if parent is not None else None
