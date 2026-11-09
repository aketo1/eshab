"""The chart kinds Office 2016 added, which store their data their own way:
waterfall, funnel, treemap, sunburst, box and whisker, histogram and Pareto.
A map chart can't be drawn without its map data, so its regions and values
come out as columns: nothing in the file is lost.
"""
from __future__ import annotations

import math
import statistics

from .charts import ARABIC, Style, TextKit, _slice, _ticks, auto_scale, format_number
from .drawingml import A, Canvas, Palette

CX = "{http://schemas.microsoft.com/office/drawing/2014/chartex}"
GREY_TEXT = "595959"
GRID = "D9D9D9"


def _number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _shade(color: str, amount: float) -> str:
    channels = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
    if amount >= 0:
        channels = [c + (255 - c) * amount for c in channels]
    else:
        channels = [c * (1 + amount) for c in channels]
    return "%02X%02X%02X" % tuple(int(max(0, min(255, c))) for c in channels)


class _Data:
    """One cx:data: its category levels (innermost first) and values."""

    def __init__(self, element):
        self.levels, self.values, self.code = [], [], None
        if element is None:
            return
        for dim in element:
            if dim.tag == CX + "strDim":
                self.levels = [self._points(level, str) for level in dim.findall(CX + "lvl")]
            elif dim.tag == CX + "numDim" and dim.get("type") in ("val", "size", None):
                level = dim.find(CX + "lvl")
                if level is not None:
                    self.values = self._points(level, _number)
                    self.code = level.get("formatCode")

    @staticmethod
    def _points(level, convert) -> list:
        count = int(_number(level.get("ptCount"), 0))
        points = level.findall(CX + "pt")
        out = [None] * max(count, max((int(p.get("idx", 0)) + 1 for p in points), default=0))
        for point in points:
            out[int(point.get("idx", 0))] = convert(point.text or "")
        return out

    def category(self, index: int) -> str:
        if self.levels and index < len(self.levels[0]):
            return self.levels[0][index] or ""
        return ""

    def paths(self) -> list:
        """Each row as (names from the outermost level in, value)."""
        rows = []
        filled = [None] * len(self.levels)
        for index, value in enumerate(self.values):
            names = []
            for depth in range(len(self.levels) - 1, -1, -1):
                level = self.levels[depth]
                name = level[index] if index < len(level) else None
                if name:
                    filled[depth] = name
                    for deeper in range(depth):
                        filled[deeper] = None
                if filled[depth]:
                    names.append(filled[depth])
            if value is not None and value > 0:
                rows.append((names or [str(index + 1)], value))
        return rows


class _Extended(TextKit):
    def __init__(self, root, palette: Palette, width: float, height: float, picture=None):
        self.root = root
        self.palette = palette
        self.canvas = Canvas(palette, picture)
        self.w, self.h = max(width, 10.0), max(height, 10.0)
        self.base = Style(9.0, False, False, GREY_TEXT, self._families())
        self.chart = root.find(CX + "chart")
        self.plot = self.chart.find(CX + "plotArea") if self.chart is not None else None
        region = self.plot.find(CX + "plotAreaRegion") if self.plot is not None else None
        self.series = region.findall(CX + "series") if region is not None else []
        self.data = {d.get("id"): _Data(d) for d in root.iter(CX + "data")}
        self.axes = self.plot.findall(CX + "axis") if self.plot is not None else []
        self.out, self.labels = [], []

    # -- the chart's own frame ---------------------------------------------------------

    def svg(self, unit) -> str:
        area = [8.0, 6.0, self.w - 8.0, self.h - 6.0]
        background = self._background()
        title = self._title(area)
        kind = self.series[0].get("layoutId") if self.series else ""
        names = self._legend_names(kind)
        legend = self._legend(area, names)
        draw = {"waterfall": self._waterfall, "funnel": self._funnel, "treemap": self._treemap, "sunburst": self._sunburst,
                "boxWhisker": self._box_whisker, "clusteredColumn": self._columns, "regionMap": self._columns}.get(kind)
        if draw is not None:
            draw(area)
        body = [background] + self.out + self.labels + legend + title
        return (f'<svg class="chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.3f} {self.h:.3f}" '
                f'style="width:{unit(self.w)};height:{unit(self.h)};overflow:hidden;display:block" '
                f'preserveAspectRatio="none">{self.canvas.definitions()}{"".join(body)}</svg>')

    def _background(self) -> str:
        props = self.root.find(CX + "spPr")
        if props is None and self.chart is not None:
            props = self.chart.find(CX + "spPr")
        paint, stroke = 'fill="#FFFFFF"', f'stroke="#{GRID}" stroke-width="0.75"'
        if props is not None:
            fill = self.canvas.fill_of(props)
            if fill is not None:
                paint = self.canvas.paint(fill)
            if props.find(A + "ln") is not None:
                stroke = self.canvas.stroke(props.find(A + "ln"))
        return f'<rect x=".4" y=".4" width="{self.w - .8:.3f}" height="{self.h - .8:.3f}" {paint} {stroke}/>'

    def _title(self, area) -> list:
        title = self.chart.find(CX + "title") if self.chart is not None else None
        if title is None:
            return []
        style = self._style(title.find(CX + "txPr"), Style(14.0, False, False, GREY_TEXT, self.base.family))
        text = "".join(t.text or "" for t in title.iter(A + "t"))
        if not text:
            cached = next(title.iter(CX + "v"), None)
            text = (cached.text or "") if cached is not None else "Chart Title"
        props = next(title.iter(A + "rPr"), None)
        style = self._apply(props, style)
        out = []
        step = style.size * 1.2
        for index, line in enumerate(self._wrap(text, style, self.w * 0.9)):
            out.append(self._text(self.w / 2, area[1] + step * (index + 0.5), line, style))
            area[1] += step
        area[1] += 4
        return out

    def _accent(self, index: int) -> str:
        return self.palette.scheme_color(f"accent{index % 6 + 1}")

    def _point_color(self, series, index: int, default: str) -> str:
        for point in series.findall(CX + "dataPt"):
            if int(_number(point.get("idx"), -1)) == index:
                props = point.find(CX + "spPr")
                fill = self.canvas.fill_of(props) if props is not None else None
                if fill is not None:
                    found = self.palette.first_color(fill)
                    if found:
                        return found[0]
        return default

    def _series_color(self, series, index: int) -> str:
        props = series.find(CX + "spPr")
        fill = self.canvas.fill_of(props) if props is not None else None
        found = self.palette.first_color(fill) if fill is not None else None
        return found[0] if found else self._accent(index)

    def _data_of(self, series) -> _Data:
        data_id = series.find(CX + "dataId")
        return self.data.get(data_id.get("val") if data_id is not None else None) or _Data(None)

    def _shows_values(self, series) -> bool:
        labels = series.find(CX + "dataLabels")
        if labels is None:
            return False
        shown = labels.find(CX + "visibility")
        return shown is None or shown.get("value") != "0"

    def _label_code(self, series, default) -> str:
        labels = series.find(CX + "dataLabels")
        fmt = labels.find(CX + "numFmt") if labels is not None else None
        return (fmt.get("formatCode") if fmt is not None else None) or default or "General"

    # -- the legend --------------------------------------------------------------------

    def _legend_names(self, kind: str) -> list:
        if self.chart is None or self.chart.find(CX + "legend") is None or not self.series:
            return []
        first = self._data_of(self.series[0])
        arabic = any(ARABIC.search(name or "") for level in first.levels for name in level)
        if kind == "waterfall":
            words = ("زيادة", "نقصان", "الإجمالي") if arabic else ("Increase", "Decrease", "Total")
            return list(zip(words, (self._accent(0), self._accent(1), self._accent(2))))
        if kind in ("treemap", "sunburst"):
            tops = []
            for names, _ in first.paths():
                if names[0] not in tops:
                    tops.append(names[0])
            return [(name, self._accent(index)) for index, name in enumerate(tops)]
        if kind in ("boxWhisker",) or len(self.series) > 1:
            out = []
            for index, series in enumerate(self.series):
                if series.get("layoutId") == "paretoLine":
                    continue
                cached = next(series.iter(CX + "v"), None)
                name = (cached.text if cached is not None else "") or f"Series{index + 1}"
                out.append((name, self._series_color(series, index)))
            return out
        return []

    def _legend(self, area, names: list) -> list:
        if not names:
            return []
        legend = self.chart.find(CX + "legend")
        style = self._style(legend.find(CX + "txPr"), self.base)
        position = legend.get("pos") or "t"
        key = style.size * 0.62
        widths = [key + 4 + self._width(name, style) for name, _ in names]
        out = []
        line = style.size * 1.35
        if position in ("l", "r"):
            x = area[2] - max(widths) if position == "r" else area[0]
            top = (area[1] + area[3] - line * len(names)) / 2
            for index, (name, color) in enumerate(names):
                y = top + line * (index + 0.5)
                out.append(f'<rect x="{x:.2f}" y="{y - key / 2:.2f}" width="{key:.2f}" height="{key:.2f}" fill="#{color}"/>')
                out.append(self._text(x + key + 4, y, name, style, anchor="start"))
            if position == "r":
                area[2] = x - 6
            else:
                area[0] = x + max(widths) + 6
            return out
        rows, row, used = [], [], 0.0
        for index, width in enumerate(widths):
            if row and used + width + 12 > area[2] - area[0]:
                rows.append((row, used))
                row, used = [], 0.0
            used += width + (12 if row else 0)
            row.append(index)
        rows.append((row, used))
        height = line * len(rows)
        top = area[1] if position == "t" else area[3] - height
        for number, (row, used) in enumerate(rows):
            x = (self.w - used) / 2
            y = top + line * (number + 0.5)
            for index in row:
                name, color = names[index]
                out.append(f'<rect x="{x:.2f}" y="{y - key / 2:.2f}" width="{key:.2f}" height="{key:.2f}" fill="#{color}"/>')
                out.append(self._text(x + key + 4, y, name, style, anchor="start"))
                x += widths[index] + 12
        if position == "t":
            area[1] = top + height + 4
        else:
            area[3] = top - 4
        return out

    # -- plain axes ---------------------------------------------------------------------

    def _value_axis_element(self):
        return next((axis for axis in self.axes if axis.find(CX + "valScaling") is not None), None)

    def _category_axis_element(self):
        return next((axis for axis in self.axes if axis.find(CX + "catScaling") is not None), None)

    def _plot_frame(self, area, low, high, code):
        """Room for the axes, the scale, and the plot's frame (x, y, w, h)."""
        axis = self._value_axis_element()
        style = self._style(axis.find(CX + "txPr"), self.base) if axis is not None else self.base
        scaling = axis.find(CX + "valScaling") if axis is not None else None
        fixed_min = _number(scaling.get("min")) if scaling is not None else None
        fixed_max = _number(scaling.get("max")) if scaling is not None else None
        unit = _number(scaling.get("majorUnit")) if scaling is not None else None
        scale = auto_scale(low, high, area[3] - area[1] - 24, 1.32 * style.size, fixed_min, fixed_max, unit)
        hidden = axis is not None and axis.get("hidden") == "1"
        width = 0.0 if hidden else max(self._width(format_number(tick, code), style) for tick in _ticks(*scale))
        left = area[0] + (width + 6 if width else 2)
        top = area[1] + 2
        bottom = area[3] - self.base.size * 1.6
        return (left, top, max(area[2] - left - 2, 10.0), max(bottom - top, 10.0)), scale, style, hidden

    def _draw_value_axis(self, frame, scale, style, hidden, code, right=False) -> None:
        x, y, w, h = frame
        start, stop, step = scale
        span = (stop - start) or 1.0
        for tick in _ticks(start, stop, step):
            at = y + h * (1 - (tick - start) / span)
            if not right:
                self.out.append(f'<path d="M{x:.2f} {at:.2f}H{x + w:.2f}" fill="none" stroke="#{GRID}" stroke-width=".75"/>')
            if not hidden:
                if right:
                    self.labels.append(self._text(x + w + 5, at, format_number(tick, code), style, anchor="start"))
                else:
                    self.labels.append(self._text(x - 5, at, format_number(tick, code), style, anchor="end"))

    def _category_labels(self, frame, names, band, centers=None) -> None:
        x, y, w, h = frame
        line_y = y + h
        style = self.base
        axis = self._category_axis_element()
        if axis is not None:
            style = self._style(axis.find(CX + "txPr"), style)
            if axis.get("hidden") == "1":
                return
        for index, name in enumerate(names):
            middle = centers[index] if centers else x + band * (index + 0.5)
            if self._width(name, style) <= band - 1 or len(name.split()) < 2:
                self.labels.append(self._text(middle, line_y + 5 + style.size * .6, name, style))
                continue
            for number, piece in enumerate(self._wrap(name, style, band - 1)[:2]):
                self.labels.append(self._text(middle, line_y + 5 + style.size * (.6 + 1.2 * number), piece, style))

    # -- waterfall -----------------------------------------------------------------------

    def _waterfall(self, area) -> None:
        series = self.series[0]
        data = self._data_of(series)
        code = data.code
        totals = {int(_number(i.get("val"), -1)) for i in series.iter(CX + "idx")}
        floors, tops, running = [], [], 0.0
        for index, value in enumerate(data.values):
            value = value or 0.0
            if index in totals:
                floors.append(0.0)
                tops.append(value)
                running = value
            else:
                floors.append(running)
                running += value
                tops.append(running)
        low, high = min(floors + tops + [0.0]), max(floors + tops + [0.0])
        frame, scale, style, hidden = self._plot_frame(area, low, high, code)
        self._draw_value_axis(frame, scale, style, hidden, code)
        x, y, w, h = frame
        start, stop, _ = scale
        at = lambda value: y + h * (1 - (value - start) / ((stop - start) or 1.0))
        count = max(len(data.values), 1)
        band = w / count
        axis = self._category_axis_element()
        scaling = axis.find(CX + "catScaling") if axis is not None else None
        gap = _number(scaling.get("gapWidth"), 0.5) if scaling is not None else 0.5
        bar = band / (1 + gap)
        show = self._shows_values(series)
        label_code = self._label_code(series, code)
        for index in range(len(data.values)):
            top, floor = tops[index], floors[index]
            value = data.values[index] or 0.0
            color = self._accent(2) if index in totals else (self._accent(0) if value >= 0 else self._accent(1))
            color = self._point_color(series, index, color)
            left = x + band * index + (band - bar) / 2
            y0, y1 = min(at(top), at(floor)), max(at(top), at(floor))
            self.out.append(f'<rect x="{left:.2f}" y="{y0:.2f}" width="{bar:.2f}" height="{y1 - y0:.2f}" fill="#{color}"/>')
            if index + 1 < len(data.values):
                level = at(top)
                self.out.append(f'<path d="M{left + bar:.2f} {level:.2f}H{left + band:.2f}" fill="none" stroke="#7F7F7F" stroke-width=".75"/>')
            if show:
                above = value >= 0 or index in totals
                self.labels.append(self._text(left + bar / 2, (y0 - self.base.size * .8) if above else (y1 + self.base.size * .8),
                                              format_number(value, label_code), self.base))
        zero = at(max(start, 0.0))
        self.out.append(f'<path d="M{x:.2f} {zero:.2f}H{x + w:.2f}" fill="none" stroke="#BFBFBF" stroke-width=".75"/>')
        self._category_labels(frame, [data.category(i) for i in range(len(data.values))], band)

    # -- funnel --------------------------------------------------------------------------

    def _funnel(self, area) -> None:
        series = self.series[0]
        data = self._data_of(series)
        values = [v or 0.0 for v in data.values]
        if not values:
            return
        style = self.base
        axis = self._category_axis_element()
        if axis is not None:
            style = self._style(axis.find(CX + "txPr"), style)
        names = [data.category(i) for i in range(len(values))]
        room = max((self._width(name, style) for name in names), default=0.0)
        left = area[0] + (room + 6 if room else 0)
        width = max(area[2] - left, 10.0)
        height = max(area[3] - area[1], 10.0)
        band = height / len(values)
        scaling = axis.find(CX + "catScaling") if axis is not None else None
        gap = _number(scaling.get("gapWidth"), 0.06) if scaling is not None else 0.06
        bar = band / (1 + gap)
        largest = max(values) or 1.0
        color = self._series_color(series, 0)
        code = self._label_code(series, data.code)
        show = self._shows_values(series) or series.find(CX + "dataLabels") is None
        for index, value in enumerate(values):
            wide = width * value / largest
            x = left + (width - wide) / 2
            y = area[1] + band * index + (band - bar) / 2
            paint = self._point_color(series, index, color)
            self.out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{wide:.2f}" height="{bar:.2f}" fill="#{paint}"/>')
            middle = y + bar / 2
            self.labels.append(self._text(area[0] + room, middle, names[index], style, anchor="end"))
            if show:
                text = format_number(value, code)
                ink = Style(self.base.size, False, False, "FFFFFF", self.base.family)
                if self._width(text, ink) > wide - 2:
                    ink = self.base
                self.labels.append(self._text(left + width / 2, middle, text, ink))

    # -- treemap --------------------------------------------------------------------------

    def _treemap(self, area) -> None:
        series = self.series[0]
        data = self._data_of(series)
        rows = data.paths()
        if not rows:
            return
        groups: dict = {}
        for names, value in rows:
            groups.setdefault(names[0], []).append((names[-1], value))
        order = sorted(groups, key=lambda name: -sum(v for _, v in groups[name]))
        tops = list(groups)
        frame = (area[0], area[1], area[2] - area[0], area[3] - area[1])
        placed = _squarify([(name, sum(v for _, v in groups[name])) for name in order], frame)
        white = Style(self.base.size, False, False, "FFFFFF", self.base.family)
        banner = Style(self.base.size, True, False, "FFFFFF", self.base.family)
        for name, (x, y, w, h) in placed:
            color = self._accent(tops.index(name))
            leaves = sorted(groups[name], key=lambda item: -item[1])
            single = len(leaves) == 1 and leaves[0][0] == name
            for leaf, (lx, ly, lw, lh) in _squarify(leaves, (x, y, w, h)):
                self.out.append(f'<rect x="{lx:.2f}" y="{ly:.2f}" width="{lw:.2f}" height="{lh:.2f}" fill="#{color}" stroke="#FFFFFF" stroke-width=".75"/>')
                if not single and lw > 16 and lh > white.size * 1.5 and not (lx == x and ly == y):
                    self.labels.append(self._text(lx + 4, ly + white.size, self._fitted(leaf, white, lw - 6), white, anchor="start"))
                elif not single and lx == x and ly == y and lh > white.size * 3.2:
                    self.labels.append(self._text(lx + 4, ly + white.size * 2.3, self._fitted(leaf, white, lw - 6), white, anchor="start"))
            if w > 16 and h > banner.size * 1.4:
                self.labels.append(self._text(x + 4, y + banner.size, self._fitted(name, banner, w - 6), banner, anchor="start"))

    def _fitted(self, text: str, style: Style, limit: float) -> str:
        if self._width(text, style) <= limit:
            return text
        while text and self._width(text + "…", style) > limit:
            text = text[:-1]
        return text + "…" if text else ""

    # -- sunburst --------------------------------------------------------------------------

    def _sunburst(self, area) -> None:
        series = self.series[0]
        data = self._data_of(series)
        rows = data.paths()
        if not rows:
            return
        depth = max(len(names) for names, _ in rows)
        cx, cy = (area[0] + area[2]) / 2, (area[1] + area[3]) / 2
        radius = max(10.0, min(area[2] - area[0], area[3] - area[1]) / 2 - 2)
        hole = radius * 0.18
        band = (radius - hole) / depth
        total = sum(value for _, value in rows) or 1.0
        white = Style(self.base.size, False, False, "FFFFFF", self.base.family)
        tops: list = []
        for names, _ in rows:
            if names[0] not in tops:
                tops.append(names[0])

        def slices(level, members, start):
            spans: dict = {}
            for names, value in members:
                if level < len(names):
                    spans.setdefault(names[level], []).append((names, value))
            angle = start
            for name, inside in spans.items():
                share = sum(v for _, v in inside) / total * 360.0
                color = self._accent(tops.index(inside[0][0][0]))
                paint = color if level == 0 else _shade(color, min(0.45, 0.18 * level))
                inner, outer = hole + band * level, hole + band * (level + 1)
                self.out.append(f'<path d="{_slice(cx, cy, outer, inner, angle, share)}" fill="#{paint}" stroke="#FFFFFF" stroke-width=".75"/>')
                middle = math.radians(angle + share / 2)
                reach = (inner + outer) / 2
                arc = share / 360.0 * 2 * math.pi * reach
                if arc > white.size * 1.4 and self._width(name, white) < band * 0.96:
                    turn = (angle + share / 2) % 360
                    if 90 < turn < 270:          # never upside down
                        turn += 180
                    self.labels.append(self._text(cx + reach * math.cos(middle), cy + reach * math.sin(middle), name, white, rotate=turn % 360))
                slices(level + 1, inside, angle)
                angle += share

        slices(0, rows, -90.0)

    # -- box and whisker ----------------------------------------------------------------------

    def _box_whisker(self, area) -> None:
        groups = []
        names: list = []
        for series in self.series:
            data = self._data_of(series)
            rows: dict = {}
            for index, value in enumerate(data.values):
                if value is None:
                    continue
                name = data.category(index)
                rows.setdefault(name, []).append(value)
                if name not in names:
                    names.append(name)
            groups.append((series, data, rows))
        every = [v for _, _, rows in groups for values in rows.values() for v in values]
        if not every:
            return
        code = groups[0][1].code
        frame, scale, style, hidden = self._plot_frame(area, min(every), max(every), code)
        self._draw_value_axis(frame, scale, style, hidden, code)
        x, y, w, h = frame
        start, stop, _ = scale
        at = lambda value: y + h * (1 - (value - start) / ((stop - start) or 1.0))
        band = w / max(len(names), 1)
        slots = max(len(groups), 1)
        wide = band * 0.68 / slots
        for number, (series, data, rows) in enumerate(groups):
            color = self._series_color(series, number)
            method = next(series.iter(CX + "statistics"), None)
            method = method.get("quartileMethod") if method is not None else "exclusive"
            for position, name in enumerate(names):
                values = rows.get(name)
                if not values:
                    continue
                q1, median, q3 = _quartiles(values, method)
                spread = (q3 - q1) * 1.5
                inside = [v for v in values if q1 - spread <= v <= q3 + spread] or values
                left = x + band * position + band * 0.16 + wide * number
                middle = left + wide / 2
                ink = _shade(color, -0.3)
                self.out.append(f'<path d="M{middle:.2f} {at(max(inside)):.2f}V{at(q3):.2f}M{middle:.2f} {at(q1):.2f}V{at(min(inside)):.2f}'
                                f'M{left + wide * .25:.2f} {at(max(inside)):.2f}H{left + wide * .75:.2f}M{left + wide * .25:.2f} {at(min(inside)):.2f}H{left + wide * .75:.2f}" '
                                f'fill="none" stroke="#{ink}" stroke-width=".75"/>')
                self.out.append(f'<rect x="{left:.2f}" y="{at(q3):.2f}" width="{wide:.2f}" height="{max(at(q1) - at(q3), 0):.2f}" fill="#{color}" stroke="#{ink}" stroke-width=".75"/>')
                self.out.append(f'<path d="M{left:.2f} {at(median):.2f}H{left + wide:.2f}" fill="none" stroke="#{ink}" stroke-width="1"/>')
                mean, r = at(statistics.fmean(values)), min(2.5, wide / 6)
                self.out.append(f'<path d="M{middle - r:.2f} {mean - r:.2f}L{middle + r:.2f} {mean + r:.2f}M{middle + r:.2f} {mean - r:.2f}L{middle - r:.2f} {mean + r:.2f}" fill="none" stroke="#FFFFFF" stroke-width=".9"/>')
                for value in values:
                    if value not in inside:
                        self.out.append(f'<circle cx="{middle:.2f}" cy="{at(value):.2f}" r="{min(2.2, wide / 6):.2f}" fill="none" stroke="#{ink}" stroke-width=".75"/>')
        self.out.append(f'<path d="M{x:.2f} {y + h:.2f}H{x + w:.2f}" fill="none" stroke="#BFBFBF" stroke-width=".75"/>')
        self._category_labels(frame, names, band)

    # -- histogram, Pareto and what stands in for a map ---------------------------------------

    def _columns(self, area) -> None:
        series = self.series[0]
        data = self._data_of(series)
        layout = series.find(CX + "layoutPr")
        binning = layout.find(CX + "binning") if layout is not None else None
        pareto = next((s for s in self.series if s.get("layoutId") == "paretoLine"), None)
        if binning is not None and not data.levels:
            names, values = _histogram([v for v in data.values if v is not None], binning)
        elif layout is not None and layout.find(CX + "aggregation") is not None or pareto is not None or binning is not None:
            totals: dict = {}
            for index, value in enumerate(data.values):
                if value is not None:
                    name = data.category(index)
                    totals[name] = totals.get(name, 0.0) + value
            names, values = list(totals), list(totals.values())
        else:
            names = [data.category(i) for i in range(len(data.values))]
            values = [v or 0.0 for v in data.values]
        if pareto is not None:
            ranked = sorted(zip(names, values), key=lambda pair: -pair[1])
            names, values = [n for n, _ in ranked], [v for _, v in ranked]
        if not values:
            return
        code = data.code if binning is None else "General"
        if pareto is not None:
            area[2] -= self._width("100%", self.base) + 6
        frame, scale, style, hidden = self._plot_frame(area, min(values + [0.0]), max(values + [0.0]), code)
        self._draw_value_axis(frame, scale, style, hidden, code)
        x, y, w, h = frame
        start, stop, _ = scale
        at = lambda value: y + h * (1 - (value - start) / ((stop - start) or 1.0))
        band = w / len(values)
        axis = self._category_axis_element()
        scaling = axis.find(CX + "catScaling") if axis is not None else None
        gap = _number(scaling.get("gapWidth"), 0.0 if binning is not None or pareto is not None else 0.5) if scaling is not None else 0.0
        bar = band / (1 + gap)
        color = self._series_color(series, 0)
        show = self._shows_values(series)
        for index, value in enumerate(values):
            left = x + band * index + (band - bar) / 2
            y0, y1 = sorted((at(value), at(max(start, 0.0))))
            paint = self._point_color(series, index, color)
            self.out.append(f'<rect x="{left:.2f}" y="{y0:.2f}" width="{bar:.2f}" height="{y1 - y0:.2f}" fill="#{paint}" stroke="#FFFFFF" stroke-width=".75"/>')
            if show:
                self.labels.append(self._text(left + bar / 2, y0 - self.base.size * .8, format_number(value, self._label_code(series, code)), self.base))
        self.out.append(f'<path d="M{x:.2f} {y + h:.2f}H{x + w:.2f}" fill="none" stroke="#BFBFBF" stroke-width=".75"/>')
        self._category_labels(frame, names, band)
        if pareto is not None:
            total = sum(values) or 1.0
            running, points = 0.0, []
            for index, value in enumerate(values):
                running += value
                points.append((x + band * (index + 0.5), y + h * (1 - running / total)))
            line_color = self._accent(1)
            self.out.append('<path d="M' + "L".join(f"{a:.2f} {b:.2f}" for a, b in points) + f'" fill="none" stroke="#{line_color}" stroke-width="2.25"/>')
            self._draw_value_axis(frame, (0.0, 1.0, 0.1 if h > 150 else 0.2), self.base, False, "0%", right=True)


def _squarify(items: list, frame: tuple) -> list:
    """Rectangles for (name, size) items, as near square as they can be."""
    x, y, w, h = frame
    items = [item for item in items if item[1] > 0]
    total = sum(size for _, size in items) or 1.0
    scale = w * h / total
    out = []
    pending = [(name, size * scale) for name, size in items]
    while pending:
        short = min(w, h) or 1.0
        row, best = [], float("inf")
        for item in pending:
            trial = row + [item]
            area = sum(a for _, a in trial)
            worst = max(max(short * short * a / (area * area), area * area / (short * short * a)) for _, a in trial)
            if worst > best:
                break
            row, best = trial, worst
        area = sum(a for _, a in row)
        thick = area / short
        at = 0.0
        for name, a in row:
            length = a / thick if thick else 0.0
            if w >= h:
                out.append((name, (x, y + at, thick, length)))
            else:
                out.append((name, (x + at, y, length, thick)))
            at += length
        if w >= h:
            x, w = x + thick, w - thick
        else:
            y, h = y + thick, h - thick
        pending = pending[len(row):]
    return out


def _quartiles(values: list, method: str) -> tuple:
    ordered = sorted(values)
    if len(ordered) < 2:
        return ordered[0], ordered[0], ordered[0]
    q1, median, q3 = statistics.quantiles(ordered, n=4, method="inclusive" if method == "inclusive" else "exclusive")
    return q1, median, q3


def _histogram(values: list, binning) -> tuple:
    if not values:
        return [], []
    low, high = min(values), max(values)
    closed_right = binning.get("intervalClosed") != "l"
    size_el, count_el = binning.find(CX + "binSize"), binning.find(CX + "binCount")
    under, over = _number(binning.get("underflow")), _number(binning.get("overflow"))
    first = under if under is not None else low
    last = over if over is not None else high
    if size_el is not None:
        size = _number(size_el.get("val"), 1.0) or 1.0
    elif count_el is not None:
        size = (last - first) / max(int(_number(count_el.get("val"), 1)), 1) or 1.0
    else:
        deviation = statistics.pstdev(values) if len(values) > 1 else 0.0
        size = 3.5 * deviation / (len(values) ** (1 / 3)) if deviation else (last - first) or 1.0
    count = max(1, math.ceil((last - first) / size - 1e-9))
    edges = [first + size * i for i in range(count + 1)]
    bins = [0.0] * count
    below = above = 0.0
    for value in values:
        if under is not None and (value <= under if closed_right else value < under):
            below += 1
            continue
        if over is not None and (value > over if closed_right else value >= over):
            above += 1
            continue
        position = (value - first) / size
        index = math.ceil(position - 1e-9) - 1 if closed_right else math.floor(position + 1e-9)
        bins[max(0, min(count - 1, index))] += 1
    number = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    names = []
    for index in range(count):
        a, b = edges[index], edges[index + 1]
        opening = "[" if index == 0 or not closed_right else "("
        names.append(f"{opening}{number(a)}, {number(b)}{']' if closed_right else ')'}")
    if under is not None:
        names.insert(0, f"≤ {number(under)}")
        bins.insert(0, below)
    if over is not None:
        names.append(f"> {number(over)}")
        bins.append(above)
    return names, bins


def chartex_html(root, palette: Palette, width: float, height: float, unit, picture=None, absent: bool = True) -> str:
    """A chartex part's XML as an SVG of the given size (points)."""
    return _Extended(root, palette, width, height, picture).svg(unit)
