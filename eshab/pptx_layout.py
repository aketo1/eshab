"""PowerPoint presentations laid out as print-faithful HTML, one page per slide.

Each slide is drawn the way PowerPoint draws it: the master's background and
graphics, the layout's, then the slide's own shapes. Placeholders take their
place, outline and text styles from the layout and master placeholders they
match (by index, then by type); text cascades from the presentation's
defaults through the master's title, body and other styles. Colours resolve
through the theme and the master's colour map (with any slide override),
fonts through the theme's font scheme. Hidden slides are left out, as
PowerPoint leaves them out of a PDF.
"""
from __future__ import annotations

import html
import logging
from pathlib import Path

from .drawingml import A, Canvas, Palette, emu
from .dml_shapes import P, R, ShapeRenderer, local, resolve_alternate, xfrm_of
from .dml_text import TextStyle
from .opc import Package, PartView

log = logging.getLogger("eshab")

SCALE = 4
TITLES = ("title", "ctrTitle")
#: What a slide placeholder looks for on the master, by its type.
MASTER_TYPE = {"ctrTitle": "title", "title": "title", "subTitle": "body", "obj": "body", "body": "body", "dt": "dt",
               "ftr": "ftr", "sldNum": "sldNum", "pic": "body", "chart": "body", "tbl": "body", "dgm": "body",
               "media": "body", "clipArt": "body", "sldImg": "sldImg", "hdr": "hdr"}


def _u(points: float) -> str:
    return f"{points * SCALE:.3f}pt"


def _ph(node):
    """(type, idx) of a shape's placeholder, or None."""
    for holder in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr", "nvCxnSpPr"):
        nv = node.find(P + holder)
        if nv is None:
            continue
        ph = nv.find(f"{P}nvPr/{P}ph")
        if ph is not None:
            return ph.get("type") or "obj", ph.get("idx")
    return None


def _placeholders(tree) -> tuple[dict, dict]:
    by_idx, by_type = {}, {}
    if tree is None:
        return by_idx, by_type
    for node in tree.iter(P + "sp", P + "pic", P + "graphicFrame"):
        found = _ph(node)
        if found is None:
            continue
        kind, idx = found
        if idx is not None and idx not in by_idx:
            by_idx[idx] = node
        by_type.setdefault(kind, node)
    return by_idx, by_type


class Theme:
    def __init__(self, root):
        self.colors, self.fonts, self.fills, self.lines, self.effects, self.backgrounds = {}, {}, [], [], None, []
        if root is None:
            return
        scheme = root.find(f".//{A}clrScheme")
        for child in (scheme if scheme is not None else []):
            srgb, system = child.find(A + "srgbClr"), child.find(A + "sysClr")
            name = local(child.tag)
            if srgb is not None:
                self.colors[name] = srgb.get("val")
            elif system is not None:
                self.colors[name] = system.get("lastClr") or ("000000" if system.get("val") == "windowText" else "FFFFFF")
        for kind in ("major", "minor"):
            font = root.find(f".//{A}{kind}Font")
            if font is None:
                continue
            latin, cs = font.find(A + "latin"), font.find(A + "cs")
            arabic = next((f.get("typeface") for f in font.findall(A + "font") if f.get("script") == "Arab"), "")
            self.fonts[kind + "Latin"] = latin.get("typeface") if latin is not None else ""
            self.fonts[kind + "Bidi"] = (cs.get("typeface") if cs is not None and cs.get("typeface") else arabic) or arabic
        looks = root.find(f".//{A}fmtScheme")
        if looks is not None:
            for name, target in (("fillStyleLst", self.fills), ("lnStyleLst", self.lines), ("bgFillStyleLst", self.backgrounds)):
                found = looks.find(A + name)
                if found is not None:
                    target.extend(list(found))
            effects = looks.find(A + "effectStyleLst")
            self.effects = list(effects) if effects is not None else None


def _color_map(element) -> dict:
    if element is None:
        return {}
    return {key: value for key, value in element.attrib.items()}


class Presentation:
    def __init__(self, path: Path):
        self.package = Package(path)
        self.root = self.package.xml("ppt/presentation.xml")
        if self.root is None:
            raise ValueError("not a presentation")
        size = self.root.find(P + "sldSz")
        self.width = emu(size.get("cx"), 720.0) if size is not None else 720.0
        self.height = emu(size.get("cy"), 405.0) if size is not None else 405.0
        self.default_text = self.root.find(P + "defaultTextStyle")
        self.first_number = int(self.root.get("firstSlideNum") or 1)
        styles = self.package.by_type("ppt/presentation.xml", "/tableStyles")
        self.table_styles = {}
        if styles:
            root = self.package.xml(styles[0])
            if root is not None:
                for style in root.findall(A + "tblStyle"):
                    self.table_styles[style.get("styleId")] = style
                if root.get("def"):
                    self.table_styles["__default__"] = root.get("def")

    def slides(self) -> list[str]:
        out = []
        listed = self.root.find(P + "sldIdLst")
        for item in (listed if listed is not None else []):
            target = self.package.target("ppt/presentation.xml", item.get(R + "id"))
            if target and self.package.has(target):
                out.append(target)
        return out

    def close(self) -> None:
        self.package.close()


class SlideDrawer:
    """One slide, through its layout and master."""

    def __init__(self, presentation: Presentation, name: str, number: int):
        self.pres = presentation
        package = presentation.package
        self.slide = PartView(package, name)
        layouts = self.slide.by_type("/slideLayout")
        self.layout = layouts[0] if layouts else None
        masters = self.layout.by_type("/slideMaster") if self.layout is not None else []
        self.master = masters[0] if masters else None
        themes = self.master.by_type("/theme") if self.master is not None else []
        theme = Theme(themes[0].xml() if themes else None)
        self.slide_root = self.slide.xml()
        self.layout_root = self.layout.xml() if self.layout is not None else None
        self.master_root = self.master.xml() if self.master is not None else None
        mapping = _color_map(self.master_root.find(P + "clrMap") if self.master_root is not None else None)
        for root in (self.layout_root, self.slide_root):
            override = root.find(f"{P}clrMapOvr/{A}overrideClrMapping") if root is not None else None
            if override is not None:
                mapping = _color_map(override)
        self.palette = Palette(theme.colors, mapping, theme.fills, theme.lines, theme.fonts, theme.effects)
        self.theme = theme
        self.number = number
        self.master_ph = _placeholders(self._tree(self.master_root))
        self.layout_ph = _placeholders(self._tree(self.layout_root))
        styles = self.master_root.find(P + "txStyles") if self.master_root is not None else None
        self.title_style = styles.find(P + "titleStyle") if styles is not None else None
        self.body_style = styles.find(P + "bodyStyle") if styles is not None else None
        self.other_style = styles.find(P + "otherStyle") if styles is not None else None

    @staticmethod
    def _tree(root):
        return root.find(f"{P}cSld/{P}spTree") if root is not None else None

    # -- placeholders -------------------------------------------------------------------

    def _layout_match(self, node):
        found = _ph(node)
        if found is None:
            return None
        kind, idx = found
        by_idx, by_type = self.layout_ph
        if idx is not None and idx in by_idx:
            return by_idx[idx]
        for candidate in (kind, "obj" if kind == "body" else None, "title" if kind == "ctrTitle" else None,
                          "ctrTitle" if kind == "title" else None):
            if candidate is not None and by_type.get(candidate) is not None:
                return by_type[candidate]
        return None

    def _master_match(self, node):
        found = _ph(node)
        if found is None:
            return None
        kind = MASTER_TYPE.get(found[0], "body")
        return self.master_ph[1].get(kind)

    def chain_for(self, node, where: str = "slide"):
        """The placeholders a shape inherits from, nearest first."""
        if _ph(node) is None:
            return []
        out = []
        if where == "slide":
            layout = self._layout_match(node)
            if layout is not None:
                out.append(layout)
                master = self._master_match(layout)
            else:
                master = self._master_match(node)
            if master is not None:
                out.append(master)
        elif where == "layout":
            master = self._master_match(node)
            if master is not None:
                out.append(master)
        return out

    def text_for_factory(self, where: str):
        def text_for(node):
            found = _ph(node)
            inherited = self.chain_for(node, where)
            if found is None:
                base = self.other_style
            else:
                base = self.title_style if found[0] in TITLES else (
                    self.other_style if found[0] in ("dt", "ftr", "sldNum") else self.body_style)
            chain = [self.pres.default_text, base]
            for holder in reversed(inherited):                    # master first, then layout
                body = holder.find(P + "txBody")
                chain.append(body.find(A + "lstStyle") if body is not None else None)
            color = None
            if found is None and node.find(P + "style") is not None:
                font = node.find(P + "style").find(A + "fontRef")
                if font is not None:
                    hit = self.palette.first_color(font)
                    color = hit[0] if hit else None
            return TextStyle(chain), color, 18.0
        return text_for

    def inherit_factory(self, where: str):
        def inherit(node):
            for holder in self.chain_for(node, where):
                placed = xfrm_of(holder)
                if placed is not None:
                    return placed
            return None
        return inherit

    def _merged(self, node, where: str):
        """A copy of a placeholder shape with what it leaves out filled in from its layout and master."""
        inherited = self.chain_for(node, where)
        if not inherited:
            return node
        from copy import deepcopy

        node = deepcopy(node)
        sp_pr = node.find(P + "spPr")
        if sp_pr is None:
            sp_pr = node.makeelement(P + "spPr", {})
            node.insert(1, sp_pr)
        for holder in inherited:
            source = holder.find(P + "spPr")
            if source is None:
                continue
            for child in source:
                name = local(child.tag)
                group = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
                if name in group and any(local(c.tag) in group for c in sp_pr):
                    continue
                if name in ("prstGeom", "custGeom") and any(local(c.tag) in ("prstGeom", "custGeom") for c in sp_pr):
                    continue
                if sp_pr.find(child.tag) is None:
                    sp_pr.append(deepcopy(child))
        body = node.find(P + "txBody")
        if body is not None:
            body_pr = body.find(A + "bodyPr")
            for holder in inherited:
                source = holder.find(f"{P}txBody/{A}bodyPr")
                if source is None:
                    continue
                if body_pr is None:
                    body_pr = deepcopy(source)
                    body.insert(0, body_pr)
                    continue
                for key, value in source.attrib.items():
                    if body_pr.get(key) is None:
                        body_pr.set(key, value)
                for child in source:
                    if body_pr.find(child.tag) is None and local(child.tag) in ("normAutofit", "noAutofit", "spAutoFit"):
                        if not any(local(c.tag) in ("normAutofit", "noAutofit", "spAutoFit") for c in body_pr):
                            body_pr.append(deepcopy(child))
        return node

    # -- drawing --------------------------------------------------------------------------

    def background_html(self) -> str:
        for root, part in ((self.slide_root, self.slide), (self.layout_root, self.layout), (self.master_root, self.master)):
            background = root.find(f"{P}cSld/{P}bg") if root is not None else None
            if background is None:
                continue
            canvas = Canvas(self.palette, part.image_uri)
            fill, placeholder = None, None
            props = background.find(P + "bgPr")
            if props is not None:
                fill = canvas.fill_of(props)
            reference = background.find(P + "bgRef")
            if reference is not None:
                index = int(reference.get("idx") or 0)
                found = self.palette.first_color(reference)
                placeholder = found[0] if found else None
                if index >= 1001 and index - 1001 < len(self.theme.backgrounds):
                    fill = self.theme.backgrounds[index - 1001]
                elif index > 0 and index - 1 < len(self.theme.fills):
                    fill = self.theme.fills[index - 1]
                elif found:
                    return self._full(f'<rect width="{self.pres.width:.3f}" height="{self.pres.height:.3f}" fill="#{found[0]}"/>', canvas)
            if fill is None:
                continue
            if fill.tag == A + "blipFill":
                return self._picture_background(fill, part)
            paint = canvas.paint(fill, placeholder, (self.pres.width, self.pres.height))
            return self._full(f'<rect width="{self.pres.width:.3f}" height="{self.pres.height:.3f}" {paint}/>', canvas)
        white = self.palette.scheme_color("bg1")
        return f'<div class="bg" style="background:#{white}"></div>'

    def _full(self, body: str, canvas) -> str:
        return (f'<svg class="bg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.pres.width:.3f} {self.pres.height:.3f}" '
                f'preserveAspectRatio="none">{canvas.definitions()}{body}</svg>')

    def _picture_background(self, fill, part) -> str:
        blip = fill.find(A + "blip")
        rid = next((v for k, v in blip.attrib.items() if k.endswith("}embed")), None) if blip is not None else None
        uri = part.image_uri(rid) if rid else None
        if not uri:
            return ""
        if fill.find(A + "tile") is not None:
            return f'<div class="bg" style="background:url({uri}) repeat"></div>'
        return f'<img class="bg" alt="" src="{uri}">'

    def shapes_html(self) -> str:
        out = []
        show_master = (self.slide_root.get("showMasterSp") != "0") if self.slide_root is not None else True
        layout_master = (self.layout_root.get("showMasterSp") != "0") if self.layout_root is not None else True
        fields = {"slidenum": str(self.number)}
        layers = []
        if show_master and layout_master and self.master_root is not None:
            layers.append((self.master, self.master_root, "master"))
        if show_master and self.layout_root is not None:
            layers.append((self.layout, self.layout_root, "layout"))
        layers.append((self.slide, self.slide_root, "slide"))
        for part, root, where in layers:
            tree = self._tree(root)
            if tree is None:
                continue
            renderer = ShapeRenderer(part, self.palette, _u, self.text_for_factory(where), fields, 18.0,
                                     self.pres.table_styles, self.inherit_factory(where))
            renderer.table_text = TextStyle([self.pres.default_text, self.other_style])
            for node in tree:
                items = resolve_alternate(node) if local(node.tag) == "AlternateContent" else [node]
                for item in items:
                    if where != "slide" and _ph(item) is not None:
                        continue                 # layout and master placeholders only lend their looks
                    try:
                        out.append(renderer.node_html(self._merged(item, where) if _ph(item) is not None else item))
                    except Exception:
                        log.exception("could not draw a %s on slide %s", local(item.tag), self.number)
        return "".join(out)


BASE_CSS = """
html, body { margin: 0; padding: 0; }
body { -webkit-print-color-adjust: exact; print-color-adjust: exact; text-rendering: geometricPrecision; }
.page { position: relative; overflow: hidden; break-after: page; }
.page:last-of-type { break-after: auto; }
.bg { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: fill; }
.dml { position: absolute; }
.dml-text { position: absolute; display: flex; flex-direction: column; }
.dml-flow { display: flow-root; min-width: 0; }
.dml-text .p { margin: 0; overflow-wrap: break-word; }
.unwrapped .p { white-space: pre; }
.dml-table-box { position: absolute; left: 0; top: 0; }
.dml-table td { overflow-wrap: break-word; }
"""


def document_html(path: Path) -> str:
    presentation = Presentation(path)
    try:
        pages = []
        names = presentation.slides()
        for index, name in enumerate(names):
            root = presentation.package.xml(name)
            if root is None or root.get("show") == "0":
                continue
            drawer = SlideDrawer(presentation, name, presentation.first_number + index)
            pages.append(f'<div class="page" style="width:{_u(presentation.width)};height:{_u(presentation.height)}">'
                         f"{drawer.background_html()}{drawer.shapes_html()}</div>")
        if not pages:
            raise ValueError("no slides to print")
        width, height = presentation.width * SCALE, presentation.height * SCALE
        title = html.escape(Path(path).stem)
        return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
                f'<meta name="eshab-print-scale" content="{SCALE}">'
                f"<style>@page {{ size: {width:.3f}pt {height:.3f}pt; margin: 0; }}{BASE_CSS}</style></head>"
                f"<body>{''.join(pages)}</body></html>")
    finally:
        presentation.close()
