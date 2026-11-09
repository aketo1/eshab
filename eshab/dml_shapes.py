"""DrawingML shape trees (PowerPoint slides, Excel drawings, SmartArt) as HTML.

Shapes, connectors, pictures, groups and graphic frames (charts, tables,
SmartArt, embedded objects' pictures) are each laid out as an absolutely
placed box: outlines and fills through :mod:`eshab.drawingml`, text through
:mod:`eshab.dml_text`, charts through :mod:`eshab.charts`. All lengths are
points; ``unit`` turns them into the page's CSS lengths.
"""
from __future__ import annotations

import html
import logging
import math

from lxml import etree

from .drawingml import A, Canvas, PRESET_COLORS, emu, geometry, text_area
from .dml_text import TextRenderer, TextStyle, autofit, body_insets

log = logging.getLogger("eshab")

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
DSP = "{http://schemas.microsoft.com/office/drawing/2008/diagram}"
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
CX = "{http://schemas.microsoft.com/office/drawing/2014/chartex}"
DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
SVG_NS = "http://www.w3.org/2000/svg"
#: Content only newer Office draws (3D models, ink): its fallback picture is shown.
UNSUPPORTED = ("am3d", "aink", "wpi")
WRITING = {"vert": "vertical-rl", "vert270": "vertical-lr", "eaVert": "vertical-rl", "wordArtVert": "vertical-rl",
           "mongolianVert": "vertical-lr", "wordArtVertRtl": "vertical-lr"}


def local(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def _child(node, name: str):
    """A child by local name, whatever its namespace (p:, xdr:, dsp: or a:)."""
    if node is None:
        return None
    for child in node:
        if local(child.tag) == name:
            return child
    return None


def _flag(value) -> bool:
    return value in ("1", "true", "on")


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_alternate(node):
    """The branch of an mc:AlternateContent Office would show here."""
    for choice in node.findall(MC + "Choice"):
        if not any(name in UNSUPPORTED for name in (choice.get("Requires") or "").split()):
            return list(choice)
    fallback = node.find(MC + "Fallback")
    return list(fallback) if fallback is not None else []


def xfrm_of(node):
    """(x, y, w, h, degrees, flipH, flipV, child offset, child extent) of a node's transform, in points."""
    holder = None
    kind = local(node.tag)
    if kind == "grpSp":
        holder = _child(_child(node, "grpSpPr"), "xfrm")
    elif kind == "graphicFrame":
        holder = _child(node, "xfrm")
    else:
        holder = _child(_child(node, "spPr"), "xfrm")
    if holder is None:
        return None
    off, ext = holder.find(A + "off"), holder.find(A + "ext")
    ch_off, ch_ext = holder.find(A + "chOff"), holder.find(A + "chExt")
    return (emu(off.get("x")) if off is not None else 0.0, emu(off.get("y")) if off is not None else 0.0,
            emu(ext.get("cx")) if ext is not None else 0.0, emu(ext.get("cy")) if ext is not None else 0.0,
            _num(holder.get("rot")) / 60000.0, _flag(holder.get("flipH")), _flag(holder.get("flipV")),
            (emu(ch_off.get("x")), emu(ch_off.get("y"))) if ch_off is not None else None,
            (emu(ch_ext.get("cx")), emu(ch_ext.get("cy"))) if ch_ext is not None else None)


class ShapeRenderer:
    """Renders the shapes of one part (a slide, a drawing) through its relationships.

    ``text_for(node)`` may give a shape's text style chain, default colour and
    size (PowerPoint's placeholders); ``fill_for(node)`` and ``line_for`` may
    give a placeholder's inherited spPr pieces."""

    def __init__(self, part, palette, unit, text_for=None, fields=None, default_size: float = 18.0,
                 table_styles=None, inherit=None):
        self.part = part
        self.palette = palette
        self.unit = unit
        self.text_for = text_for
        self.fields = fields or {}
        self.default_size = default_size
        self.table_styles = table_styles or {}
        self.inherit = inherit

    # -- trees ------------------------------------------------------------------------

    def tree_html(self, tree, mapping=None) -> str:
        """The members of an spTree or grpSp; ``mapping`` turns their coordinates into the page's."""
        out = []
        for node in tree:
            for item in (resolve_alternate(node) if node.tag == MC + "AlternateContent" else [node]):
                try:
                    out.append(self.node_html(item, mapping))
                except Exception:
                    log.exception("could not draw a %s", local(item.tag))
        return "".join(out)

    def node_html(self, node, mapping=None, box=None) -> str:
        kind = local(node.tag)
        if kind not in ("sp", "cxnSp", "pic", "grpSp", "graphicFrame", "contentPart"):
            return ""
        placed = xfrm_of(node)
        if box is None:
            if placed is None and self.inherit is not None:
                placed = self.inherit(node)
            if placed is None:
                return ""
            x, y, w, h = placed[:4]
            if mapping is not None:
                x, y, w, h = mapping(x, y, w, h)
        else:
            x, y, w, h = box
        rotation, flip_h, flip_v = (placed[4], placed[5], placed[6]) if placed else (0.0, False, False)
        if kind == "grpSp":
            return self._group(node, placed, x, y, w, h, rotation, flip_h, flip_v)
        if kind == "graphicFrame":
            return self._frame(node, x, y, w, h)
        if kind == "pic":
            return self._picture(node, x, y, w, h, rotation, flip_h, flip_v)
        if kind == "contentPart":
            return ""
        return self._shape(node, x, y, w, h, rotation, flip_h, flip_v)

    def _box(self, x, y, w, h, inner, rotation=0.0, extra="") -> str:
        turn = f";transform:rotate({rotation:.3f}deg)" if rotation else ""
        return (f'<div class="dml" style="left:{self.unit(x)};top:{self.unit(y)};width:{self.unit(max(w, 0.01))};'
                f'height:{self.unit(max(h, 0.01))}{turn}{extra}">{inner}</div>')

    def _svg(self, canvas, body: str, w: float, h: float, flip_h=False, flip_v=False) -> str:
        flips = f";transform:scale({-1 if flip_h else 1},{-1 if flip_v else 1})" if flip_h or flip_v else ""
        return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {max(w, 0.01):.3f} {max(h, 0.01):.3f}" preserveAspectRatio="none" '
                f'style="position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible{flips}">'
                f"{canvas.definitions()}{body}</svg>")

    # -- groups -----------------------------------------------------------------------

    def _group(self, node, placed, x, y, w, h, rotation, flip_h, flip_v) -> str:
        child_off = placed[7] if placed and placed[7] else (placed[0], placed[1]) if placed else (0.0, 0.0)
        child_ext = placed[8] if placed and placed[8] else (placed[2], placed[3]) if placed else (w, h)
        sx = w / child_ext[0] if child_ext[0] else 1.0
        sy = h / child_ext[1] if child_ext[1] else 1.0

        def inner(cx, cy, cw, ch):
            # inside the group's own box: members are placed relative to it
            return (cx - child_off[0]) * sx, (cy - child_off[1]) * sy, cw * sx, ch * sy
        members = self.tree_html(node, inner)
        flips = f";transform:scale({-1 if flip_h else 1},{-1 if flip_v else 1})" if flip_h or flip_v else ""
        holder = f'<div class="dml" style="left:0;top:0;width:100%;height:100%{flips}">{members}</div>'
        return self._box(x, y, w, h, holder, rotation)

    # -- shapes -----------------------------------------------------------------------

    def _shape(self, node, x, y, w, h, rotation, flip_h, flip_v) -> str:
        sp_pr = _child(node, "spPr")
        style = _child(node, "style")
        canvas = Canvas(self.palette, self.part.image_uri if self.part is not None else None)
        outline = canvas.shape_paths(sp_pr, style, w, h) if self._has_geometry(sp_pr) or style is not None else ""
        inner = self._svg(canvas, outline, w, h, flip_h, flip_v) if outline else ""
        body = _child(node, "txBody")
        if body is not None and any((t.text or "").strip() for t in body.iter(A + "t")):
            area = None
            placed = _child(node, "txXfrm")              # SmartArt keeps its text box apart
            if placed is not None and placed.find(A + "off") is not None and placed.find(A + "ext") is not None:
                own = xfrm_of(node)
                tx, ty = emu(placed.find(A + "off").get("x")), emu(placed.find(A + "off").get("y"))
                tw, th = emu(placed.find(A + "ext").get("cx")), emu(placed.find(A + "ext").get("cy"))
                if own is not None:
                    area = (tx - own[0], ty - own[1], tx - own[0] + tw, ty - own[1] + th)
            inner += self._text(node, body, sp_pr, style, w, h, rotation, flip_v, area)
        if not inner:
            return ""
        return self._box(x, y, w, h, inner, rotation)

    @staticmethod
    def _has_geometry(sp_pr) -> bool:
        return sp_pr is not None and (sp_pr.find(A + "prstGeom") is not None or sp_pr.find(A + "custGeom") is not None)

    def _text(self, node, body, sp_pr, style, w, h, rotation=0.0, flip_v=False, area=None) -> str:
        body_pr = body.find(A + "bodyPr")
        chain, color, size = (self.text_for(node) if self.text_for else (None, None, None)) or (None, None, None)
        override = False
        if style is not None:
            font = style.find(A + "fontRef")
            found = self.palette.first_color(font) if font is not None else None
            if found:
                color, override = found[0], True
        scale, cut = autofit(body_pr)
        renderer = TextRenderer(self.palette, self.unit, chain or TextStyle(), color, scale, cut, self.fields,
                                size or self.default_size, self.part.image_uri if self.part is not None else None,
                                override)
        paragraphs = renderer.body_html(body)
        left, top, right, bottom = area if area is not None else text_area(sp_pr, w, h)
        inset = body_insets(body_pr)
        left, top, right, bottom = left + inset[0], top + inset[1], right - inset[2], bottom - inset[3]
        get = body_pr.get if body_pr is not None else (lambda *_: None)
        anchor = {"ctr": "center", "b": "flex-end", "just": "center", "dist": "center"}.get(get("anchor") or "", "flex-start")
        css = [f"left:{self.unit(left)}", f"top:{self.unit(top)}", f"width:{self.unit(max(0.0, right - left))}",
               f"height:{self.unit(max(0.0, bottom - top))}", f"justify-content:{anchor}"]
        mode = WRITING.get(get("vert") or "")
        if mode:
            css.append("writing-mode:" + mode)
        unwrapped = get("wrap") == "none"
        if _flag(get("anchorCtr")):
            css.append("align-items:center")
        turn = _num(get("rot")) / 60000.0
        if _flag(get("upright")):
            turn -= rotation
        if flip_v:
            turn += 180.0
        names = "dml-text unwrapped" if unwrapped else "dml-text"
        text = f'<div class="{names}" style="{";".join(css)}"><div class="dml-flow">{paragraphs}</div></div>'
        if turn:
            text = f'<div class="dml" style="left:0;top:0;width:100%;height:100%;transform:rotate({turn:.3f}deg)">{text}</div>'
        return text

    # -- pictures ---------------------------------------------------------------------

    def _picture(self, node, x, y, w, h, rotation, flip_h, flip_v) -> str:
        fill = _child(node, "blipFill")
        blip = fill.find(A + "blip") if fill is not None else None
        rid = next((v for k, v in blip.attrib.items() if k in (R + "embed",)), None) if blip is not None else None
        uri = self.part.image_uri(rid) if rid and self.part is not None else None
        sp_pr = _child(node, "spPr")
        canvas = Canvas(self.palette, self.part.image_uri if self.part is not None else None)
        crop = fill.find(A + "srcRect") if fill is not None else None
        left, top, right, bottom = ((_num(crop.get(k)) / 100000.0 for k in ("l", "t", "r", "b")) if crop is not None
                                    else (0.0, 0.0, 0.0, 0.0))
        shown_w, shown_h = max(1e-6, 1 - left - right), max(1e-6, 1 - top - bottom)
        image_w, image_h = w / shown_w, h / shown_h
        image_x, image_y = -left * image_w, -top * image_h
        filters = []
        opacity = ""
        if blip is not None:
            if blip.find(A + "grayscl") is not None:
                filters.append("grayscale(1)")
            amount = blip.find(A + "alphaModFix")
            if amount is not None:
                opacity = f' opacity="{_num(amount.get("amt"), 100000.0) / 100000.0:.3f}"'
            light = blip.find(A + "lum")
            if light is not None:
                bright, contrast = _num(light.get("bright")) / 100000.0, _num(light.get("contrast")) / 100000.0
                if bright:
                    filters.append(f"brightness({1 + bright:.3f})")
                if contrast:
                    filters.append(f"contrast({1 + contrast:.3f})")
            if blip.find(A + "duotone") is not None:
                filters.append("grayscale(1)")
        filtered = f' style="filter:{" ".join(filters)}"' if filters else ""
        clip = ""
        pieces = geometry(sp_pr, w, h) if sp_pr is not None else []
        if sp_pr is not None and sp_pr.find(A + "prstGeom") is not None and sp_pr.find(A + "prstGeom").get("prst") not in (None, "rect"):
            name = f"pc{id(node)}"
            canvas.defs.append(f'<clipPath id="{name}"><path d="{" ".join(d for d, m in pieces if m != "nofill")}"/></clipPath>')
            clip = f' clip-path="url(#{name})"'
        body = ""
        if uri:
            body = (f'<image href="{uri}" x="{image_x:.3f}" y="{image_y:.3f}" width="{image_w:.3f}" height="{image_h:.3f}" '
                    f'preserveAspectRatio="none"{opacity}{filtered}{clip}/>')
            if not clip:
                name = f"pr{id(node)}"
                canvas.defs.append(f'<clipPath id="{name}"><rect width="{w:.3f}" height="{h:.3f}"/></clipPath>')
                body = f'<g clip-path="url(#{name})">{body}</g>'
        line = sp_pr.find(A + "ln") if sp_pr is not None else None
        if line is not None and line.find(A + "noFill") is None:
            stroke = canvas.stroke(line)
            outline = " ".join(d for d, _ in pieces) or f"M0 0H{w:.3f}V{h:.3f}H0Z"
            body += f'<path d="{outline}" fill="none" {stroke}/>'
        if not body:
            return ""
        return self._box(x, y, w, h, self._svg(canvas, body, w, h, flip_h, flip_v), rotation)

    # -- graphic frames -----------------------------------------------------------------

    def _frame(self, node, x, y, w, h) -> str:
        graphic = node.find(A + "graphic")
        data = graphic.find(A + "graphicData") if graphic is not None else None
        if data is None:
            return ""
        for item in data:
            tag = item.tag
            if tag == C + "chart":
                return self._box(x, y, w, h, self._chart(item, w, h))
            if tag == CX + "chart":
                return self._box(x, y, w, h, self._chart(item, w, h, ex=True))
            if tag == A + "tbl":
                return self._box(x, y, w, h, self._table(item, w, h), extra=";overflow:visible")
            if tag == DGM + "relIds":
                return self._box(x, y, w, h, self._diagram(item, w, h))
            if tag == MC + "AlternateContent":
                for chosen in resolve_alternate(item):
                    if local(chosen.tag) in ("oleObj", "pic"):
                        picture = chosen if local(chosen.tag) == "pic" else _child(chosen, "pic")
                        if picture is not None:
                            return self.node_html(picture, box=(x, y, w, h))
            if local(tag) == "oleObj":
                picture = _child(item, "pic")
                if picture is not None:
                    return self.node_html(picture, box=(x, y, w, h))
        return ""

    def _chart(self, item, w, h, ex=False) -> str:
        part = self.part.related(item.get(R + "id")) if self.part is not None else None
        if part is None or part.xml() is None:
            return ""
        if ex:
            from .chartex import chartex_html

            return chartex_html(part.xml(), self.palette, w, h, self.unit, part.image_uri, True)
        from .charts import chart_html

        return chart_html(part.xml(), self.palette, w, h, self.unit, part.image_uri, True)

    def _diagram(self, item, w, h) -> str:
        """SmartArt as Office last drew it: the drawing part the file keeps."""
        data = self.part.related(item.get(R + "dm")) if self.part is not None else None
        if data is None or data.xml() is None:
            return ""
        note = next(data.xml().iter(DSP + "dataModelExt"), None)
        drawing = self.part.related(note.get("relId")) if note is not None else None
        if drawing is None or drawing.xml() is None:
            return ""
        tree = next(drawing.xml().iter(DSP + "spTree"), None)
        if tree is None:
            return ""
        saved, self.part = self.part, drawing
        try:
            return self.tree_html(tree)
        finally:
            self.part = saved

    # -- tables -----------------------------------------------------------------------

    def _table(self, table, w, h) -> str:
        from .dml_tables import table_html

        return table_html(self, table, w, h)


def color_html(palette, element) -> str | None:
    found = palette.first_color(element) if element is not None else None
    return found[0] if found else None


__all__ = ["ShapeRenderer", "resolve_alternate", "xfrm_of", "local", "PRESET_COLORS", "etree", "html", "math"]
