"""DrawingML text, the text of PowerPoint slides and of shapes in Excel, as HTML.

A text body's paragraphs take their look from a chain of list styles (the
presentation's defaults, the slide master's title/body/other styles, the
master's and layout's placeholder, the shape's own), level by level, then
from the paragraph and run properties themselves. Bullets and numbers,
spacing in points or as a share of the line, autofit's font scale and line
reduction, fields such as the slide number, and right-to-left paragraphs are
all honoured. Line heights follow the fonts' own measures, as PowerPoint's do.
"""
from __future__ import annotations

import html
import re

from .drawingml import A, Palette, emu
from .winfonts import font_info

NUMBERING = {
    "arabicPeriod": ("1", "", "."), "arabicParenR": ("1", "", ")"), "arabicParenBoth": ("1", "(", ")"),
    "arabicPlain": ("1", "", ""), "arabicDbPeriod": ("1", "", "."), "arabicDbPlain": ("1", "", ""),
    "romanUcPeriod": ("I", "", "."), "romanLcPeriod": ("i", "", "."), "romanUcParenR": ("I", "", ")"),
    "romanLcParenR": ("i", "", ")"), "romanUcParenBoth": ("I", "(", ")"), "romanLcParenBoth": ("i", "(", ")"),
    "alphaUcPeriod": ("A", "", "."), "alphaLcPeriod": ("a", "", "."), "alphaUcParenR": ("A", "", ")"),
    "alphaLcParenR": ("a", "", ")"), "alphaUcParenBoth": ("A", "(", ")"), "alphaLcParenBoth": ("a", "(", ")"),
    "arabic1Minus": ("1", "", "-"), "arabic2Minus": ("1", "", "-"), "hindiAlphaPeriod": ("أ", "", "."),
    "hindiNumPeriod": ("١", "", "."), "hindiNumParenR": ("١", "", ")"), "arabicAbjadDash": ("أ", "", "-"),
    "arabicAlphaDash": ("أ", "", "-"), "circleNumDbPlain": ("1", "", ""), "circleNumWdBlackPlain": ("1", "", ""),
    "circleNumWdWhitePlain": ("1", "", ""),
}
ABJAD = "أبجدهوزحطيكلمنسعفصقرشتثخذضظغ"
ALPHA = "أبتثجحخدذرزسشصضطظعغفقكلمنهوي"
#: Paragraph properties that come from the list styles, and the run properties in their defRPr.
PARAGRAPH_KEYS = ("marL", "marR", "indent", "algn", "rtl", "defTabSz", "fontAlgn", "lvl")
PARAGRAPH_CHILDREN = ("lnSpc", "spcBef", "spcAft", "buClrTx", "buClr", "buSzTx", "buSzPct", "buSzPts", "buFontTx",
                      "buFont", "buNone", "buAutoNum", "buChar", "buBlip", "tabLst")
RUN_KEYS = ("sz", "b", "i", "u", "strike", "baseline", "cap", "spc", "kern", "lang")
RUN_CHILDREN = ("ln", "noFill", "solidFill", "gradFill", "highlight", "latin", "ea", "cs", "sym", "hlinkClick", "effectLst")


def _merge(target: dict, element, keys, children) -> None:
    if element is None:
        return
    for key in keys:
        if element.get(key) is not None:
            target[key] = element.get(key)
    groups = {"bullet": ("buNone", "buAutoNum", "buChar", "buBlip"), "bucolor": ("buClrTx", "buClr"),
              "busize": ("buSzTx", "buSzPct", "buSzPts"), "bufont": ("buFontTx", "buFont"),
              "fill": ("noFill", "solidFill", "gradFill")}
    for child in element:
        if not isinstance(child.tag, str) or not child.tag.startswith(A):
            continue
        name = child.tag[len(A):]
        if name not in children:
            continue
        for members in groups.values():          # one of a group replaces the others
            if name in members:
                for other in members:
                    target.pop("@" + other, None)
        target["@" + name] = child


class TextStyle:
    """Level properties (paragraph and default run) from a chain of list styles."""

    def __init__(self, chain=()):
        self.chain = [style for style in chain if style is not None]

    def level(self, level: int) -> tuple[dict, dict]:
        paragraph, run = {}, {}
        for style in self.chain:
            props = style.find(f"{A}lvl{level + 1}pPr")
            if props is None and level == 0 and style.tag == A + "pPr":
                props = style
            if props is None:
                continue
            _merge(paragraph, props, PARAGRAPH_KEYS, PARAGRAPH_CHILDREN)
            _merge(run, props.find(A + "defRPr"), RUN_KEYS, RUN_CHILDREN)
        return paragraph, run

    def then(self, *more) -> "TextStyle":
        return TextStyle(self.chain + [m for m in more if m is not None])


def _int(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _roman(number: int) -> str:
    out = ""
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
                           (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while number >= value:
            out += letters
            number -= value
    return out


def _counter(kind: str, number: int) -> str:
    first, before, after = NUMBERING.get(kind, ("1", "", "."))
    if first == "I":
        text = _roman(number).upper()
    elif first == "i":
        text = _roman(number)
    elif first == "A":
        text = chr(65 + (number - 1) % 26) * ((number - 1) // 26 + 1)
    elif first == "a":
        text = chr(97 + (number - 1) % 26) * ((number - 1) // 26 + 1)
    elif first == "١":
        text = "".join(chr(0x0660 + int(d)) for d in str(number))
    elif first == "أ":
        text = (ABJAD if "Abjad" in kind else ALPHA)[(number - 1) % 28]
    else:
        text = str(number)
    return before + text + after


class TextRenderer:
    """Paragraphs of one text body as HTML; lengths through ``unit`` (points to CSS)."""

    def __init__(self, palette: Palette, unit, style: TextStyle | None = None, default_color: str | None = None,
                 font_scale: float = 1.0, spacing_cut: float = 0.0, fields: dict | None = None,
                 default_size: float = 18.0, image_uri=None, override: bool = False):
        """With ``override``, ``default_color`` (a shape style's or table style's text colour)
        wins over the colours of the inherited list styles, as it does in Office; the
        body's own list style and its runs still win over it."""
        self.override = override
        self.palette = palette
        self.unit = unit
        self.style = style or TextStyle()
        self.default_color = default_color
        self.font_scale = font_scale
        self.spacing_cut = spacing_cut
        self.fields = fields or {}
        self.default_size = default_size
        self.image_uri = image_uri

    # -- the whole body -------------------------------------------------------------

    def body_html(self, body) -> str:
        own = body.find(A + "lstStyle") if body is not None else None
        style = self.style if self.override else self.style.then(own)
        own_style = TextStyle([own]) if self.override else None
        out = []
        counters: dict[int, int] = {}
        last_kind: dict[int, str] = {}
        paragraphs = body.findall(A + "p") if body is not None else []
        for index, paragraph in enumerate(paragraphs):
            props = paragraph.find(A + "pPr")
            level = int(_int(props.get("lvl") if props is not None else None, 0))
            level = max(0, min(8, level))
            base_paragraph, base_run = style.level(level)
            if own_style is not None:
                for key in ("@solidFill", "@gradFill", "@noFill"):
                    base_run.pop(key, None)
                extra_paragraph, extra_run = own_style.level(level)
                base_paragraph.update(extra_paragraph)
                base_run.update(extra_run)
            merged = dict(base_paragraph)
            _merge(merged, props, PARAGRAPH_KEYS, PARAGRAPH_CHILDREN)
            numbered = merged.get("@buAutoNum")
            has_text = any((r.findtext(A + "t") or "") for r in paragraph if r.tag in (A + "r", A + "fld"))
            # Numbering counts on through paragraphs of the same level and kind.
            for deeper in [k for k in counters if k > level]:
                counters.pop(deeper, None)
            if numbered is not None and has_text:
                kind = numbered.get("type") or "arabicPeriod"
                start = int(_int(numbered.get("startAt"), 1))
                if last_kind.get(level) != kind or level not in counters:
                    counters[level] = start
                else:
                    counters[level] += 1
                last_kind[level] = kind
                number = counters[level]
            else:
                if not has_text:
                    pass
                elif numbered is None:
                    counters.pop(level, None)
                    last_kind.pop(level, None)
                number = 0
            out.append(self._paragraph(paragraph, merged, base_run, number, index == 0))
        return "".join(out)

    # -- one paragraph ----------------------------------------------------------------

    def _paragraph(self, paragraph, props: dict, base_run: dict, number: int, first: bool) -> str:
        rtl = props.get("rtl") == "1"
        spans, sizes, first_run = [], [], None
        line_factor = self._line_factor(props)
        exact = self._exact_line(props)
        for node in paragraph:
            kind = node.tag[len(A):] if isinstance(node.tag, str) and node.tag.startswith(A) else ""
            if kind == "br":
                spans.append("<br>")
                continue
            if kind not in ("r", "fld"):
                continue
            run = dict(base_run)
            _merge(run, node.find(A + "rPr"), RUN_KEYS, RUN_CHILDREN)
            text = node.findtext(A + "t") or ""
            if kind == "fld":
                text = self.fields.get(node.get("type") or "", text)
            size = self._size(run)
            sizes.append(size)
            if first_run is None:
                first_run = run
            css = self._run_css(run, size, line_factor, exact)
            shown = html.escape(self._caps(text, run), quote=False)
            link = node.find(A + "rPr")
            spans.append(f'<span style="{css}">{shown}</span>')
        end = dict(base_run)
        _merge(end, paragraph.find(A + "endParaRPr"), RUN_KEYS, RUN_CHILDREN)
        end_size = self._size(end)
        size = max(sizes) if sizes else end_size
        css = []
        align = props.get("algn") or "l"
        css.append("text-align:" + {"ctr": "center", "r": "right", "l": "left",
                                     "just": "justify", "justLow": "justify", "dist": "justify",
                                     "thaiDist": "justify"}.get(align, "left"))
        if align == "dist":
            css.append("text-align-last:justify")
        left = emu(props.get("marL"))
        right = emu(props.get("marR"))
        indent = emu(props.get("indent"))
        if left:
            css.append(f"padding-inline-start:{self.unit(left)}")
        if right:
            css.append(f"padding-inline-end:{self.unit(right)}")
        before = self._space(props.get("@spcBef"), size, line_factor)
        after = self._space(props.get("@spcAft"), size, line_factor)
        if before and not first:
            css.append(f"margin-top:{self.unit(before)}")
        if after:
            css.append(f"margin-bottom:{self.unit(after)}")
        tab = emu(props.get("defTabSz"), 72.0) or 72.0
        css.append(f"tab-size:{self.unit(tab)}")
        bullet = self._bullet(props, first_run or end, size, number) if spans else ""
        if bullet:
            width = max(0.0, -indent)
            css.append(f"text-indent:{self.unit(indent)}" if indent else "")
            spans.insert(0, f'<span class="bu" style="display:inline-block;min-width:{self.unit(width)};text-indent:0;'
                            f'{bullet[1]}">{bullet[0]}</span>')
        elif indent:
            css.append(f"text-indent:{self.unit(indent)}")
        if not spans:
            spans.append(f'<span style="{self._run_css(end, end_size, line_factor, exact)}">&#8203;</span>')
        css = ";".join(c for c in css if c)
        return f'<div class="p" dir="{"rtl" if rtl else "ltr"}" style="{css}">{"".join(spans)}</div>'

    # -- measures -------------------------------------------------------------------

    def _size(self, run: dict) -> float:
        size = _int(run.get("sz"), self.default_size * 100) / 100.0
        return max(1.0, size * self.font_scale)

    def _line_factor(self, props: dict) -> float:
        spacing = props.get("@lnSpc")
        percent = spacing.find(A + "spcPct") if spacing is not None else None
        factor = _int(percent.get("val"), 100000.0) / 100000.0 if percent is not None else 1.0
        return max(0.1, factor - self.spacing_cut)

    @staticmethod
    def _exact_line(props: dict):
        spacing = props.get("@lnSpc")
        points = spacing.find(A + "spcPts") if spacing is not None else None
        return _int(points.get("val")) / 100.0 if points is not None else None

    def _space(self, holder, size: float, line_factor: float) -> float:
        if holder is None:
            return 0.0
        percent, points = holder.find(A + "spcPct"), holder.find(A + "spcPts")
        if points is not None:
            return _int(points.get("val")) / 100.0
        if percent is not None:
            return _int(percent.get("val")) / 100000.0 * size * 1.2
        return 0.0

    # -- runs -----------------------------------------------------------------------

    def _family(self, run: dict) -> list[str]:
        names = []
        for slot in ("@latin", "@cs", "@ea"):
            face = run.get(slot)
            if face is not None and face.get("typeface"):
                name = self.palette.font(face.get("typeface"))
                if name and name not in names:
                    names.append(name)
        for name in (self.palette.fonts.get("minorLatin"), self.palette.fonts.get("minorBidi"), "Arial"):
            if name and name not in names:
                names.append(name)
        return names

    def _run_css(self, run: dict, size: float, line_factor: float, exact) -> str:
        names = self._family(run)
        family = ", ".join("'" + n.replace("'", "") + "'" for n in names)
        metrics = font_info(names[0])
        if exact is not None:
            height = f"{self.unit(exact)}"
        else:
            height = f"{metrics.line * line_factor:.4f}"
        css = [f"font-family:{family}", f"font-size:{self.unit(size)}", f"line-height:{height}", "white-space:pre-wrap"]
        if run.get("b") in ("1", "true"):
            css.append("font-weight:bold")
        if run.get("i") in ("1", "true"):
            css.append("font-style:italic")
        decorations = []
        if run.get("u") not in (None, "none"):
            decorations.append("underline")
            if run.get("u") in ("dbl", "dblHeavy"):
                css.append("text-decoration-style:double")
        if run.get("strike") not in (None, "noStrike"):
            decorations.append("line-through")
        if run.get("@hlinkClick") is not None:
            decorations.append("underline")
        if decorations:
            css.append("text-decoration-line:" + " ".join(dict.fromkeys(decorations)))
        baseline = _int(run.get("baseline"))
        if baseline:
            css.append(f"vertical-align:{baseline / 1000.0:.1f}%")
        spacing = _int(run.get("spc"))
        if spacing:
            css.append(f"letter-spacing:{self.unit(spacing / 100.0)}")
        if run.get("cap") == "small":
            css.append("font-variant-caps:small-caps")
        color = self._color(run)
        if color:
            css.append(f"color:#{color[0]}" + (f";opacity:{color[1]:.3f}" if color[1] < 1 else ""))
        highlight = run.get("@highlight")
        if highlight is not None:
            found = self.palette.first_color(highlight)
            if found:
                css.append(f"background:#{found[0]}")
        return ";".join(css)

    def _color(self, run: dict):
        if run.get("@noFill") is not None:
            return ("FFFFFF", 0.0)
        fill = run.get("@solidFill")
        if fill is not None:
            return self.palette.first_color(fill, self.default_color)
        gradient = run.get("@gradFill")
        if gradient is not None:
            stop = next(gradient.iter(A + "gs"), None)
            if stop is not None:
                return self.palette.first_color(stop, self.default_color)
        if run.get("@hlinkClick") is not None:
            return (self.palette.scheme_color("hlink"), 1.0)
        if self.default_color:
            return (self.default_color, 1.0)
        return None

    @staticmethod
    def _caps(text: str, run: dict) -> str:
        return text.upper() if run.get("cap") == "all" else text

    # -- bullets ------------------------------------------------------------------------

    def _bullet(self, props: dict, run: dict, size: float, number: int):
        """(HTML, CSS) of a paragraph's bullet or number, or None."""
        if props.get("@buNone") is not None:
            return None
        char, numbered, picture = props.get("@buChar"), props.get("@buAutoNum"), props.get("@buBlip")
        if char is None and numbered is None and picture is None:
            return None
        scale = 1.0
        if props.get("@buSzPct") is not None:
            scale = _int(props["@buSzPct"].get("val"), 100000.0) / 100000.0
        bullet_size = size * scale
        if props.get("@buSzPts") is not None:
            bullet_size = _int(props["@buSzPts"].get("val")) / 100.0 * self.font_scale
        color = None
        if props.get("@buClr") is not None:
            found = self.palette.first_color(props["@buClr"])
            color = found[0] if found else None
        if color is None:
            found = self._color(run)
            color = found[0] if found else None
        family = self._family(run)
        if props.get("@buFont") is not None and props["@buFont"].get("typeface"):
            family = [self.palette.font(props["@buFont"].get("typeface"))] + family
        css = [f"font-size:{self.unit(bullet_size)}", "font-family:" + ", ".join("'" + n + "'" for n in family)]
        if color:
            css.append(f"color:#{color}")
        if picture is not None:
            blip = picture.find(A + "blip")
            rid = next((v for k, v in blip.attrib.items() if k.endswith("}embed")), None) if blip is not None else None
            uri = self.image_uri(rid) if rid and self.image_uri else None
            if uri:
                return (f'<img alt="" src="{uri}" style="height:{self.unit(bullet_size)};vertical-align:baseline">&#160;',
                        ";".join(css))
            return ("&#8226;&#160;", ";".join(css))
        if numbered is not None:
            return (html.escape(_counter(numbered.get("type") or "arabicPeriod", max(1, number))) + "&#160;", ";".join(css))
        text = char.get("char") or "&#8226;"
        return (html.escape(text, quote=False) + "&#160;", ";".join(css))


def body_insets(body_pr) -> tuple[float, float, float, float]:
    """A text body's insets in points: left, top, right, bottom (PowerPoint's defaults)."""
    get = body_pr.get if body_pr is not None else (lambda *_: None)
    return (emu(get("lIns"), 7.2), emu(get("tIns"), 3.6), emu(get("rIns"), 7.2), emu(get("bIns"), 3.6))


def autofit(body_pr) -> tuple[float, float]:
    """(font scale, line spacing cut) from a body's normAutofit."""
    if body_pr is None:
        return 1.0, 0.0
    fit = body_pr.find(A + "normAutofit")
    if fit is None:
        return 1.0, 0.0
    return _int(fit.get("fontScale"), 100000.0) / 100000.0, _int(fit.get("lnSpcReduction"), 0.0) / 100000.0


def plain_text(body) -> str:
    if body is None:
        return ""
    return "\n".join("".join(node.findtext(A + "t") or "" for node in paragraph if node.tag in (A + "r", A + "fld"))
                     for paragraph in body.findall(A + "p"))


_SPACES = re.compile(" {2,}")
