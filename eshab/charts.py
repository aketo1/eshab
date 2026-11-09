"""Office charts as SVG, drawn from the data cached inside the file.

Columns and bars (clustered, stacked, 100%), lines, areas, pies, doughnuts,
scatter, bubble and radar charts, and charts that combine them, with titles,
legends, axes, gridlines and data labels, following the settings stored in
the chart and Office's defaults where it stores none. One SVG unit is a point.
"""
from __future__ import annotations

import html
import math
import re
from collections import namedtuple
from datetime import datetime, timedelta

from .drawingml import A, Canvas, Palette
from .winfonts import font_info, text_width

C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
BRACKETS = re.compile(re.escape("[") + "[^" + re.escape("]") + "]*" + re.escape("]"))
DATE_TOKENS = re.compile('"[^"]*"|yyyy|yy|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|am/pm|a/p', re.I)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ARABIC = re.compile("[" + chr(0x0590) + "-" + chr(0x08FF) + chr(0xFB1D) + "-" + chr(0xFDFF) + chr(0xFE70) + "-" + chr(0xFEFF) + "]")
Style = namedtuple("Style", "size bold italic color family")
Frame = namedtuple("Frame", "x y w h")
MARKERS = ("diamond", "square", "triangle", "x", "star", "circle", "plus", "dot", "dash")
BAR_KINDS = ("barChart", "bar3DChart")
LINE_KINDS = ("lineChart", "line3DChart", "stockChart")
AREA_KINDS = ("areaChart", "area3DChart")
PIE_KINDS = ("pieChart", "pie3DChart", "ofPieChart")
XY_KINDS = ("scatterChart", "bubbleChart")
SURFACE_KINDS = ("surfaceChart", "surface3DChart")
OUTER = 11.0        # what Office leaves around a plot that has nothing else beside it
MID = 0.286         # how far below the middle of a label its baseline sits, in sizes
MAX_INTERVALS = 10  # an automatic axis never has more divisions than this
DISPLAY_UNITS = {"hundreds": 1e2, "thousands": 1e3, "tenThousands": 1e4, "hundredThousands": 1e5, "millions": 1e6,
                 "tenMillions": 1e7, "hundredMillions": 1e8, "billions": 1e9, "trillions": 1e12}


def _val(element, default=None):
    return element.get("val", default) if element is not None else default


def _flag(parent, name, default=False):
    element = parent.find(C + name) if parent is not None else None
    if element is None:
        return default
    return element.get("val", "1") in ("1", "true", "on")


def _number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _lighter(color: str, amount: float) -> str:
    """A colour moved towards white (amount > 0) or black (amount < 0)."""
    channels = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
    if amount >= 0:
        channels = [c + (255 - c) * amount for c in channels]
    else:
        channels = [c * (1 + amount) for c in channels]
    return "%02X%02X%02X" % tuple(int(max(0, min(255, c))) for c in channels)


def format_number(value, code: str | None) -> str:
    """A value through an Office number format (the common cases of it)."""
    if value is None:
        return ""
    code = (code or "General").split(";")
    section = code[1] if value < 0 and len(code) > 1 else code[0]
    negative = value < 0 and len(code) < 2
    magnitude = abs(value)
    if section.strip().lower() in ("general", ""):
        text = f"{magnitude:.10g}"
        if "e" in text:
            text = f"{magnitude:.2E}"
        return ("-" if value < 0 else "") + text
    section = BRACKETS.sub("", section).replace("_)", "").replace("_(", "")
    if re.search("[ymdhs]", re.sub('"[^"]*"', "", section), re.I):
        return _date_text(value, section)
    match = re.search("[#0,?]+([.][0#?]+)?", section)
    if not match:
        return section.replace('"', "")
    pattern = match.group(0)
    decimals = len(match.group(1)) - 1 if match.group(1) else 0
    if re.search("E[+-]", section):
        return ("-" if negative else "") + f"{magnitude:.{decimals}E}"
    percent = "%" in section
    if percent:
        magnitude *= 100
    magnitude += 0.5 * 10 ** -(decimals + 6)        # Office rounds halves up, not to even
    text = f"{magnitude:,.{decimals}f}" if "," in pattern else f"{magnitude:.{decimals}f}"
    before, after = section[:match.start()], section[match.end():]
    clean = lambda part: part.replace('"', "").replace("*", "").strip("_")
    return ("-" if negative else "") + clean(before) + text + clean(after)


def _date_text(value: float, section: str) -> str:
    """A date in a format such as d/m/yyyy or mmm-yy."""
    try:
        moment = datetime(1899, 12, 30) + timedelta(days=value)
    except (OverflowError, ValueError):
        return f"{value:g}"
    tokens = list(DATE_TOKENS.finditer(section))
    out, at = [], 0
    for index, match in enumerate(tokens):
        out.append(section[at:match.start()].replace('"', "").replace(chr(92), ""))
        at = match.end()
        token = match.group(0).lower()
        if token[0] == '"':
            out.append(match.group(0)[1:-1])
            continue
        before = tokens[index - 1].group(0).lower() if index else ""
        after = tokens[index + 1].group(0).lower() if index + 1 < len(tokens) else ""
        if token == "yyyy":
            out.append(f"{moment.year:04d}")
        elif token == "yy":
            out.append(f"{moment.year % 100:02d}")
        elif token in ("m", "mm") and (before[:1] == "h" or after[:1] == "s"):
            out.append(f"{moment.minute:02d}" if token == "mm" else str(moment.minute))
        elif token == "mmmm":
            out.append(MONTHS[moment.month - 1])
        elif token == "mmm":
            out.append(MONTHS[moment.month - 1][:3])
        elif token == "mm":
            out.append(f"{moment.month:02d}")
        elif token == "m":
            out.append(str(moment.month))
        elif token == "dddd":
            out.append(DAYS[moment.weekday()])
        elif token == "ddd":
            out.append(DAYS[moment.weekday()][:3])
        elif token == "dd":
            out.append(f"{moment.day:02d}")
        elif token == "d":
            out.append(str(moment.day))
        elif token in ("h", "hh"):
            twelve = any("/" in t.group(0) for t in tokens)
            hour = (moment.hour % 12 or 12) if twelve else moment.hour
            out.append(f"{hour:02d}" if token == "hh" else str(hour))
        elif token in ("s", "ss"):
            out.append(f"{moment.second:02d}" if token == "ss" else str(moment.second))
        else:
            out.append("PM" if moment.hour >= 12 else "AM")
    out.append(section[at:].replace('"', "").replace(chr(92), ""))
    return "".join(out)


def _steps(span: float):
    """The steps an axis can use, smallest first: 1, 2 and 5 times a power of ten."""
    power = math.floor(math.log10(span)) - 2 if span > 0 else -2
    while True:
        for factor in (1, 2, 5):
            yield factor * 10.0 ** power
        power += 1


def auto_scale(low, high, length, spacing, fixed_min=None, fixed_max=None, unit=None, across=False):
    """An axis's (minimum, maximum, step), the way Office picks them: the smallest
    usual step that leaves ``spacing`` points per division, ten divisions at most.
    Numbers side by side (``across``) count one division fewer."""
    if low is None:
        low, high = 0.0, 1.0
    if low == high:
        if low == 0:
            high = 1.0
        elif low > 0:
            low = 0.0
        else:
            high = 0.0
    start, stop = low, high
    if fixed_min is not None:
        start = fixed_min
    elif low >= 0 and (high - low) / high > 1 / 6:
        start = 0.0
    elif low > 0:
        start = low - (high - low) / 2
    elif low < 0:
        start = low - (high - low) * 0.05
    if fixed_max is not None:
        stop = fixed_max
    elif high <= 0 and (high - low) / abs(low) > 1 / 6:
        stop = 0.0
    elif high < 0:
        stop = high + (high - low) / 2
    elif high > 0:
        stop = high + (high - start) * 0.05
    answer = None
    for step in ([unit] if unit else _steps((stop - start) or 1.0)):
        bottom = start if fixed_min is not None else math.floor(start / step + 1e-9) * step
        top = stop if fixed_max is not None else math.ceil(stop / step - 1e-9) * step
        if top <= bottom:
            top = bottom + step
        answer = (bottom, top, step)
        count = round((top - bottom) / step)
        if unit or (count <= MAX_INTERVALS and length / max(count - (1 if across else 0), 1) >= spacing):
            return answer
        if (top - bottom) / step < 1.5:
            return answer
    return answer


def _ticks(start, stop, step):
    out, value = [], start
    if step < 0:                # a logarithmic axis: each mark a multiple of the last
        while value <= stop * (1 + 1e-9):
            out.append(value)
            value *= -step
        return out
    while value <= stop + step * 1e-6:
        out.append(round(value, 10))
        value += step
    return out


class _Series:
    def __init__(self, element, index):
        self.el = element
        self.index = index
        self.order = int(_number(_val(element.find(C + "order")), index))
        tx = element.find(C + "tx")
        self.name = ""
        if tx is not None:
            value = next(tx.iter(C + "v"), None)
            self.name = (value.text or "") if value is not None else ""
        self.categories = _strings(element.find(C + "cat"))
        values = element.find(C + "val")
        if values is None:
            values = element.find(C + "yVal")
        self.values, self.format = _numbers(values)
        self.category_numbers, _ = _numbers(element.find(C + "cat"))
        self.xs, self.x_format = _numbers(element.find(C + "xVal"))
        if self.categories is None and element.find(C + "xVal") is not None and not self.xs:
            self.categories = _strings(element.find(C + "xVal"))
        self.sizes, _ = _numbers(element.find(C + "bubbleSize"))
        self.points = {}
        for point in element.findall(C + "dPt"):
            self.points[int(_number(_val(point.find(C + "idx")), -1))] = point


def _numbers(element):
    if element is None:
        return [], None
    cache = next(element.iter(C + "numCache"), None)
    if cache is None:
        cache = element.find(C + "numLit")
    if cache is None:
        return [], None
    count = int(_number(_val(cache.find(C + "ptCount")), 0))
    points = cache.findall(C + "pt")
    values = [None] * max(count, max((int(p.get("idx", 0)) + 1 for p in points), default=0))
    for point in points:
        values[int(point.get("idx", 0))] = _number(point.findtext(C + "v"))
    return values, cache.findtext(C + "formatCode")


def _strings(element):
    if element is None:
        return None
    cache = next(element.iter(C + "strCache"), None)
    if cache is None:
        cache = element.find(C + "strLit")
    if cache is not None:
        return _string_points(cache)
    multi = next(element.iter(C + "multiLvlStrCache"), None)
    if multi is not None:                # each name goes with the outer groups that start at it
        levels = [_string_points(level) for level in multi.findall(C + "lvl")]
        if levels:
            out = levels[0]
            for outer in levels[1:]:
                for index, name in enumerate(outer):
                    if name and index < len(out):
                        out[index] = f"{out[index]} {name}".strip()
            return out
    numbers, code = _numbers(element)
    if numbers:
        return [format_number(v, code) for v in numbers]
    return None


def _string_points(cache) -> list:
    count = int(_number(_val(cache.find(C + "ptCount")), 0))
    points = cache.findall(C + "pt")
    out = [""] * max(count, max((int(p.get("idx", 0)) + 1 for p in points), default=0))
    for point in points:
        out[int(point.get("idx", 0))] = point.findtext(C + "v") or ""
    return out


class Room:
    """What stands around a plot: its title, its legend."""
    left = top = right = bottom = 0.0


class _Axis:
    def __init__(self, element, absent=True):
        self.el = element
        self.kind = element.tag[len(C):]
        self.id = _val(element.find(C + "axId"))
        self.pos = _val(element.find(C + "axPos"), "b")
        self.deleted = _flag(element, "delete", absent)
        scaling = element.find(C + "scaling")
        self.reversed = _val(scaling.find(C + "orientation") if scaling is not None else None) == "maxMin"
        self.fixed_min = _number(_val(scaling.find(C + "min"))) if scaling is not None else None
        self.fixed_max = _number(_val(scaling.find(C + "max"))) if scaling is not None else None
        self.log_base = _number(_val(scaling.find(C + "logBase"))) if scaling is not None else None
        self.unit = _number(_val(element.find(C + "majorUnit")))
        units = element.find(C + "dispUnits")
        self.divide = 1.0
        if units is not None:
            self.divide = _number(_val(units.find(C + "custUnit"))) or DISPLAY_UNITS.get(_val(units.find(C + "builtInUnit")), 1.0)
        # Which way the labels turn; None leaves it to fit. The file's "automatic" is -60000000.
        body = element.find(f"{C}txPr/{A}bodyPr")
        turn = _number(body.get("rot")) if body is not None else None
        self.turn = None if turn is None or turn == -60000000 else turn / 60000.0
        if body is not None and body.get("vert") in ("vert", "vert270"):
            self.turn = 90.0 if body.get("vert") == "vert" else -90.0
        self.crosses = _val(element.find(C + "crosses"), "autoZero")
        self.crosses_at = _number(_val(element.find(C + "crossesAt")))
        self.labels = _val(element.find(C + "tickLblPos"), "nextTo")
        self.major_mark = _val(element.find(C + "majorTickMark"), "cross")
        self.grid = element.find(C + "majorGridlines")
        fmt = element.find(C + "numFmt")
        self.code = fmt.get("formatCode") if fmt is not None else None
        self.linked = fmt is None or fmt.get("sourceLinked") == "1"
        self.between = _val(element.find(C + "crossBetween"), "between")
        self.skip = _number(_val(element.find(C + "tickLblSkip")))
        self.scale = None           # (min, max, step)


class TextKit:
    """A chart's text: styles from the file, measured and written as SVG."""

    palette: Palette

    def _families(self) -> list:
        fonts = self.palette.fonts
        return [name for name in (fonts.get("minorLatin"), fonts.get("minorBidi")) if name] or ["Arial"]

    def _style(self, tx_pr, inherit: Style) -> Style:
        if tx_pr is None:
            return inherit
        props = next(tx_pr.iter(A + "defRPr"), None)
        return self._apply(props, inherit)

    def _apply(self, props, inherit: Style) -> Style:
        if props is None:
            return inherit
        size = _number(props.get("sz"))
        size = size / 100.0 if size else inherit.size
        bold = props.get("b") == "1" if props.get("b") is not None else inherit.bold
        italic = props.get("i") == "1" if props.get("i") is not None else inherit.italic
        fill = props.find(A + "solidFill")
        found = self.palette.first_color(fill) if fill is not None else None
        color = found[0] if found else inherit.color
        family = list(inherit.family)
        names = []
        for slot in ("latin", "cs"):
            face = props.find(A + slot)
            if face is not None and face.get("typeface"):
                name = self.palette.font(face.get("typeface"))
                if name:
                    names.append(name)
        if names:
            family = names + [n for n in family if n not in names]
        return Style(size, bold, italic, color, family)

    def _line(self, style: Style) -> float:
        """A line of this text's height, as Office measures it."""
        return font_info(style.family[0]).line * style.size

    def _width(self, text: str, style: Style) -> float:
        family = style.family[0]
        if ARABIC.search(text) and len(style.family) > 1:
            family = style.family[1]
        return text_width(text, family, style.size, style.bold)

    def _text(self, x, y, text, style: Style, anchor="middle", rotate=0.0) -> str:
        """A line of text, ``y`` at its middle."""
        rtl = bool(ARABIC.search(text))
        if rtl and anchor != "middle":          # start and end follow the text's direction
            anchor = "end" if anchor == "start" else "start"
        fonts = ", ".join("'" + name.replace("'", "") + "'" for name in style.family + ["Arial"])
        extra = ""
        if style.bold:
            extra += ' font-weight="bold"'
        if style.italic:
            extra += ' font-style="italic"'
        if rotate:
            extra += f' transform="rotate({rotate:.1f} {x:.2f} {y:.2f})"'
        return (f'<text x="{x:.2f}" y="{y + style.size * MID:.2f}" font-size="{style.size:.2f}" font-family="{fonts}" '
                f'fill="#{style.color}" text-anchor="{anchor}" direction="{"rtl" if rtl else "ltr"}"{extra}>'
                f"{html.escape(text, quote=False)}</text>")

    def _wrap(self, text: str, style: Style, limit: float) -> list:
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if line and self._width(trial, style) > limit:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + ([line] if line else [""] if not lines else [])


class _Chart(TextKit):
    def __init__(self, root, palette: Palette, width: float, height: float, picture=None, absent: bool = True):
        self.root = root
        self.absent = absent        # what Office takes a yes-or-no setting the file leaves out to mean
        self.palette = palette
        self.canvas = Canvas(palette, picture)
        self.w, self.h = max(width, 10.0), max(height, 10.0)
        self.chart = root.find(C + "chart")
        self.plot = self.chart.find(C + "plotArea") if self.chart is not None else None
        default_color = palette.scheme_color("tx1")
        # Newer files keep the style number in an alternate-content wrapper.
        self.style_id = int(_number(_val(next(root.iter(C + "style"), None)), 2))
        self.base = self._style(root.find(C + "txPr"), Style(10.0, False, False, default_color, self._families()))
        self.groups, self.axes = [], {}
        self.bars, self.front, self.labels = [], [], []
        if self.plot is None:
            return
        running = 0
        for child in self.plot:
            kind = child.tag[len(C):]
            if kind.endswith("Chart"):
                series = [_Series(s, running + i) for i, s in enumerate(child.findall(C + "ser"))]
                running += len(series)
                series.sort(key=lambda s: s.order)
                if series:
                    self.groups.append((kind, child, series))
            elif kind in ("catAx", "valAx", "dateAx", "serAx"):
                axis = _Axis(child, absent)
                self.axes[axis.id] = axis

    # -- the drawing ----------------------------------------------------------------

    def svg(self, unit) -> str:
        room = Room()
        body = [self._background()]
        title = self._title(room)
        legend = self._legend(room)
        kinds = {kind for kind, _, _ in self.groups}
        if kinds and kinds <= set(PIE_KINDS) | {"doughnutChart"}:
            self._round_charts(room)
        elif "radarChart" in kinds:
            self._radar(room)
        elif self.groups:
            self._axis_charts(room)
        body += self.bars + self.front + self.labels + legend + title
        return (f'<svg class="chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.3f} {self.h:.3f}" '
                f'style="width:{unit(self.w)};height:{unit(self.h)};overflow:visible;display:block" '
                f'preserveAspectRatio="none">{self.canvas.definitions()}{"".join(body)}</svg>')

    def _background(self) -> str:
        props = self.root.find(C + "spPr")
        paint, stroke = 'fill="#FFFFFF"', 'stroke="#898989" stroke-width="0.5"'     # Office's look when none is stored
        if props is not None:
            fill = self.canvas.fill_of(props)
            paint = self.canvas.paint(fill) if fill is not None else 'fill="none"'
            stroke = self.canvas.stroke(props.find(A + "ln"))
        corners = ' rx="10" ry="10"' if _flag(self.root, "roundedCorners", self.absent) else ""
        return f'<rect x="0" y="0" width="{self.w:.3f}" height="{self.h:.3f}"{corners} {paint} {stroke}/>'

    def _manual(self, layout):
        """A layout's fractions of the chart, if it was placed by hand."""
        manual = layout.find(C + "manualLayout") if layout is not None else None
        if manual is None:
            return None
        return {name: _number(_val(manual.find(C + name))) for name in ("x", "y", "w", "h")} | {
            "target": _val(manual.find(C + "layoutTarget"), "outer"),
            "xMode": _val(manual.find(C + "xMode"), "factor"), "yMode": _val(manual.find(C + "yMode"), "factor")}

    def _title_text(self):
        """The chart title's lines and style, or None."""
        title = self.chart.find(C + "title")
        deleted = _flag(self.chart, "autoTitleDeleted", self.absent)
        all_series = [s for _, _, series in self.groups for s in series]
        if title is None:
            if deleted or len(all_series) != 1 or not all_series[0].name:
                return None
            return [all_series[0].name], self._title_style(None), None
        style = self._title_style(title)
        rich = next(title.iter(C + "rich"), None)
        lines = []
        if rich is not None:
            for paragraph in rich.findall(A + "p"):
                pieces = [(run.findtext(A + "t") or "") for run in paragraph.findall(A + "r")]
                run_props = next(paragraph.iter(A + "rPr"), None)
                style = self._apply(run_props, self._apply(paragraph.find(f"{A}pPr/{A}defRPr"), style))
                lines.append("".join(pieces))
        else:
            cached = next(title.iter(C + "v"), None)
            if cached is not None:
                lines = [cached.text or ""]
            elif len(all_series) == 1:
                lines = [all_series[0].name]
            else:
                lines = ["Chart Title"]
        return lines, style, title

    def _title_style(self, title) -> Style:
        base = self.base
        inherit = Style(base.size * 1.2 if self.root.find(C + "txPr") is not None else 18.0, True, base.italic, base.color, base.family)
        return self._style(title.find(C + "txPr"), inherit) if title is not None else inherit

    def _title(self, room) -> list:
        found = self._title_text()
        if not found:
            return []
        lines, style, element = found
        wrapped = [piece for line in lines for piece in self._wrap(line, style, self.w * 0.75)]
        step = self._line(style)
        manual = self._manual(element.find(C + "layout")) if element is not None else None
        out = []
        baseline = 7.45 + font_info(style.family[0]).ascent * style.size
        x = self.w / 2
        if manual and manual.get("x") is not None and manual["xMode"] == "edge":
            x = manual["x"] * self.w + max(self._width(line, style) for line in wrapped) / 2
        if manual and manual.get("y") is not None and manual["yMode"] == "edge":
            baseline = manual["y"] * self.h + font_info(style.family[0]).ascent * style.size
        for index, line in enumerate(wrapped):
            out.append(self._text(x, baseline + index * step - MID * style.size, line, style))
        if element is None or not _flag(element, "overlay", self.absent):
            room.top += 9.0 + step * len(wrapped)
        return out

    def _legend_entries(self) -> list:
        legend = self.chart.find(C + "legend")
        hidden = set()
        for entry in legend.findall(C + "legendEntry"):
            if _flag(entry, "delete"):
                hidden.add(int(_number(_val(entry.find(C + "idx")), -1)))
        out = []
        at = 0
        for kind, group, series in self.groups:
            vary = _flag(group, "varyColors", self.absent)
            if kind in PIE_KINDS or kind == "doughnutChart" or (vary and len(series) == 1 and kind in BAR_KINDS):
                first = series[0]
                names = first.categories or [str(i + 1) for i in range(len(first.values))]
                for index, name in enumerate(names):
                    if index not in hidden:
                        out.append((name, ("point", first, index, kind, group)))
                at += len(names)
            else:
                for one in series:
                    if at not in hidden:
                        out.append((one.name or f"Series{one.index + 1}", ("series", one, one.index, kind, group)))
                    at += 1
        if len(self.groups) == 1:
            # Office lists series in the order they stand: bars across go bottom up
            # everywhere, and stacks read top down when the legend stands beside them.
            kind, group, _ = self.groups[0]
            stacked = _val(group.find(C + "grouping")) in ("stacked", "percentStacked")
            across = _val(group.find(C + "barDir")) == "bar"
            beside = _val(legend.find(C + "legendPos"), "r") in ("r", "l", "tr")
            if (kind in BAR_KINDS and across and not stacked) or (beside and stacked and (kind in AREA_KINDS or (kind in BAR_KINDS and not across))):
                out.reverse()
        return out

    def _key_width(self, entry, size) -> float:
        """How wide a legend entry's key is: lines take more room than swatches."""
        _, (kind, series, _, chart_kind, group) = entry
        if kind == "series" and self._is_lined(chart_kind, group) and self._line_stroke(series, chart_kind) != 'stroke="none"':
            return 2.133 * size
        return 0.549 * size

    @staticmethod
    def _is_lined(kind, group) -> bool:
        if kind == "radarChart":
            return _val(group.find(C + "radarStyle")) != "filled"
        return kind in LINE_KINDS or kind == "scatterChart"

    def _legend(self, room) -> list:
        legend = self.chart.find(C + "legend") if self.chart is not None else None
        if legend is None or not self.groups:
            return []
        entries = self._legend_entries()
        if not entries:
            return []
        style = self._style(legend.find(C + "txPr"), self.base)
        size, line = style.size, self._line(style)
        metrics = font_info(style.family[0])
        swatch, gap = 0.549 * size, 0.245 * size
        position = _val(legend.find(C + "legendPos"), "r")
        manual = self._manual(legend.find(C + "layout"))
        overlay = _flag(legend, "overlay", self.absent)
        keys = [self._key_width(entry, size) for entry in entries]
        if max(keys) > swatch:
            keys = [max(keys)] * len(keys)
        texts = [self._width(entry[0], style) for entry in entries]
        out = []
        if position in ("t", "b"):
            lead = [7.08 if key > swatch else 6.09 for key in keys]
            widths = [text + key + gap + (10.65 if key > swatch else 8.63) for text, key in zip(texts, keys)]
            rows, row, used = [], [], 0.0
            for index, width in enumerate(widths):
                if row and used + width > self.w - 12:
                    rows.append((row, used))
                    row, used = [], 0.0
                used += width
                row.append(index)
            rows.append((row, used))
            if position == "b":
                first = self.h - 9.42 - metrics.descent * size - line * (len(rows) - 1)
            else:
                first = room.top + 17.03
            if manual and manual.get("y") is not None and manual["yMode"] == "edge":
                first = manual["y"] * self.h + metrics.ascent * size
            for number, (row, used) in enumerate(rows):
                x = (self.w - used) / 2
                if manual and manual.get("x") is not None and manual["xMode"] == "edge":
                    x = manual["x"] * self.w
                y = first + number * line - MID * size
                for index in row:
                    out += self._legend_item(x + lead[index], y, keys[index], gap, entries[index], style)
                    x += widths[index]
            if not overlay:
                extra = 11.89 + line * len(rows)
                if position == "b":
                    room.bottom += extra
                else:
                    room.top += extra
            return out
        widest, key = max(texts), max(keys)
        pitch = line + 5.88
        extra = widest + 22.0 + (key - swatch)
        text_x = self.w - 10.0 - widest if position in ("r", "tr") else 10.7 + swatch + gap + (key - swatch)
        key_x = text_x - gap - key
        if manual and manual.get("x") is not None and manual["xMode"] == "edge":
            key_x = manual["x"] * self.w + 6.09
        if position == "tr":
            first = room.top + 20.5
        else:
            first = (self.h + room.top) / 2 - pitch * (len(entries) - 1) / 2
        if manual and manual.get("y") is not None and manual["yMode"] == "edge":
            first = manual["y"] * self.h + line / 2
        for index, entry in enumerate(entries):
            shift = key - keys[index]
            out += self._legend_item(key_x + shift, first + pitch * index, keys[index], gap, entry, style)
        if not overlay:
            if position in ("r", "tr"):
                room.right += extra
                if position == "tr":
                    room.top += 6.0
            else:
                room.left += extra
        return out

    def _legend_item(self, x, y, key, gap, entry, style) -> list:
        name, (kind, series, index, chart_kind, group) = entry
        out = []
        side = 0.549 * style.size
        if kind == "point":
            paint, stroke = self._point_paint(series, index, chart_kind, group)
            out.append(f'<rect x="{x:.2f}" y="{y - side / 2:.2f}" width="{side:.2f}" height="{side:.2f}" {paint} {stroke}/>')
        elif chart_kind == "bubbleChart":
            paint, stroke = self._series_paint(series)
            out.append(f'<circle cx="{x + side / 2:.2f}" cy="{y:.2f}" r="{side / 2:.2f}" {paint} {stroke}/>')
        elif self._is_lined(chart_kind, group):
            stroke = self._line_stroke(series, chart_kind)
            if stroke != 'stroke="none"':
                out.append(f'<path d="M{x:.2f} {y:.2f}H{x + key:.2f}" fill="none" {stroke}/>')
            marker = self._marker_of(series, chart_kind, group)
            if marker:
                out.append(self._draw_marker(marker, x + key / 2, y, series))
        else:
            paint, stroke = self._series_paint(series)
            out.append(f'<rect x="{x:.2f}" y="{y - side / 2:.2f}" width="{key:.2f}" height="{side:.2f}" {paint} {stroke}/>')
        out.append(self._text(x + key + gap, y, name, style, anchor="start"))
        return out

    def _auto_color(self, index: int) -> str:
        # The 48 chart styles repeat every eight: greys, all the accents, then each accent alone.
        family = (self.style_id - 1) % 8
        if family == 0:
            return _lighter("000000", min(0.85, 0.25 + 0.15 * (index % 5)))
        if family >= 2:
            base = self.palette.scheme_color(f"accent{family - 1}")
            return _lighter(base, (index % 6) * 0.14 - 0.3)
        accent = self.palette.scheme_color(f"accent{index % 6 + 1}")
        rounds = index // 6
        if rounds:
            return _lighter(accent, -0.3 if rounds % 2 else 0.3)
        return accent

    def _series_paint(self, series) -> tuple:
        props = series.el.find(C + "spPr")
        paint = f'fill="#{self._auto_color(series.index)}"'
        stroke = 'stroke="none"'
        if props is not None:
            fill = self.canvas.fill_of(props)
            if fill is not None:
                paint = self.canvas.paint(fill)
            line = props.find(A + "ln")
            if line is not None:
                stroke = self.canvas.stroke(line)
        return paint, stroke

    def _point_paint(self, series, index, kind, group) -> tuple:
        point = series.points.get(index)
        props = point.find(C + "spPr") if point is not None else None
        vary = _flag(group, "varyColors", self.absent)
        paint, stroke = self._series_paint(series)
        if vary:
            paint = f'fill="#{self._auto_color(index)}"'
            if kind in PIE_KINDS or kind == "doughnutChart":
                if series.el.find(C + "spPr") is None or series.el.find(C + "spPr").find(A + "ln") is None:
                    stroke = 'stroke="#FFFFFF" stroke-width="0.75"'
        if props is not None:
            fill = self.canvas.fill_of(props)
            if fill is not None:
                paint = self.canvas.paint(fill)
            line = props.find(A + "ln")
            if line is not None:
                stroke = self.canvas.stroke(line)
        return paint, stroke

    def _line_stroke(self, series, kind) -> str:
        props = series.el.find(C + "spPr")
        line = props.find(A + "ln") if props is not None else None
        color = self._auto_color(series.index)
        if kind in XY_KINDS and line is None:
            group_style = None
            for one_kind, group, members in self.groups:
                if series in members:
                    group_style = _val(group.find(C + "scatterStyle"))
            if group_style in (None, "lineMarker", "marker"):
                return 'stroke="none"' if group_style == "marker" else f'stroke="#{color}" stroke-width="1.5"'
        if line is None:
            return f'stroke="#{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'
        if line.find(A + "noFill") is not None:
            return 'stroke="none"'
        return self.canvas.stroke(line, default_width=2.25, default_color=color)

    def _marker_of(self, series, kind, group):
        """(symbol, size, paint, stroke) of a series' points, or None."""
        marker = series.el.find(C + "marker")
        symbol = _val(marker.find(C + "symbol")) if marker is not None else None
        stated = _number(_val(marker.find(C + "size") if marker is not None else None))
        size = stated * 0.948 if stated else 6.0
        if symbol == "none":
            return None
        if symbol is None:
            if kind in LINE_KINDS and not _flag(group, "marker", self.absent):
                return None
            if kind == "radarChart" and _val(group.find(C + "radarStyle")) != "marker":
                return None
            symbol = MARKERS[series.index % len(MARKERS)]
        color = self._auto_color(series.index)
        paint, stroke = f'fill="#{color}"', f'stroke="#{color}" stroke-width="{0.75 if stated else 0.5}"'
        props = marker.find(C + "spPr") if marker is not None else None
        if props is not None:
            fill = self.canvas.fill_of(props)
            if fill is not None:
                paint = self.canvas.paint(fill)
            line = props.find(A + "ln")
            if line is not None:
                stroke = self.canvas.stroke(line)
        return symbol, size, paint, stroke

    def _draw_marker(self, marker, x, y, series) -> str:
        symbol, size, paint, stroke = marker
        r = size / 2
        if symbol == "circle":
            return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" {paint} {stroke}/>'
        if symbol == "dot":
            return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * .5:.2f}" {paint} {stroke}/>'
        if symbol == "square":
            return f'<rect x="{x - r:.2f}" y="{y - r:.2f}" width="{size:.2f}" height="{size:.2f}" {paint} {stroke}/>'
        if symbol == "diamond":
            return f'<path d="M{x:.2f} {y - r:.2f}L{x + r:.2f} {y:.2f}L{x:.2f} {y + r:.2f}L{x - r:.2f} {y:.2f}Z" {paint} {stroke}/>'
        if symbol == "triangle":
            return f'<path d="M{x:.2f} {y - r:.2f}L{x + r:.2f} {y + r:.2f}L{x - r:.2f} {y + r:.2f}Z" {paint} {stroke}/>'
        if symbol == "x":
            return f'<path d="M{x - r:.2f} {y - r:.2f}L{x + r:.2f} {y + r:.2f}M{x + r:.2f} {y - r:.2f}L{x - r:.2f} {y + r:.2f}" fill="none" {stroke}/>'
        if symbol == "plus":
            return f'<path d="M{x - r:.2f} {y:.2f}H{x + r:.2f}M{x:.2f} {y - r:.2f}V{y + r:.2f}" fill="none" {stroke}/>'
        if symbol == "star":
            return (f'<path d="M{x - r:.2f} {y - r:.2f}L{x + r:.2f} {y + r:.2f}M{x + r:.2f} {y - r:.2f}L{x - r:.2f} {y + r:.2f}'
                    f'M{x:.2f} {y - r:.2f}V{y + r:.2f}" fill="none" {stroke}/>')
        if symbol == "dash":
            return f'<path d="M{x - r:.2f} {y:.2f}H{x + r:.2f}" fill="none" {stroke}/>'
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" {paint} {stroke}/>'

    # -- data labels -------------------------------------------------------------------

    def _label_settings(self, element, inherited=None):
        if element is None:
            return inherited
        if _flag(element, "delete"):
            return None
        out = dict(inherited) if inherited else {"val": self.absent, "cat": self.absent, "ser": self.absent, "pct": self.absent,
                                                 "pos": None, "code": None, "sep": None, "style": self.base}
        for key, name in (("val", "showVal"), ("cat", "showCatName"), ("ser", "showSerName"), ("pct", "showPercent")):
            if element.find(C + name) is not None:
                out[key] = _flag(element, name)
        out["pos"] = _val(element.find(C + "dLblPos"), out["pos"])
        fmt = element.find(C + "numFmt")
        if fmt is not None:
            out["code"] = fmt.get("formatCode")
        if element.find(C + "separator") is not None:
            out["sep"] = element.findtext(C + "separator")
        out["style"] = self._style(element.find(C + "txPr"), out["style"])
        return out

    def _label_text(self, settings, value, category, series_name, percent=None, code=None) -> str:
        pieces = []
        if settings["ser"] and series_name:
            pieces.append(series_name)
        if settings["cat"] and category:
            pieces.append(category)
        if settings["val"] and value is not None:
            pieces.append(format_number(value, settings["code"] or code))
        if settings["pct"] and percent is not None:
            pieces.append(format_number(percent, "0%" if not settings["val"] and settings["code"] is None else "0%"))
        return (settings["sep"] or ", ").join(pieces)

    def _point_labels(self, series, group, index):
        settings = self._label_settings(group.find(C + "dLbls"))
        settings = self._label_settings(series.el.find(C + "dLbls"), settings)
        labels = series.el.find(C + "dLbls")
        if labels is not None and settings is not None:
            for one in labels.findall(C + "dLbl"):
                if int(_number(_val(one.find(C + "idx")), -1)) == index:
                    return self._label_settings(one, settings)
        return settings

    # -- pies and doughnuts --------------------------------------------------------------

    def _round_charts(self, room) -> None:
        left, top = room.left + OUTER, room.top + OUTER
        right, bottom = self.w - room.right - OUTER, self.h - room.bottom - OUTER
        cx, cy = (left + right) / 2, (top + bottom) / 2
        radius = max(10.0, min(right - left, bottom - top) / 2)
        manual = self._manual(self.plot.find(C + "layout"))
        if manual and manual.get("w"):
            x, y = manual.get("x") or 0, manual.get("y") or 0
            box = Frame(x * self.w, y * self.h, manual["w"] * self.w, (manual.get("h") or manual["w"]) * self.h)
            cx, cy = box.x + box.w / 2, box.y + box.h / 2
            radius = min(box.w, box.h) / 2
        for kind, group, series in self.groups:
            start = _number(_val(group.find(C + "firstSliceAng")), 0.0)
            first = series[0]
            spots = [self._point_labels(first, group, i) for i in range(len(first.values))]
            # Labels that may stand outside take room from the circle; a ring is drawn the same size.
            outside = any(s is not None and self._has_label(s) and s.get("pos") in ("outEnd", "bestFit", None) for s in spots)
            outer = radius * (0.85 if outside else 1.0)
            if kind == "doughnutChart":
                hole = _number(_val(group.find(C + "holeSize")), 50.0) / 100.0
                band = outer * (1 - hole) / max(len(series), 1)
                for number, one in enumerate(series):
                    ring = outer * hole + band * (number + 1)
                    self._slices(one, group, kind, cx, cy, ring, ring - band, start)
            else:
                self._slices(first, group, kind, cx, cy, outer, 0.0, start)

    @staticmethod
    def _has_label(settings) -> bool:
        return settings["val"] or settings["cat"] or settings["ser"] or settings["pct"]

    def _slices(self, series, group, kind, cx, cy, outer, inner, start) -> None:
        values = [max(v or 0.0, 0.0) for v in series.values]
        total = sum(values) or 1.0
        shares = _rounded_shares(values)
        angle = start - 90.0
        for index, value in enumerate(values):
            sweep = value / total * 360.0
            if value <= 0:
                continue
            paint, stroke = self._point_paint(series, index, kind, group)
            point = series.points.get(index)
            explode = _number(_val(point.find(C + "explosion") if point is not None else None),
                              _number(_val(series.el.find(C + "explosion")), 0.0)) / 100.0
            middle = math.radians(angle + sweep / 2)
            ox, oy = cx + outer * explode * math.cos(middle), cy + outer * explode * math.sin(middle)
            self.bars.append(f'<path d="{_slice(ox, oy, outer, inner, angle, sweep)}" {paint} {stroke}/>')
            settings = self._point_labels(series, group, index)
            if settings:
                category = series.categories[index] if series.categories and index < len(series.categories) else ""
                text = self._label_text(settings, series.values[index], category, series.name, shares[index], series.format)
                if text:
                    self._slice_label(text, settings, ox, oy, outer, inner, middle, sweep)
            angle += sweep

    def _slice_label(self, text, settings, ox, oy, outer, inner, middle, sweep) -> None:
        """A label inside or outside its slice, by the setting; its edge keeps clear of the circle."""
        style = settings["style"]
        line = self._line(style)
        pieces = self._wrap(text, style, self.w * 0.2 - 5.2)
        wide = max(self._width(piece, style) for piece in pieces)
        tall = line * len(pieces)
        along, across = math.cos(middle), math.sin(middle)
        reach = abs(along) * wide / 2 + abs(across) * tall / 2
        position = settings["pos"] or ("ctr" if inner else "bestFit")
        if inner:
            distance = (outer + inner) / 2
        elif position == "ctr":
            distance = outer * 0.5
        elif position == "inEnd":
            distance = outer - reach - 3.4
        elif position == "outEnd" or (position == "bestFit" and (reach * 2.2 > outer or sweep < 30)):
            distance = outer + 4.2 + reach
        else:
            distance = outer * 0.72
        x, y = ox + distance * along, oy + distance * across
        for number, piece in enumerate(pieces):
            self.labels.append(self._text(x, y + (number - (len(pieces) - 1) / 2) * line, piece, style))

    def _axis_pair(self, group):
        ids = [_val(a) for a in group.findall(C + "axId")]
        found = [self.axes[i] for i in ids if i in self.axes]
        if not found:
            return None, None
        category = next((a for a in found if a.kind in ("catAx", "dateAx")), None)
        values = next((a for a in found if a.kind == "valAx" and a is not category), None)
        if category is None and len(found) >= 2:   # scatter: x axis along the bottom or top
            first, second = found[0], found[1]
            category, values = (first, second) if first.pos in ("b", "t") else (second, first)
        return category, values

    def _range(self, value_axis) -> tuple:
        """The lowest and highest values a value axis must show."""
        low, high = None, None

        def see(value):
            nonlocal low, high
            if value is None:
                return
            low = value if low is None else min(low, value)
            high = value if high is None else max(high, value)

        for kind, group, series in self.groups:
            if kind in PIE_KINDS or kind == "doughnutChart":
                continue
            _, axis = self._axis_pair(group)
            if axis is not value_axis:
                continue
            grouping = _val(group.find(C + "grouping"), "clustered" if kind in BAR_KINDS else "standard")
            if grouping in ("stacked", "percentStacked"):
                length = max(len(s.values) for s in series)
                for index in range(length):
                    up = down = 0.0
                    for one in series:
                        value = one.values[index] if index < len(one.values) else None
                        if value is None:
                            continue
                        if value >= 0:
                            up += value
                        else:
                            down += value
                    if grouping == "percentStacked":
                        total = up - down or 1.0
                        up, down = up / total, down / total
                    see(up)
                    see(down)
            else:
                for one in series:
                    for value in one.values:
                        see(value)
        return low, high

    def _x_range(self, axis) -> tuple:
        low, high = None, None
        for kind, group, series in self.groups:
            first, _ = self._axis_pair(group)
            if first is not axis:
                continue
            for one in series:
                xs = one.xs or list(range(1, len(one.values) + 1))
                for value in xs:
                    if value is None:
                        continue
                    low = value if low is None else min(low, value)
                    high = value if high is None else max(high, value)
        return low, high

    def _axis_style(self, axis) -> Style:
        return self._style(axis.el.find(C + "txPr"), self.base)

    def _axis_title(self, axis):
        """(text, style, degrees it stands at or None) of an axis's title."""
        title = axis.el.find(C + "title")
        fallback = "Axis Title"
        if title is None:                # "Thousands" and the like stand where a title would
            units = axis.el.find(C + "dispUnits")
            title = units.find(C + "dispUnitsLbl") if units is not None else None
            if title is None:
                return None
            built_in = _val(units.find(C + "builtInUnit"), "")
            fallback = re.sub("([A-Z])", lambda m: " " + m.group(1).lower(), built_in).capitalize()
        rich = next(title.iter(C + "rich"), None)
        text = ""
        style = Style(self.base.size, True, False, self.base.color, self.base.family)
        style = self._style(title.find(C + "txPr"), style)
        body = next(title.iter(A + "bodyPr"), None)
        turn = _number(body.get("rot")) if body is not None else None
        turn = None if turn is None or turn == -60000000 else turn / 60000.0
        if rich is not None:
            text = " ".join("".join((r.findtext(A + "t") or "") for r in p.findall(A + "r")) for p in rich.findall(A + "p"))
            props = next(rich.iter(A + "rPr"), None)
            style = self._apply(props, self._apply(next(rich.iter(A + "defRPr"), None), style))
        else:
            cached = next(title.iter(C + "v"), None)
            text = (cached.text or "") if cached is not None else fallback
        return (text, style, turn) if text else None

    def _value_code(self, axis) -> str:
        if not axis.linked and axis.code:
            return axis.code
        for kind, group, series in self.groups:
            _, values = self._axis_pair(group)
            grouping = _val(group.find(C + "grouping"))
            if values is axis:
                if grouping == "percentStacked":
                    return "0%"
                if series[0].format:
                    return series[0].format
        return axis.code or "General"

    def _categories(self):
        for _, group, series in self.groups:
            axis = self._axis_pair(group)[0]
            for one in series:
                if one.category_numbers and axis is not None and axis.code and not axis.linked:
                    return [format_number(value, axis.code) for value in one.category_numbers]
                if one.categories:
                    return one.categories
        length = max((len(s.values) for _, _, series in self.groups for s in series), default=0)
        return [str(i + 1) for i in range(length)]

    def _axis_charts(self, room) -> None:
        pairs = [self._axis_pair(group) for _, group, _ in self.groups]
        pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
        if not pairs:
            return
        category, values = pairs[0]
        kinds = [kind for kind, _, _ in self.groups]
        horizontal = any(kind in BAR_KINDS and _val(group.find(C + "barDir"), "col") == "bar" for kind, group, _ in self.groups)
        scatter = all(kind in XY_KINDS for kind in kinds)
        secondary = next((p[1] for p in pairs if p[1] is not values), None)
        names = self._categories()
        layout = _Layout(category, values, secondary, names, horizontal, scatter)
        self._room_left, self._room_right = room.left, room.right
        val_style = self._axis_style(values)
        manual = self._manual(self.plot.find(C + "layout"))
        wide = self.w - room.left - room.right
        tall = self.h - room.top - room.bottom
        # Which step fits depends on the plot, and how wide the numbers are on the step.
        edges = (OUTER, OUTER, OUTER, OUTER)
        for _ in range(3):
            plot_w = max(wide - edges[0] - edges[2], 20.0)
            plot_h = max(tall - edges[1] - edges[3], 20.0)
            if horizontal:
                self._scale_axis(values, plot_w, 3.32 * val_style.size, True)
                if secondary is not None:
                    self._scale_axis(secondary, plot_w, 3.32 * self._axis_style(secondary).size, True)
            else:
                plain = self._edges(layout, plot_w, one_line=True)
                length = max(tall - plain[1] - plain[3], 20.0)
                self._scale_axis(values, length, 1.07 * self._line(val_style))
                if secondary is not None:
                    self._scale_axis(secondary, length, 1.07 * self._line(self._axis_style(secondary)))
            if scatter:
                low, high = self._x_range(category)
                if "bubbleChart" in kinds and high is not None:
                    high *= 1.15          # the bubbles reach past their centres
                category.scale = auto_scale(low, high, plot_w, 4.2 * self._axis_style(category).size, category.fixed_min, category.fixed_max, category.unit, True)
            edges = self._edges(layout, plot_w)
        frame = Frame(room.left + edges[0], room.top + edges[1], max(wide - edges[0] - edges[2], 10.0), max(tall - edges[1] - edges[3], 10.0))
        if manual is not None and manual.get("w") and manual.get("h"):
            x = (manual.get("x") or 0) * self.w
            y = (manual.get("y") or 0) * self.h
            frame = Frame(x, y, manual["w"] * self.w, manual["h"] * self.h)
            if manual["target"] != "inner":
                frame = Frame(x + edges[0], y + edges[1], manual["w"] * self.w - edges[0] - edges[2], manual["h"] * self.h - edges[1] - edges[3])
        self._plot_background(frame)
        self._gridlines(frame, category, values, horizontal, scatter, names)
        for kind, group, series in self.groups:
            cat_axis, val_axis = self._axis_pair(group)
            if cat_axis is None or val_axis is None:
                continue
            if kind in BAR_KINDS:
                self._bars(frame, group, kind, series, cat_axis, val_axis, horizontal, len(names))
            elif kind in AREA_KINDS:
                self._areas(frame, group, kind, series, cat_axis, val_axis, len(names))
            elif kind in LINE_KINDS:
                self._stock_marks(frame, group, series, cat_axis, val_axis, len(names))
                self._lines(frame, group, kind, series, cat_axis, val_axis, horizontal, len(names))
            elif kind in SURFACE_KINDS:          # a surface reads as its lines of values
                self._lines(frame, group, "lineChart", series, cat_axis, val_axis, horizontal, len(names))
            elif kind in XY_KINDS:
                self._scatter(frame, group, kind, series, cat_axis, val_axis)
        self._draw_axes(frame, layout)

    def _labels_side(self, layout) -> str:
        """Where a category axis's names stand: 'near' its low end, 'far' past its high end, 'inside' the plot."""
        category, values = layout.category, layout.values
        start, stop, _ = values.scale
        if category.labels == "low":
            return "far" if values.reversed else "near"
        if category.labels == "high":
            return "near" if values.reversed else "far"
        crossing = self._crossing(category, values)
        if crossing <= start + 1e-9:
            return "far" if values.reversed else "near"
        if crossing >= stop - 1e-9:
            return "near" if values.reversed else "far"
        return "inside"

    @staticmethod
    def _crossing(category, values) -> float:
        start, stop, _ = values.scale
        if category.crosses == "max":
            return stop
        if category.crosses == "min":
            return start
        if category.crosses_at is not None:
            return category.crosses_at
        return start if values.log_base else min(max(0.0, start), stop)

    def _edges(self, layout, plot_w, one_line=False) -> tuple:
        """What stands beside the plot, as Office measures it: (left, top, right, bottom)."""
        category, values, secondary, names = layout.category, layout.values, layout.secondary, layout.names
        if values.scale is None:
            return OUTER, OUTER, OUTER, OUTER
        cat_style, val_style = self._axis_style(category), self._axis_style(values)
        code = self._value_code(values)
        extent = self._label_side_extent(values, code, val_style)
        val_title, cat_title = self._axis_title(values), self._axis_title(category)
        left = top = right = bottom = OUTER
        if layout.horizontal:
            # The numbers stand under the plot, half their width past each end.
            start, stop, step = values.scale
            ticks = _ticks(start, stop, step)
            if not values.deleted and values.labels != "none":
                bottom = 6.43 + 0.642 * val_style.size + self._line(val_style)
                first, last = (ticks[-1], ticks[0]) if values.reversed else (ticks[0], ticks[-1])
                left = max(left, OUTER + self._width(format_number(first / values.divide, code), val_style) / 2)
                right = max(right, OUTER + self._width(format_number(last / values.divide, code), val_style) / 2)
            if val_title:
                bottom += self._line(val_title[1]) + 9.0
            if not category.deleted and category.labels != "none":
                side = self._labels_side(layout)
                span = self._bar_names_extent(names, cat_style)
                if side == "near":
                    left = max(left, span)
                elif side == "far":
                    right = max(right, span)
            if cat_title:
                extra = self._width(cat_title[0], cat_title[1]) + 12.1 if cat_title[2] == 0 else self._line(cat_title[1]) + 9.03
                if values.reversed:
                    right += extra
                else:
                    left += extra
            return left, top, right, bottom
        far = self._value_on_far_side(values, category)
        if extent:
            top = max(OUTER, 5.1 + self._line(val_style) / 2)
            beside = 6.5 + extent + 0.923 * val_style.size
            if far:
                right = beside
            else:
                left = beside
        if val_title:
            if far:
                right += self._line(val_title[1]) + 9.03
            else:
                left += self._line(val_title[1]) + 9.03
        if secondary is not None and not secondary.deleted:
            style = self._axis_style(secondary)
            second = self._label_side_extent(secondary, self._value_code(secondary), style)
            if second:
                if far:
                    left = 6.5 + second + 0.923 * style.size
                else:
                    right = 6.5 + second + 0.923 * style.size
            title = self._axis_title(secondary)
            if title:
                if far:
                    left += self._line(title[1]) + 9.03
                else:
                    right += self._line(title[1]) + 9.03
        labels = 0.0
        if layout.scatter:
            if not category.deleted and category.labels != "none":
                labels = 6.43 + 0.642 * cat_style.size + self._line(cat_style)
                code_x = category.code if not category.linked and category.code else "General"
                ticks = _ticks(*category.scale) if category.scale else []
                if ticks:
                    right = max(right, OUTER + self._width(format_number(ticks[-1], code_x), cat_style) / 2)
                    left = max(left, OUTER + self._width(format_number(ticks[0], code_x), cat_style) / 2)
            side = "near"
        else:
            side = self._labels_side(layout)
            if not category.deleted and category.labels != "none" and names:
                if values.between == "midCat":         # the first and last names centre on the plot's ends
                    left = max(left, OUTER + self._width(names[0], cat_style) / 2)
                    right = max(right, OUTER + self._width(names[-1], cat_style) / 2)
                if side != "inside":
                    width = max(plot_w, 20.0)
                    if one_line:
                        depth = self._line(cat_style)
                    else:
                        depth = self._label_depth(category, names, cat_style, width, values.between == "midCat")
                    labels = 6.43 + 0.642 * cat_style.size + depth
                    if not one_line:
                        _, angle, _ = self._name_plan(category, names, cat_style, width, values.between == "midCat")
                        if angle and abs(angle) < 80 and angle < 0:
                            band = width / max(len(names), 1)
                            left = max(left, 8.68 + 0.7071 * self._width(names[0], cat_style) - band / 2)
        if cat_title:
            labels = (labels or OUTER) + self._line(cat_title[1]) + 9.0
        if labels:
            if side == "far":
                top = labels
            else:
                bottom = labels
        return left, top, right, bottom

    def _bar_names_extent(self, names, style) -> float:
        """How far the names of bars across reach from the plot's edge to the chart's."""
        limit = self.w * 0.45
        extent = 0.0
        for name in names:
            shown, cut = self._cut_name(name, style, limit)
            width = self._width(shown, style)
            extent = max(extent, width + (8.66 if cut else 14.81))
        return extent

    def _cut_name(self, name, style, limit) -> tuple:
        """A bar's name, cut off with dots at a word if it is too long for its place."""
        if self._width(name, style) <= limit:
            return name, False
        words = name.split()
        while len(words) > 1:
            words.pop()
            shown = " ".join(words) + "…"
            if self._width(shown, style) <= limit:
                return shown, True
        shown = name
        while len(shown) > 1 and self._width(shown + "…", style) > limit:
            shown = shown[:-1]
        return shown + "…", True

    def _scale_axis(self, axis, length, spacing, across=False) -> None:
        low, high = self._range(axis)
        if axis.log_base and axis.log_base > 1:
            base = axis.log_base
            low = low if low and low > 0 else 1.0
            high = high if high and high > low else low * base
            axis.scale = (axis.fixed_min or min(1.0, base ** math.floor(math.log(low, base) + 1e-9)),
                          axis.fixed_max or base ** math.ceil(math.log(high, base) - 1e-9), -base)
            return
        is_percent = any(_val(group.find(C + "grouping")) == "percentStacked" and self._axis_pair(group)[1] is axis
                         for _, group, _ in self.groups)
        fixed_min, fixed_max = axis.fixed_min, axis.fixed_max
        if is_percent:
            fixed_max = 1.0 if fixed_max is None else fixed_max
            if fixed_min is None:
                fixed_min = -1.0 if low and low < 0 else 0.0
        elif any(kind == "bubbleChart" for kind, _, _ in self.groups) and high is not None:
            high = high * 1.15          # the bubbles reach past their centres
        axis.scale = auto_scale(low, high, length, spacing, fixed_min, fixed_max, axis.unit, across)

    def _label_side_extent(self, axis, code, style) -> float:
        if axis.deleted or axis.labels == "none":
            return 0.0
        start, stop, step = axis.scale
        return max((self._width(format_number(tick / axis.divide, code), style) for tick in _ticks(start, stop, step)), default=0.0)

    def _category_layout(self, categories, style, plot_w) -> tuple:
        """(lines, angle, skip) of a category axis's names: flat and wrapped if they fit,
        else turned 45 degrees, else on end, else leaving out enough names to fit."""
        count = max(len(categories), 1)
        band = plot_w / count
        line = self._line(style)
        for skip in range(1, count + 1):
            room = band * skip
            shown = categories[::skip]
            fits = True
            lines = 1
            for text in shown:
                words = text.split()
                if len(words) > 1:
                    if any(self._width(word, style) > room for word in words):
                        fits = False
                        break
                    if self._width(text, style) > room * 0.94:
                        lines = max(lines, len(self._wrap(text, style, room)))
                elif self._width(text, style) > room * 0.94:
                    fits = False
                    break
            if fits and lines * line <= self.h * 0.45:
                return lines, 0.0, skip
            if room >= 1.41 * line:
                return 1, -45.0, skip
            if room >= line:
                return 1, -90.0, skip
        return 1, -90.0, count

    def _name_plan(self, axis, categories, style, plot_w, midcat=False) -> tuple:
        """(lines, angle, skip) of a category axis's names, with the file's own settings."""
        count = max(len(categories), 1)
        length = plot_w * count / max(count - 1, 1) if midcat and count > 1 else plot_w
        lines, angle, skip = self._category_layout(categories, style, length)
        if axis.turn is not None:
            angle = axis.turn
            line = self._line(style)
            band = length / count
            if angle:
                lines, skip = 1, 1
                while band * skip < line * (1.41 if abs(angle) < 80 else 1.0) and skip < count:
                    skip += 1
        if axis.skip:
            skip = int(axis.skip)
        return lines, angle, skip

    def _label_depth(self, axis, categories, style, plot_w, midcat=False) -> float:
        """How far a category axis's names reach from the axis."""
        lines, angle, skip = self._name_plan(axis, categories, style, plot_w, midcat)
        if angle:
            turn = math.radians(abs(angle))
            widest = max((self._width(text, style) for text in categories[::skip]), default=0.0)
            return min(widest * math.sin(turn) + self._line(style) * math.cos(turn), self.h * 0.45)
        return lines * self._line(style)

    def _value_on_far_side(self, values, category) -> bool:
        """Whether the value axis stands at the far end of the category axis."""
        at_max = values.crosses == "max"
        if category.reversed:
            at_max = not at_max
        if values.pos in ("r", "t") and values.crosses == "autoZero" and not category.reversed:
            at_max = False
        return at_max

    def _plot_background(self, frame) -> None:
        props = self.plot.find(C + "spPr")
        paint, stroke = 'fill="#FFFFFF"', 'stroke="none"'       # Office's look when none is stored
        if props is not None:
            fill = self.canvas.fill_of(props)
            paint = self.canvas.paint(fill) if fill is not None else 'fill="none"'
            stroke = self.canvas.stroke(props.find(A + "ln"))
        self.bars.append(f'<rect x="{frame.x:.2f}" y="{frame.y:.2f}" width="{frame.w:.2f}" height="{frame.h:.2f}" {paint} {stroke}/>')

    def _map_value(self, axis, frame, horizontal):
        start, stop, _ = axis.scale
        span = (stop - start) or 1.0

        def to_position(value):
            if axis.log_base:
                part = (math.log(max(value, start * 1e-3)) - math.log(start)) / ((math.log(stop) - math.log(start)) or 1.0)
            else:
                part = (value - start) / span
            if axis.reversed:
                part = 1 - part
            return frame.x + frame.w * part if horizontal else frame.y + frame.h * (1 - part)
        return to_position

    def _band(self, axis, frame, horizontal, count):
        """Where category ``i`` runs: its (start, end) along the category axis."""
        total = frame.h if horizontal else frame.w
        origin = frame.y if horizontal else frame.x
        size = total / max(count, 1)
        flip = axis.reversed != horizontal      # bars rise from the bottom unless reversed

        def span(index):
            at = count - 1 - index if flip else index
            return origin + at * size, origin + (at + 1) * size
        return span

    def _gridlines(self, frame, category, values, horizontal, scatter, categories) -> None:
        if values.grid is not None:
            to_position = self._map_value(values, frame, horizontal)
            stroke = self._grid_stroke(values.grid)
            start, stop, step = values.scale
            for tick in _ticks(start, stop, step):
                at = to_position(tick)
                if horizontal:
                    self.bars.append(f'<path d="M{at:.2f} {frame.y:.2f}V{frame.y + frame.h:.2f}" fill="none" {stroke}/>')
                else:
                    self.bars.append(f'<path d="M{frame.x:.2f} {at:.2f}H{frame.x + frame.w:.2f}" fill="none" {stroke}/>')
        if category.grid is not None:
            stroke = self._grid_stroke(category.grid)
            if scatter:
                to_position = self._map_value(category, frame, True)
                start, stop, step = category.scale
                for tick in _ticks(start, stop, step):
                    at = to_position(tick)
                    self.bars.append(f'<path d="M{at:.2f} {frame.y:.2f}V{frame.y + frame.h:.2f}" fill="none" {stroke}/>')
            else:
                span = self._band(category, frame, horizontal, len(categories))
                for index in range(len(categories) + 1):
                    at = span(index)[0] if index < len(categories) else span(len(categories) - 1)[1]
                    if horizontal:
                        self.bars.append(f'<path d="M{frame.x:.2f} {at:.2f}H{frame.x + frame.w:.2f}" fill="none" {stroke}/>')
                    else:
                        self.bars.append(f'<path d="M{at:.2f} {frame.y:.2f}V{frame.y + frame.h:.2f}" fill="none" {stroke}/>')

    def _grid_stroke(self, grid) -> str:
        props = grid.find(C + "spPr")
        line = props.find(A + "ln") if props is not None else None
        return self.canvas.stroke(line, default_width=0.5, default_color=self.palette.scheme_color("tx1"))

    def _axis_stroke(self, axis) -> str:
        props = axis.el.find(C + "spPr")
        line = props.find(A + "ln") if props is not None else None
        return self.canvas.stroke(line, default_width=0.5, default_color=self.palette.scheme_color("tx1"))

    def _bars(self, frame, group, kind, series, cat_axis, val_axis, horizontal, count) -> None:
        grouping = _val(group.find(C + "grouping"), "clustered")
        stacked = grouping in ("stacked", "percentStacked")
        gap = _number(_val(group.find(C + "gapWidth")), 150.0) / 100.0
        overlap = _number(_val(group.find(C + "overlap")), 100.0 if stacked else 0.0) / 100.0
        members = 1 if stacked else len(series)
        span = self._band(cat_axis, frame, horizontal, count)
        to_position = self._map_value(val_axis, frame, horizontal)
        start, stop, _ = val_axis.scale
        base = to_position(min(max(0.0, start), stop))
        vary = _flag(group, "varyColors", self.absent) and len(series) == 1
        ups, downs = [0.0] * count, [0.0] * count
        for number, one in enumerate(series):
            centers, tops = [], [None] * count
            for index in range(count):
                band_start, band_end = span(index)
                band = band_end - band_start
                bar = band / (members - (members - 1) * overlap + gap)
                used = bar * (members - (members - 1) * overlap)
                offset = (band - used) / 2
                slot = 0 if stacked else number
                # Clustered series read along the axis the way the categories do.
                if not stacked and horizontal != cat_axis.reversed:
                    slot = members - 1 - number
                near = band_start + offset + slot * bar * (1 - overlap)
                centers.append(near + bar / 2)
                value = one.values[index] if index < len(one.values) else None
                if value is None:
                    continue
                tops[index] = value
                if stacked:
                    total = 1.0
                    if grouping == "percentStacked":
                        total = sum(abs(s.values[index] or 0.0) for s in series if index < len(s.values)) or 1.0
                    shown = value / total
                    if shown >= 0:
                        low, high = ups[index], ups[index] + shown
                        ups[index] = high
                    else:
                        low, high = downs[index], downs[index] + shown
                        downs[index] = high
                    a, b = to_position(low), to_position(high)
                    tops[index] = high
                else:
                    a, b = base, to_position(value)
                if vary or index in one.points:
                    paint, stroke = self._point_paint(one, index, kind, group)
                else:
                    paint, stroke = self._series_paint(one)
                if value < 0 and _flag(one.el, "invertIfNegative", self.absent):
                    paint = 'fill="#FFFFFF"'
                if horizontal:
                    x, width = min(a, b), abs(b - a)
                    self.bars.append(f'<rect x="{x:.2f}" y="{near:.2f}" width="{width:.2f}" height="{bar:.2f}" {paint} {stroke}/>')
                else:
                    y, height = min(a, b), abs(b - a)
                    self.bars.append(f'<rect x="{near:.2f}" y="{y:.2f}" width="{bar:.2f}" height="{height:.2f}" {paint} {stroke}/>')
                self._bar_label(one, group, index, value, a, b, near, bar, horizontal, stacked)
            self._extras(one, list(range(1, count + 1)), tops, _along(centers, to_position, horizontal), frame)

    def _extras(self, series, xs, ys, place, frame) -> None:
        """A series' trendlines and error bars. ``place`` turns its data into a point on the page."""
        pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        for line in series.el.findall(C + "trendline"):
            points = _trend_points(_val(line.find(C + "trendlineType"), "linear"), pairs,
                                   int(_number(_val(line.find(C + "order")), 2)), int(_number(_val(line.find(C + "period")), 2)),
                                   _number(_val(line.find(C + "forward")), 0.0), _number(_val(line.find(C + "backward")), 0.0))
            shown = [place(x, y) for x, y in points]
            shown = [(x, y) for x, y in shown if frame.x - 1 <= x <= frame.x + frame.w + 1 and frame.y - 1 <= y <= frame.y + frame.h + 1]
            if len(shown) > 1:
                props = line.find(C + "spPr")
                stroke = self.canvas.stroke(props.find(A + "ln") if props is not None else None, default_width=0.75, default_color="000000")
                self.front.append(f'<path d="{_path(shown, False)}" fill="none" {stroke}/>')
        for bars in series.el.findall(C + "errBars"):
            self._error_bars(series, bars, pairs, place, frame)

    def _error_bars(self, series, bars, pairs, place, frame) -> None:
        props = bars.find(C + "spPr")
        stroke = self.canvas.stroke(props.find(A + "ln") if props is not None else None, default_width=0.75, default_color="000000")
        across = _val(bars.find(C + "errDir"), "y") == "x"
        kind = _val(bars.find(C + "errValType"), "fixedVal")
        which = _val(bars.find(C + "errBarType"), "both")
        amount = _number(_val(bars.find(C + "val")), 1.0)
        plus, _ = _numbers(bars.find(C + "plus"))
        minus, _ = _numbers(bars.find(C + "minus"))
        data = [pair[0 if across else 1] for pair in pairs]
        mean = sum(data) / len(data) if data else 0.0
        deviation = math.sqrt(sum((v - mean) ** 2 for v in data) / max(len(data) - 1, 1)) if data else 0.0
        caps = not _flag(bars, "noEndCap")

        def inside(point):
            return max(frame.x, min(frame.x + frame.w, point[0])), max(frame.y, min(frame.y + frame.h, point[1]))

        for index, (x, y) in enumerate(pairs):
            value = x if across else y
            if kind == "percentage":
                up = down = abs(value) * amount / 100.0
            elif kind == "stdDev":
                up = down = deviation * amount
            elif kind == "stdErr":
                up = down = deviation / math.sqrt(max(len(data), 1))
            elif kind == "cust":
                up = (plus[index] or 0.0) if index < len(plus) else 0.0
                down = (minus[index] or 0.0) if index < len(minus) else 0.0
            else:
                up = down = amount
            ends = []
            if which != "minus":
                ends.append(value + up)
            if which != "plus":
                ends.append(value - down)
            origin = place(x, y)
            for end in ends:
                tip = inside(place(end, y) if across else place(x, end))
                self.front.append(f'<path d="M{origin[0]:.2f} {origin[1]:.2f}L{tip[0]:.2f} {tip[1]:.2f}" fill="none" {stroke}/>')
                if caps:
                    if abs(tip[0] - origin[0]) > abs(tip[1] - origin[1]):
                        cap = f"M{tip[0]:.2f} {tip[1] - 3:.2f}V{tip[1] + 3:.2f}"
                    else:
                        cap = f"M{tip[0] - 3:.2f} {tip[1]:.2f}H{tip[0] + 3:.2f}"
                    self.front.append(f'<path d="{cap}" fill="none" {stroke}/>')

    def _stock_marks(self, frame, group, series, cat_axis, val_axis, count) -> None:
        """The high-low lines and up-down bars of a stock chart."""
        high_low, up_down = group.find(C + "hiLowLines"), group.find(C + "upDownBars")
        if high_low is None and up_down is None:
            return
        to_y = self._map_value(val_axis, frame, False)
        x_of = self._point_x(cat_axis, frame, count, self._midcat(val_axis))
        for index in range(count):
            values = [one.values[index] for one in series if index < len(one.values) and one.values[index] is not None]
            if len(values) < 2:
                continue
            x = x_of(index)
            if high_low is not None:
                props = high_low.find(C + "spPr")
                stroke = self.canvas.stroke(props.find(A + "ln") if props is not None else None, default_width=0.75, default_color="000000")
                self.bars.append(f'<path d="M{x:.2f} {to_y(max(values)):.2f}V{to_y(min(values)):.2f}" fill="none" {stroke}/>')
            if up_down is not None:
                rising = values[-1] >= values[0]
                part = up_down.find(C + ("upBars" if rising else "downBars"))
                props = part.find(C + "spPr") if part is not None else None
                fill = self.canvas.fill_of(props) if props is not None else None
                paint = self.canvas.paint(fill) if fill is not None else ('fill="#FFFFFF"' if rising else 'fill="#000000"')
                stroke = self.canvas.stroke(props.find(A + "ln") if props is not None else None, default_width=0.75, default_color="000000")
                wide = frame.w / max(count, 1) / (1 + _number(_val(up_down.find(C + "gapWidth")), 150.0) / 100.0)
                top, bottom = sorted((to_y(values[0]), to_y(values[-1])))
                self.bars.append(f'<rect x="{x - wide / 2:.2f}" y="{top:.2f}" width="{wide:.2f}" height="{bottom - top:.2f}" {paint} {stroke}/>')

    def _bar_label(self, series, group, index, value, a, b, near, bar, horizontal, stacked) -> None:
        settings = self._point_labels(series, group, index)
        if not settings:
            return
        category = series.categories[index] if series.categories and index < len(series.categories) else ""
        text = self._label_text(settings, value, category, series.name, None, series.format)
        if not text:
            return
        style = settings["style"]
        position = settings["pos"] or ("ctr" if stacked else "outEnd")
        middle = near + bar / 2
        if horizontal:
            forward = 1 if b >= a else -1
            if position == "ctr":
                self.labels.append(self._text((a + b) / 2, middle, text, style))
            elif position == "inEnd":
                self.labels.append(self._text(b - forward * 6.1, middle, text, style, anchor="end" if forward > 0 else "start"))
            elif position == "inBase":
                self.labels.append(self._text(a + forward * 6.1, middle, text, style, anchor="start" if forward > 0 else "end"))
            else:
                self.labels.append(self._text(b + forward * 6.1, middle, text, style, anchor="start" if forward > 0 else "end"))
            return
        up = -1 if b <= a else 1
        half = self._line(style) / 2
        if position == "ctr":
            self.labels.append(self._text(middle, (a + b) / 2, text, style))
        elif position == "inEnd":
            self.labels.append(self._text(middle, b - up * (half + 5.05), text, style))
        elif position == "inBase":
            self.labels.append(self._text(middle, a + up * (half + 3.95), text, style))
        else:
            self.labels.append(self._text(middle, b + up * (half + 4.0), text, style))

    def _point_x(self, axis, frame, count, midcat):
        span = self._band(axis, frame, False, count)
        if midcat and count > 1:
            first, last = span(0), span(count - 1)
            a = (first[0] if not axis.reversed else first[1])
            b = (last[1] if not axis.reversed else last[0])
            return lambda index: a + (b - a) * index / (count - 1)
        return lambda index: sum(span(index)) / 2

    def _midcat(self, value_axis) -> bool:
        return value_axis.between == "midCat"

    def _stacked_values(self, series, grouping, count) -> list:
        """Each series' drawn values, stacked if the chart stacks them."""
        if grouping not in ("stacked", "percentStacked"):
            return [one.values for one in series]
        running = [0.0] * count
        out = []
        for one in series:
            drawn = []
            for index in range(count):
                value = one.values[index] if index < len(one.values) else None
                if value is None:
                    drawn.append(running[index])
                    continue
                if grouping == "percentStacked":
                    total = sum(abs(s.values[index] or 0.0) for s in series if index < len(s.values)) or 1.0
                    value /= total
                running[index] += value
                drawn.append(running[index])
            out.append(drawn)
        return out

    def _areas(self, frame, group, kind, series, cat_axis, val_axis, count) -> None:
        grouping = _val(group.find(C + "grouping"), "standard")
        drawn = self._stacked_values(series, grouping, count)
        to_y = self._map_value(val_axis, frame, False)
        x_of = self._point_x(cat_axis, frame, count, self._midcat(val_axis))
        floor = to_y(min(max(0.0, val_axis.scale[0]), val_axis.scale[1]))
        previous = None
        for one, values in zip(series, drawn):
            points = [(x_of(i), to_y(v)) for i, v in enumerate(values[:count]) if v is not None]
            if not points:
                continue
            if grouping in ("stacked", "percentStacked") and previous:
                lower = list(reversed(previous))
            else:
                lower = [(points[-1][0], floor), (points[0][0], floor)]
            d = "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in points + lower) + "Z"
            paint, stroke = self._series_paint(one)
            self.bars.append(f'<path d="{d}" {paint} {stroke}/>')
            previous = points
            for index, value in enumerate(one.values[:count]):
                settings = self._point_labels(one, group, index)
                if settings and value is not None:
                    category = one.categories[index] if one.categories and index < len(one.categories) else ""
                    text = self._label_text(settings, value, category, one.name, None, one.format)
                    if text:
                        self.labels.append(self._text(x_of(index), to_y(values[index]) - settings["style"].size * 0.8, text, settings["style"]))

    def _lines(self, frame, group, kind, series, cat_axis, val_axis, horizontal, count) -> None:
        grouping = _val(group.find(C + "grouping"), "standard")
        drawn = self._stacked_values(series, grouping, count)
        to_y = self._map_value(val_axis, frame, False)
        x_of = self._point_x(cat_axis, frame, count, self._midcat(val_axis))
        for one, values in zip(series, drawn):
            stroke = self._line_stroke(one, kind)
            pieces, current = [], []
            for index, value in enumerate(values[:count]):
                original = one.values[index] if index < len(one.values) else None
                if original is None:
                    if current:
                        pieces.append(current)
                    current = []
                    continue
                current.append((x_of(index), to_y(value)))
            if current:
                pieces.append(current)
            smooth = _flag(one.el, "smooth", self.absent)
            if stroke != 'stroke="none"':
                for points in pieces:
                    if len(points) > 1:
                        self.front.append(f'<path d="{_path(points, smooth)}" fill="none" {stroke}/>')
            marker = self._marker_of(one, kind, group)
            for index, value in enumerate(values[:count]):
                original = one.values[index] if index < len(one.values) else None
                if original is None:
                    continue
                x, y = x_of(index), to_y(value)
                if marker:
                    self.front.append(self._draw_marker(marker, x, y, one))
                settings = self._point_labels(one, group, index)
                if settings:
                    category = one.categories[index] if one.categories and index < len(one.categories) else ""
                    text = self._label_text(settings, original, category, one.name, None, one.format)
                    if text:
                        self.labels.append(self._positioned(x, y, text, settings))
            shown = [v if i < len(one.values) and one.values[i] is not None else None for i, v in enumerate(values[:count])]
            self._extras(one, list(range(1, count + 1)), shown, _along([x_of(i) for i in range(count)], to_y, False), frame)

    def _positioned(self, x, y, text, settings) -> str:
        """A label beside its point: to the right unless the file says otherwise."""
        style, position = settings["style"], settings["pos"] or "r"
        half = self._line(style) / 2
        if position == "t":
            return self._text(x, y - half - 6.55, text, style)
        if position == "b":
            return self._text(x, y + half + 7.55, text, style)
        if position == "l":
            return self._text(x - 8.5, y, text, style, anchor="end")
        if position == "ctr":
            return self._text(x, y, text, style)
        return self._text(x + 8.5, y, text, style, anchor="start")

    def _scatter(self, frame, group, kind, series, x_axis, y_axis) -> None:
        to_x = self._map_value(x_axis, frame, True)
        to_y = self._map_value(y_axis, frame, False)
        largest = max((v or 0.0 for one in series for v in one.sizes), default=0.0) or 1.0
        scale = _number(_val(group.find(C + "bubbleScale")), 100.0) / 100.0
        for one in series:
            xs = one.xs or [float(i + 1) for i in range(len(one.values))]
            points = [(to_x(x), to_y(y)) for x, y in zip(xs, one.values) if x is not None and y is not None]
            if kind == "bubbleChart":
                paint, stroke = self._series_paint(one)
                for (x, y), size in zip(points, one.sizes):
                    radius = math.sqrt((size or 0.0) / largest) * min(frame.w, frame.h) * 0.1475 * scale
                    self.front.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" {paint} {stroke}/>')
                continue
            stroke = self._line_stroke(one, kind)
            if stroke != 'stroke="none"' and len(points) > 1:
                self.front.append(f'<path d="{_path(points, _flag(one.el, "smooth", self.absent))}" fill="none" {stroke}/>')
            marker = self._marker_of(one, kind, group)
            for index, (x, y) in enumerate(points):
                if marker:
                    self.front.append(self._draw_marker(marker, x, y, one))
                settings = self._point_labels(one, group, index)
                if settings:
                    text = self._label_text(settings, one.values[index], "", one.name, None, one.format)
                    if text:
                        self.labels.append(self._positioned(x, y, text, settings))
            self._extras(one, xs, one.values, lambda a, b: (to_x(a), to_y(b)), frame)

    def _draw_axes(self, frame, layout) -> None:
        category, values, secondary = layout.category, layout.values, layout.secondary
        far = self._value_on_far_side(values, category)
        self._draw_value_axis(frame, values, category, layout.horizontal, far)
        if secondary is not None:
            self._draw_value_axis(frame, secondary, category, layout.horizontal, not far)
        if layout.scatter:
            self._draw_x_axis(frame, category, values)
        else:
            self._draw_category_axis(frame, layout)

    def _draw_value_axis(self, frame, axis, category, horizontal, far) -> None:
        if axis.deleted:
            return
        style = self._axis_style(axis)
        line = self._line(style)
        to_position = self._map_value(axis, frame, horizontal)
        stroke = self._axis_stroke(axis)
        code = self._value_code(axis)
        start, stop, step = axis.scale
        tick_in, tick_out = {"out": (0.0, 3.17), "in": (3.17, 0.0), "cross": (3.17, 3.17)}.get(axis.major_mark, (0.0, 0.0))
        if horizontal:
            line_y = frame.y if far else frame.y + frame.h
            sign = -1 if far else 1
            self.front.append(f'<path d="M{frame.x:.2f} {line_y:.2f}H{frame.x + frame.w:.2f}" fill="none" {stroke}/>')
            for tick in _ticks(start, stop, step):
                at = to_position(tick)
                if tick_in or tick_out:
                    self.front.append(f'<path d="M{at:.2f} {line_y - sign * tick_in:.2f}V{line_y + sign * tick_out:.2f}" fill="none" {stroke}/>')
                if axis.labels != "none":
                    y = line_y + sign * (0.642 * style.size + line / 2) + (0.0 if far else 0.0)
                    self.labels.append(self._text(at, y, format_number(tick / axis.divide, code), style))
            title = self._axis_title(axis)
            if title:
                baseline = frame.y + frame.h + 0.642 * style.size + line + 3.03 + font_info(title[1].family[0]).ascent * title[1].size
                self.labels.append(self._text(frame.x + frame.w / 2, baseline - MID * title[1].size, title[0], title[1]))
            return
        line_x = frame.x + frame.w if far else frame.x
        sign = 1 if far else -1
        self.front.append(f'<path d="M{line_x:.2f} {frame.y:.2f}V{frame.y + frame.h:.2f}" fill="none" {stroke}/>')
        gap = 0.923 * style.size
        for tick in _ticks(start, stop, step):
            at = to_position(tick)
            if tick_in or tick_out:
                self.front.append(f'<path d="M{line_x - sign * tick_in:.2f} {at:.2f}H{line_x + sign * tick_out:.2f}" fill="none" {stroke}/>')
            if axis.labels != "none":
                text = format_number(tick / axis.divide, code)
                self.labels.append(self._text(line_x + sign * gap, at, text, style, anchor="start" if far else "end"))
        title = self._axis_title(axis)
        if title:
            size = self._line(title[1])
            edge = 12.4 + size / 2
            x = self.w - edge if far else edge
            if self._room_left and not far:
                x += self._room_left
            if self._room_right and far:
                x -= self._room_right
            turn = title[2] if title[2] is not None else (90 if far else -90)
            y = frame.y + frame.h / 2
            if axis.el.find(C + "title") is None:
                y = frame.y + 10.7
            self.labels.append(self._text(x, y, title[0], title[1], rotate=turn))

    def _draw_x_axis(self, frame, axis, values) -> None:
        if axis.deleted:
            return
        style = self._axis_style(axis)
        line = self._line(style)
        to_x = self._map_value(axis, frame, True)
        stroke = self._axis_stroke(axis)
        line_y = frame.y + frame.h
        self.front.append(f'<path d="M{frame.x:.2f} {line_y:.2f}H{frame.x + frame.w:.2f}" fill="none" {stroke}/>')
        code = axis.code if not axis.linked and axis.code else "General"
        start, stop, step = axis.scale
        tick_in, tick_out = {"out": (0.0, 3.17), "in": (3.17, 0.0), "cross": (3.17, 3.17)}.get(axis.major_mark, (0.0, 0.0))
        for tick in _ticks(start, stop, step):
            at = to_x(tick)
            if tick_in or tick_out:
                self.front.append(f'<path d="M{at:.2f} {line_y - tick_in:.2f}V{line_y + tick_out:.2f}" fill="none" {stroke}/>')
            if axis.labels != "none":
                self.labels.append(self._text(at, line_y + 0.642 * style.size + line / 2, format_number(tick, code), style))
        title = self._axis_title(axis)
        if title:
            baseline = line_y + 0.642 * style.size + line + 3.03 + font_info(title[1].family[0]).ascent * title[1].size
            self.labels.append(self._text(frame.x + frame.w / 2, baseline - MID * title[1].size, title[0], title[1]))

    def _draw_category_axis(self, frame, layout) -> None:
        axis, values, categories, horizontal = layout.category, layout.values, layout.names, layout.horizontal
        if axis.deleted:
            return
        style = self._axis_style(axis)
        stroke = self._axis_stroke(axis)
        line_height = self._line(style)
        to_position = self._map_value(values, frame, horizontal)
        line = to_position(self._crossing(axis, values))
        span = self._band(axis, frame, horizontal, len(categories))
        side = self._labels_side(layout)
        tick_in, tick_out = {"out": (0.0, 3.17), "in": (3.17, 0.0), "cross": (3.17, 3.17)}.get(axis.major_mark, (0.0, 0.0))
        midcat = values.between == "midCat"
        if horizontal:
            self.front.append(f'<path d="M{line:.2f} {frame.y:.2f}V{frame.y + frame.h:.2f}" fill="none" {stroke}/>')
            toward = 1 if values.reversed else -1
            edge = {"near": frame.x, "far": frame.x + frame.w}.get(side, line)
            limit = self.w * 0.45
            for index, text in enumerate(categories):
                a, b = span(index)
                if tick_in or tick_out:
                    self.front.append(f'<path d="M{line - toward * tick_in:.2f} {a:.2f}H{line + toward * tick_out:.2f}" fill="none" {stroke}/>')
                if axis.labels == "none" or (axis.skip and index % int(axis.skip)):
                    continue
                shown, cut = self._cut_name(text, style, limit)
                reach = 2.02 if cut else 8.31
                self.labels.append(self._text(edge + toward * reach, (a + b) / 2, shown, style, anchor="start" if toward > 0 else "end"))
            if (tick_in or tick_out) and categories:
                end = span(len(categories) - 1)[0] if not axis.reversed else span(len(categories) - 1)[1]
                far_end = frame.y if abs(end - frame.y) < abs(end - frame.y - frame.h) else frame.y + frame.h
                self.front.append(f'<path d="M{line - toward * tick_in:.2f} {far_end:.2f}H{line + toward * tick_out:.2f}" fill="none" {stroke}/>')
        else:
            self.front.append(f'<path d="M{frame.x:.2f} {line:.2f}H{frame.x + frame.w:.2f}" fill="none" {stroke}/>')
            above = side == "far"
            axis_y = frame.y if above else (frame.y + frame.h if side == "near" else line)
            lines, angle, skip = self._name_plan(axis, categories, style, frame.w, midcat)
            count = max(len(categories), 1)
            band = frame.w / count if not midcat else frame.w / max(count - 1, 1)
            x_of = self._point_x(axis, frame, len(categories), midcat)
            first_y = axis_y + 0.642 * style.size + line_height / 2
            for index, text in enumerate(categories):
                a, b = span(index)
                if tick_in or tick_out:
                    self.front.append(f'<path d="M{a:.2f} {line - tick_in:.2f}V{line + tick_out:.2f}" fill="none" {stroke}/>')
                if axis.labels == "none" or index % skip:
                    continue
                middle = x_of(index)
                if angle:
                    start = axis_y + 0.642 * style.size
                    if abs(angle) >= 80:
                        self.labels.append(self._text(middle, start, text, style, anchor="end" if angle < 0 else "start", rotate=angle))
                    else:
                        self.labels.append(self._text(middle, start + line_height * 0.25 + 1.5, text, style, anchor="end" if angle < 0 else "start", rotate=angle))
                elif above:
                    pieces = self._wrap(text, style, band * skip)
                    for number, piece in enumerate(reversed(pieces)):
                        y = axis_y - 0.642 * style.size - line_height * (number + 0.5)
                        self.labels.append(self._text(middle, y, piece, style))
                else:
                    pieces = [text] if self._width(text, style) <= band * skip * 0.94 else self._wrap(text, style, band * skip)
                    for number, piece in enumerate(pieces):
                        self.labels.append(self._text(middle, first_y + line_height * number, piece, style))
            if (tick_in or tick_out) and categories:
                self.front.append(f'<path d="M{frame.x + frame.w:.2f} {line - tick_in:.2f}V{line + tick_out:.2f}" fill="none" {stroke}/>')
        title = self._axis_title(axis)
        if title:
            size = self._line(title[1])
            if horizontal:
                turned = title[2] != 0
                x = 12.4 + size / 2 if turned else 14.11 + self._width(title[0], title[1]) / 2
                if values.reversed:
                    x = self.w - x
                self.labels.append(self._text(x, frame.y + frame.h / 2, title[0], title[1], rotate=(title[2] if turned and title[2] is not None else -90) if turned else 0.0))
            else:
                depth = self._label_depth(axis, categories, style, frame.w, midcat)
                baseline = frame.y + frame.h + 0.642 * style.size + depth + 3.03 + font_info(title[1].family[0]).ascent * title[1].size
                self.labels.append(self._text(frame.x + frame.w / 2, baseline - MID * title[1].size, title[0], title[1]))

    def _radar(self, room) -> None:
        kind, group, series = next(g for g in self.groups if g[0] == "radarChart")
        categories = self._categories()
        count = max(len(categories), 3)
        cat_axis, val_axis = self._axis_pair(group)
        style = self._axis_style(cat_axis) if cat_axis is not None else self.base
        line = self._line(style)
        left, top = room.left + OUTER, room.top + OUTER
        right, bottom = self.w - room.right - OUTER, self.h - room.bottom - OUTER
        cx, cy = (left + right) / 2, (top + bottom) / 2
        widest = max((self._width(name, style) for name in categories), default=0.0)
        radius = max(10.0, min((bottom - top) / 2 - 0.953 * style.size, (right - left) / 2 - widest - 1.71))
        if val_axis is not None:
            self._scale_axis(val_axis, radius, 1.07 * self._line(self._axis_style(val_axis)))
            start, stop, step = val_axis.scale
        else:
            start, stop, step = 0.0, 1.0, 0.2

        def point(index, value):
            angle = math.radians(-90.0 + 360.0 * index / count)
            r = radius * (value - start) / ((stop - start) or 1.0)
            return cx + r * math.cos(angle), cy + r * math.sin(angle)

        grid = self._grid_stroke(val_axis.grid) if val_axis is not None and val_axis.grid is not None else 'stroke="#D9D9D9" stroke-width="0.75"'
        filled = _val(group.find(C + "radarStyle")) == "filled"
        rings, spokes, numbers = [], [], []
        for tick in _ticks(start, stop, step):
            ring = [point(i, tick) for i in range(count)]
            rings.append('<path d="M' + "L".join(f"{x:.2f} {y:.2f}" for x, y in ring) + f'Z" fill="none" {grid}/>')
            if val_axis is not None and not val_axis.deleted and val_axis.labels != "none":
                x, y = point(0, tick)
                value_style = self._axis_style(val_axis)
                numbers.append(self._text(x - 0.923 * value_style.size - 0.73, y + 0.05 * value_style.size, format_number(tick / val_axis.divide, self._value_code(val_axis)), value_style, anchor="end"))
        for index in range(count):
            x, y = point(index, stop)
            spokes.append(f'<path d="M{cx:.2f} {cy:.2f}L{x:.2f} {y:.2f}" fill="none" {grid}/>')
            if index < len(categories):
                angle = math.radians(-90.0 + 360.0 * index / count)
                along, across = math.cos(angle), math.sin(angle)
                if abs(along) < 0.2:
                    lx, ly = x, y + (-1 if across < 0 else 1) * (line / 2 + 1.7)
                    self.labels.append(self._text(lx, ly, categories[index], style))
                else:
                    self.labels.append(self._text(x + (1.71 if along > 0 else -1.71), y, categories[index], style, anchor="start" if along > 0 else "end"))
        drawn = []
        for one in series:
            points = [point(i, v) for i, v in enumerate(one.values[:count]) if v is not None]
            if len(points) < 2:
                continue
            d = "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in points) + "Z"
            if filled:
                paint, stroke = self._series_paint(one)
                drawn.append(f'<path d="{d}" {paint} {stroke}/>')
            else:
                drawn.append(f'<path d="{d}" fill="none" {self._line_stroke(one, kind)}/>')
            marker = self._marker_of(one, kind, group)
            if marker:
                for x, y in points:
                    drawn.append(self._draw_marker(marker, x, y, one))
        # A filled radar's rings stand over its colours; lines go over the rings.
        self.bars += (drawn + rings + spokes) if filled else (rings + spokes + drawn)
        self.labels += numbers

def _rounded_shares(values: list) -> list:
    """Each value's share, so that shown as whole percents they add up to 100:
    what rounding leaves over goes to the largest remainders, the later of equals first."""
    total = sum(values) or 1.0
    exact = [value / total * 100.0 for value in values]
    whole = [math.floor(share + 1e-9) for share in exact]
    left = 100 - sum(whole)
    order = sorted(range(len(values)), key=lambda i: (-round(exact[i] - whole[i], 6), -i))
    for index in order[:max(left, 0)]:
        whole[index] += 1
    return [share / 100.0 for share in whole]


def _slice(cx, cy, outer, inner, start, sweep) -> str:
    if sweep >= 359.99:
        ring = (f"M{cx - outer:.2f} {cy:.2f}A{outer:.2f} {outer:.2f} 0 1 1 {cx + outer:.2f} {cy:.2f}"
                f"A{outer:.2f} {outer:.2f} 0 1 1 {cx - outer:.2f} {cy:.2f}Z")
        if inner > 0:
            ring += (f"M{cx - inner:.2f} {cy:.2f}A{inner:.2f} {inner:.2f} 0 1 0 {cx + inner:.2f} {cy:.2f}"
                     f"A{inner:.2f} {inner:.2f} 0 1 0 {cx - inner:.2f} {cy:.2f}Z")
        return ring
    a0, a1 = math.radians(start), math.radians(start + sweep)
    large = 1 if sweep > 180 else 0
    x0, y0, x1, y1 = cx + outer * math.cos(a0), cy + outer * math.sin(a0), cx + outer * math.cos(a1), cy + outer * math.sin(a1)
    if inner > 0:
        x2, y2, x3, y3 = cx + inner * math.cos(a1), cy + inner * math.sin(a1), cx + inner * math.cos(a0), cy + inner * math.sin(a0)
        return (f"M{x0:.2f} {y0:.2f}A{outer:.2f} {outer:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}L{x2:.2f} {y2:.2f}"
                f"A{inner:.2f} {inner:.2f} 0 {large} 0 {x3:.2f} {y3:.2f}Z")
    return f"M{cx:.2f} {cy:.2f}L{x0:.2f} {y0:.2f}A{outer:.2f} {outer:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}Z"


class _Layout:
    """The axes of a chart with axes, and what they label."""

    def __init__(self, category, values, secondary, names, horizontal, scatter):
        self.category, self.values, self.secondary = category, values, secondary
        self.names, self.horizontal, self.scatter = names, horizontal, scatter


def _along(centers: list, to_value, horizontal: bool):
    """Turns (category number from 1, value) into a point on the page."""

    def place(x, y):
        at = x - 1
        if len(centers) > 1:
            index = max(0, min(len(centers) - 2, int(math.floor(at))))
            along = centers[index] + (centers[index + 1] - centers[index]) * (at - index)
        else:
            along = centers[0] if centers else 0.0
        value = to_value(y)
        return (value, along) if horizontal else (along, value)
    return place


def _line_fit(xs: list, ys: list) -> tuple:
    """Least squares: (a, b) of y = a + b x."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    spread = sum((x - mean_x) ** 2 for x in xs)
    b = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread if spread else 0.0
    return mean_y - b * mean_x, b


def _poly_fit(xs: list, ys: list, order: int) -> list:
    """Least squares through a polynomial: its coefficients, lowest first."""
    size = order + 1
    rows = [[sum(x ** (i + j) for x in xs) for j in range(size)] + [sum(y * x ** i for x, y in zip(xs, ys))] for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        if not rows[column][column]:
            return [0.0] * size
        for row in range(size):
            if row != column:
                factor = rows[row][column] / rows[column][column]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[column])]
    return [rows[i][size] / rows[i][i] for i in range(size)]


def _trend_points(kind: str, pairs: list, order=2, period=2, forward=0.0, backward=0.0) -> list:
    """The points of a trendline through (x, y) pairs."""
    if len(pairs) < 2:
        return []
    if kind == "movingAvg":
        period = max(2, period)
        return [(pairs[i][0], sum(y for _, y in pairs[i - period + 1:i + 1]) / period) for i in range(period - 1, len(pairs))]
    xs, ys = [x for x, _ in pairs], [y for _, y in pairs]
    if kind == "log":
        kept = [(x, y) for x, y in pairs if x > 0]
        if len(kept) < 2:
            return []
        a, b = _line_fit([math.log(x) for x, _ in kept], [y for _, y in kept])
        fit = lambda x: a + b * math.log(x)
    elif kind == "exp":
        kept = [(x, y) for x, y in pairs if y > 0]
        if len(kept) < 2:
            return []
        a, b = _line_fit([x for x, _ in kept], [math.log(y) for _, y in kept])
        fit = lambda x: math.exp(a + b * x)
    elif kind == "power":
        kept = [(x, y) for x, y in pairs if x > 0 and y > 0]
        if len(kept) < 2:
            return []
        a, b = _line_fit([math.log(x) for x, _ in kept], [math.log(y) for _, y in kept])
        fit = lambda x: math.exp(a) * x ** b
    elif kind == "poly":
        terms = _poly_fit(xs, ys, max(2, order))
        fit = lambda x: sum(term * x ** i for i, term in enumerate(terms))
    else:
        a, b = _line_fit(xs, ys)
        fit = lambda x: a + b * x
    low, high = min(xs) - (backward or 0.0), max(xs) + (forward or 0.0)
    if kind in ("log", "power"):
        low = max(low, 1e-9)
    steps = 1 if kind == "linear" else 60
    return [(low + (high - low) * i / steps, fit(low + (high - low) * i / steps)) for i in range(steps + 1)]


def _path(points, smooth: bool) -> str:
    """A line through points; smooth lines bend the way Office's do."""
    if not smooth or len(points) < 3:
        return "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in points)
    d = [f"M{points[0][0]:.2f} {points[0][1]:.2f}"]
    for index in range(len(points) - 1):
        p0 = points[index - 1] if index else points[index]
        p1, p2 = points[index], points[index + 1]
        p3 = points[index + 2] if index + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    return "".join(d)


def chart_html(root, palette: Palette, width: float, height: float, unit, picture=None, absent: bool = True) -> str:
    """A chart part's XML as an SVG of the given size (points). ``absent`` is what a
    yes-or-no setting left out of the file means: yes, except in Word 2007's files."""
    return _Chart(root, palette, width, height, picture, absent).svg(unit)
