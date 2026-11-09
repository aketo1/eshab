"""Excel workbooks laid out as print-faithful HTML, each sheet as Excel prints it.

Python reads the workbook into a model of each sheet: its columns (Excel's
widths in pixels of the default font's digits), rows, cells with their
formatted values (number formats, fonts, fills, alignment, wrapping and the
text that runs over into empty neighbours), borders on the grid lines, merged
cells, pictures, charts and shapes where their anchors put them, and the page
setup (paper, margins, scale or fit to pages, print area and titles, page
breaks, page order, centring, gridlines, headers and footers). Then
xlsx_pages.js, inside Edge, measures the rows Excel would fit to their text
and cuts the sheet into pages the way Excel does.
"""
from __future__ import annotations

import colorsys
import html
import json
import logging
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .drawingml import Palette, emu
from .dml_shapes import ShapeRenderer, XDR, local
from .dml_text import TextStyle
from .numfmt import INDEXED, format_value
from .opc import Package, PartView
from .winfonts import font_info, text_width

log = logging.getLogger("eshab")

SCALE = 4
PAGES_SCRIPT = Path(__file__).with_name("xlsx_pages.js")
PAPER = {1: (612, 792), 3: (792, 1224), 5: (612, 1008), 7: (522, 756), 8: (842, 1191), 9: (595.3, 841.9),
         11: (419.5, 595.3), 13: (515.9, 728.5), 14: (612, 936), 66: (1190.6, 1683.8), 70: (297.6, 419.5)}
#: Border styles: (width in points, CSS style), Excel's widths as printed.
BORDERS = {"hair": (0.25, "solid"), "thin": (0.75, "solid"), "dotted": (0.75, "dotted"), "dashed": (0.75, "dashed"),
           "dashDot": (0.75, "dashed"), "dashDotDot": (0.75, "dotted"), "medium": (1.5, "solid"),
           "mediumDashed": (1.5, "dashed"), "mediumDashDot": (1.5, "dashed"), "mediumDashDotDot": (1.5, "dashed"),
           "slantDashDot": (1.5, "dashed"), "thick": (2.25, "solid"), "double": (2.25, "double")}
STRENGTH = {"hair": 1, "dotted": 2, "dashDotDot": 3, "dashDot": 4, "dashed": 5, "thin": 6, "mediumDashDotDot": 7,
            "slantDashDot": 8, "mediumDashDot": 9, "mediumDashed": 10, "medium": 11, "thick": 12, "double": 13}
C_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
THEME_ORDER = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]


def _u(points: float) -> str:
    return f"{points * SCALE:.3f}pt"


def _short_date() -> str | None:
    """Windows' short date as an Excel format: what Excel shows for its default date."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as key:
            pattern = winreg.QueryValueEx(key, "sShortDate")[0]
    except OSError:
        return None
    return pattern.replace("M", "m").replace("tt", "AM/PM") or None


class Book:
    def __init__(self, path: Path):
        import openpyxl

        self.path = Path(path)
        self.workbook = openpyxl.load_workbook(self.path, data_only=True, rich_text=True)
        self.package = Package(self.path)
        from .pptx_layout import Theme

        themes = self.package.by_type("xl/workbook.xml", "/theme")
        self.theme = Theme(self.package.xml(themes[0]) if themes else None)
        self.palette = Palette(self.theme.colors, {}, self.theme.fills, self.theme.lines, self.theme.fonts, self.theme.effects)
        self.date1904 = bool(getattr(self.workbook, "epoch", None) and self.workbook.epoch.year == 1904)
        self.short_date = _short_date()
        base = self.workbook._fonts[0] if getattr(self.workbook, "_fonts", None) else None
        self.font_name = (base.name if base is not None and base.name else None) or "Calibri"
        self.font_size = float(base.sz) if base is not None and base.sz else 11.0
        # Excel measures columns in the default font's widest digit, in whole pixels.
        size_px = self.font_size * 96 / 72
        self.digit = max(1, round(max(text_width(d, self.font_name, size_px) for d in "0123456789")))
        self.line = self._line_px(self.font_name, self.font_size)
        self.sheet_parts = self._sheet_parts()

    def close(self) -> None:
        self.package.close()

    # -- measures ---------------------------------------------------------------------

    @staticmethod
    def _line_px(name: str, size: float) -> float:
        """A text line's height in a cell, in pixels: the font's line rounded up, plus two."""
        metrics = font_info(name)
        return math.ceil(metrics.line * size * 96 / 72 - 1e-6) + 2

    def column_px(self, width) -> int:
        """Excel's column width (characters with padding) in pixels."""
        return int(((256 * width + int(128 / self.digit)) / 256) * self.digit)

    def default_column_px(self, sheet) -> int:
        fmt = sheet.sheet_format
        if fmt.defaultColWidth:
            return self.column_px(float(fmt.defaultColWidth))
        base = float(fmt.baseColWidth or 8)
        return int(math.ceil((base * self.digit + 5) / 8.0) * 8)

    # -- colours -------------------------------------------------------------------------

    def color(self, color, default: str | None = None) -> str | None:
        if color is None:
            return default
        kind = getattr(color, "type", None)
        value = getattr(color, "value", None)
        tint = float(getattr(color, "tint", 0.0) or 0.0)
        base = None
        if kind == "rgb" and isinstance(value, str) and len(value) >= 6:
            base = value[-6:].upper()
            if len(value) == 8 and value[:2] == "00" and value[2:] == "000000":
                base = "000000"
        elif kind == "theme" and isinstance(value, int):
            slot = THEME_ORDER[value] if value < len(THEME_ORDER) else "dk1"
            base = (self.theme.colors.get(slot) or {"lt1": "FFFFFF", "dk1": "000000"}.get(slot, "000000")).upper()
        elif kind == "indexed" and isinstance(value, int):
            if value == 64:
                return default or "000000"
            if value in (65, 81):
                return default
            base = INDEXED[value] if value < len(INDEXED) else None
        elif kind == "auto":
            return default
        if base is None:
            return default
        return _tinted(base, tint) if tint else base

    # -- charts that keep no numbers of their own -------------------------------------------

    def fill_chart_caches(self, root) -> None:
        """Give a chart's series the values its formulas point to, where the file kept none
        (files written by tools other than Excel often leave them out)."""
        for reference in root.iter(C_NS + "numRef", C_NS + "strRef"):
            if reference.find(C_NS + "numCache") is not None or reference.find(C_NS + "strCache") is not None:
                continue
            values = self._reference_values(reference.findtext(C_NS + "f"))
            if values is None:
                continue
            numeric = reference.tag == C_NS + "numRef"
            cache = reference.makeelement(C_NS + ("numCache" if numeric else "strCache"), {})
            if numeric:
                code = cache.makeelement(C_NS + "formatCode", {})
                code.text = "General"
                cache.append(code)
            count = cache.makeelement(C_NS + "ptCount", {"val": str(len(values))})
            cache.append(count)
            for index, value in enumerate(values):
                if value is None or value == "":
                    continue
                if numeric:
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                point = cache.makeelement(C_NS + "pt", {"idx": str(index)})
                shown = point.makeelement(C_NS + "v", {})
                shown.text = (f"{value:.15g}" if numeric else str(value))
                point.append(shown)
                cache.append(point)
            reference.append(cache)

    def _reference_values(self, formula: str | None):
        if not formula:
            return None
        from openpyxl.utils.cell import range_boundaries

        text = formula.strip().lstrip("(").rstrip(")").split(",")[0]
        if "!" not in text:
            return None
        name, area = text.rsplit("!", 1)
        name = name.strip("'").replace("''", "'")
        if name not in self.workbook.sheetnames:
            return None
        sheet = self.workbook[name]
        try:
            min_col, min_row, max_col, max_row = range_boundaries(area.replace("$", ""))
        except ValueError:
            return None
        values = []
        for row in range(min_row, (max_row or min_row) + 1):
            for column in range(min_col, (max_col or min_col) + 1):
                values.append(sheet.cell(row=row, column=column).value)
        return values

    # -- the sheets ----------------------------------------------------------------------

    def _sheet_parts(self) -> dict:
        """Sheet name -> its part, to find drawings and the raw page setup."""
        out = {}
        root = self.package.xml("xl/workbook.xml")
        if root is None:
            return out
        main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        sheets = root.find(main + "sheets")
        for sheet in (sheets if sheets is not None else []):
            target = self.package.target("xl/workbook.xml", sheet.get(r_ns + "id"))
            if target:
                out[sheet.get("name")] = target
        return out


def _tinted(hex_color: str, tint: float) -> str:
    """Excel's tint: lighter or darker in HLS lightness."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _range(text: str | None):
    """(min_col, min_row, max_col, max_row) of the first range in a reference like 'Sheet'!$A$1:$H$20."""
    if not text:
        return None
    from openpyxl.utils.cell import range_boundaries

    first = str(text).split(",")[0]
    first = first.split("!")[-1].replace("$", "")
    try:
        return range_boundaries(first)
    except ValueError:
        return None


class SheetModel:
    def __init__(self, book: Book, sheet, number: int):
        self.book = book
        self.sheet = sheet
        self.number = number
        self.part = book.sheet_parts.get(sheet.title)
        self.styles: dict[str, str] = {}
        self.raw = book.package.xml(self.part) if self.part else None

    # -- the printed range ----------------------------------------------------------------

    def bounds(self):
        sheet = self.sheet
        area = _range(sheet.print_area if sheet.print_area else None)
        if area:
            return area
        rows, cols = [], []
        for (r, c), cell in sheet._cells.items():
            if cell.value is not None and cell.value != "" or self._painted(cell):
                rows.append(r)
                cols.append(c)
        for merged in sheet.merged_cells.ranges:
            rows += [merged.min_row, merged.max_row]
            cols += [merged.min_col, merged.max_col]
        for anchor in self._anchors():
            cols += [anchor[0][0] + 1, anchor[1][0] + 1]
            rows += [anchor[0][2] + 1, anchor[1][2] + 1]
        if not rows:
            return None
        return min(cols), min(rows), max(cols), max(rows)

    @staticmethod
    def _painted(cell) -> bool:
        if not cell.has_style:
            return False
        fill = cell.fill
        if fill is not None and getattr(fill, "fill_type", None) not in (None, "none"):
            return True
        border = cell.border
        return border is not None and any(getattr(getattr(border, side), "style", None)
                                          for side in ("left", "right", "top", "bottom"))

    # -- columns and rows -----------------------------------------------------------------

    def columns(self, first: int, last: int) -> list[tuple[int, float]]:
        """(Excel column, width in points) of the visible columns, read from the sheet's own <cols>."""
        main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        widths, hidden = {}, set()
        holder = self.raw.find(main + "cols") if self.raw is not None else None
        for col in (holder if holder is not None else []):
            try:
                low, high = int(col.get("min")), int(col.get("max"))
            except (TypeError, ValueError):
                continue
            for column in range(low, min(high, last) + 1):
                if col.get("hidden") in ("1", "true"):
                    hidden.add(column)
                if col.get("width") is not None:
                    widths[column] = self.book.column_px(float(col.get("width")))
        default = self.book.default_column_px(self.sheet)
        out = []
        for column in range(first, last + 1):
            if column in hidden:
                continue
            px = widths.get(column, default)
            if px <= 0:
                continue
            out.append((column, px * 0.75))
        return out

    def rows(self, first: int, last: int) -> list[tuple[int, float | None]]:
        """(Excel row, height in points or None to fit) of the visible rows."""
        out = []
        fmt = self.sheet.sheet_format
        default = float(fmt.defaultRowHeight) if fmt.defaultRowHeight else self.book.line * 0.75
        custom_default = bool(getattr(fmt, "customHeight", False))
        for row in range(first, last + 1):
            dimension = self.sheet.row_dimensions.get(row)
            if dimension is not None and dimension.hidden:
                continue
            if dimension is not None and dimension.height is not None:
                out.append((row, float(dimension.height)))
            elif custom_default:
                out.append((row, default))
            else:
                out.append((row, None))
        return out

    # -- cells --------------------------------------------------------------------------------

    def _class(self, css: str) -> str:
        if css not in self.styles:
            self.styles[css] = f"s{self.number}_{len(self.styles)}"
        return self.styles[css]

    def _font_css(self, font) -> tuple[str, float, str]:
        name = (font.name if font is not None and font.name else None) or self.book.font_name
        size = float(font.sz) if font is not None and font.sz else self.book.font_size
        css = [f"font-family:'{name}', '{self.book.font_name}', Arial", f"font-size:{_u(size)}"]
        if font is not None:
            if font.b:
                css.append("font-weight:bold")
            if font.i:
                css.append("font-style:italic")
            lines = []
            if font.u and font.u != "none":
                lines.append("underline")
                if "double" in str(font.u):
                    css.append("text-decoration-style:double")
            if font.strike:
                lines.append("line-through")
            if lines:
                css.append("text-decoration-line:" + " ".join(lines))
            if font.vertAlign in ("superscript", "subscript"):
                css.append("vertical-align:" + ("super" if font.vertAlign == "superscript" else "sub") + ";font-size:" + _u(size * 0.75))
        color = self.book.color(getattr(font, "color", None), "000000") if font is not None else "000000"
        return ";".join(css), size, color

    def _fill_css(self, fill) -> str:
        kind = getattr(fill, "fill_type", None) or getattr(fill, "patternType", None)
        if kind in (None, "none"):
            if getattr(fill, "stop", None):
                stops = [self.book.color(stop.color, "FFFFFF") for stop in fill.stop]
                angle = float(getattr(fill, "degree", 0) or 0)
                return f"background:linear-gradient({angle + 90:.0f}deg, " + ", ".join(f"#{c}" for c in stops) + ")"
            return ""
        front = self.book.color(fill.fgColor, "000000")
        back = self.book.color(fill.bgColor, "FFFFFF")
        if kind == "solid":
            return f"background:#{front}"
        share = {"gray125": 0.125, "gray0625": 0.0625, "lightGray": 0.25, "mediumGray": 0.5, "darkGray": 0.75}.get(kind, 0.3)
        mixed = "".join(f"{round(int(front[i:i + 2], 16) * share + int(back[i:i + 2], 16) * (1 - share)):02X}" for i in (0, 2, 4))
        return f"background:#{mixed}"

    def cells(self, columns, rows):
        """The cells of the printed range, with merged cells and text that runs over."""
        sheet, book = self.sheet, self.book
        col_index = {column: i for i, (column, _) in enumerate(columns)}
        row_index = {row: i for i, (row, _) in enumerate(rows)}
        merged_at, covered = {}, set()
        for merged in sheet.merged_cells.ranges:
            merged_at[(merged.min_row, merged.min_col)] = merged
            for r in range(merged.min_row, merged.max_row + 1):
                for c in range(merged.min_col, merged.max_col + 1):
                    if (r, c) != (merged.min_row, merged.min_col):
                        covered.add((r, c))
        rtl = bool(getattr(sheet.sheet_view, "rightToLeft", False))
        out = []
        filled_rows: dict[int, set] = {}
        for (r, c), cell in sheet._cells.items():
            if cell.value is not None and cell.value != "":
                filled_rows.setdefault(r, set()).add(c)
        for (r, c), cell in sorted(sheet._cells.items()):
            if r not in row_index or c not in col_index or (r, c) in covered:
                continue
            value = cell.value
            has_value = value is not None and value != ""
            if not has_value and not self._painted(cell) and (r, c) not in merged_at:
                continue
            merged = merged_at.get((r, c))
            rs = cs = 1
            if merged is not None:
                rs = sum(1 for rr in range(merged.min_row, merged.max_row + 1) if rr in row_index)
                cs = sum(1 for cc in range(merged.min_col, merged.max_col + 1) if cc in col_index)
                if rs == 0 or cs == 0:
                    continue
            font_css, size, color = self._font_css(cell.font if cell.has_style else None)
            text, number, general, raw = "", False, False, None
            format_color = None
            if has_value:
                text, number, general, raw, format_color, runs = self._value(cell, rtl)
            else:
                runs = None
            align = cell.alignment if cell.has_style else None
            horizontal = getattr(align, "horizontal", None) or "general"
            vertical = getattr(align, "vertical", None) or "bottom"
            wrap = bool(getattr(align, "wrap_text", False)) or horizontal in ("justify", "distributed") or vertical in ("justify", "distributed")
            if horizontal == "general":
                if isinstance(value, bool) or cell.data_type == "e":
                    horizontal = "center"
                elif number:
                    horizontal = "left" if rtl else "right"
                else:
                    horizontal = "right" if rtl else "left"
            if getattr(align, "readingOrder", 0) == 2 and horizontal == "general":
                horizontal = "right"
            rotation = int(getattr(align, "textRotation", 0) or 0)
            indent = float(getattr(align, "indent", 0) or 0) * book.digit * 0.75 * 1.43
            css = [font_css, f"color:#{format_color or color}"]
            fill = self._fill_css(cell.fill) if cell.has_style else ""
            if fill:
                css.append(fill)
            spill = [0, 0]
            if has_value and not wrap and not number and merged is None and rotation == 0 and horizontal in ("left", "right", "center", "centerContinuous", "fill"):
                spill = self._spill(r, c, horizontal, columns, col_index, filled_rows, covered, rtl)
            html_text = runs if runs is not None else html.escape(text)
            out.append({"r": row_index[r], "c": col_index[c], "rs": rs, "cs": cs, "k": self._class(";".join(css)),
                        "t": html_text, "n": int(number), "g": int(general), "v": raw, "w": int(wrap),
                        "ha": horizontal, "va": vertical, "sl": spill[0], "sr": spill[1], "rot": rotation,
                        "ind": round(indent, 2), "sz": size, "lh": round(book._line_px(cell.font.name if cell.has_style and cell.font.name else book.font_name, size) * 0.75, 3)})
        return out

    def _spill(self, r, c, horizontal, columns, col_index, filled_rows, covered, rtl):
        """How many empty neighbours a cell's text may run over, to its left and right."""
        filled = filled_rows.get(r, set())
        order = [column for column, _ in columns]
        at = order.index(c)

        def count(step):
            n, i = 0, at + step
            while 0 <= i < len(order):
                column = order[i]
                if column in filled or (r, column) in covered:
                    break
                n += 1
                i += step
            return n
        right, left = count(1), count(-1)
        if horizontal == "left":
            return [0, right] if not rtl else [right, 0]
        if horizontal == "right":
            return [left, 0] if not rtl else [0, left]
        return [left, right] if not rtl else [right, left]

    def _value(self, cell, rtl: bool):
        """(text, is a number, in General, raw number, format colour, rich text HTML)."""
        value = cell.value
        book = self.book
        code = cell.number_format if cell.has_style else "General"
        runs = None
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)) and type(value).__name__ == "CellRichText":
            parts = []
            for block in value:
                if isinstance(block, str):
                    parts.append(html.escape(block))
                    continue
                font = block.font
                css = []
                if font is not None:
                    if font.b:
                        css.append("font-weight:bold")
                    if font.i:
                        css.append("font-style:italic")
                    if font.sz:
                        css.append(f"font-size:{_u(float(font.sz))}")
                    if font.rFont:
                        css.append(f"font-family:'{font.rFont}', '{book.font_name}', Arial")
                    if font.u:
                        css.append("text-decoration-line:underline")
                    if font.strike:
                        css.append("text-decoration-line:line-through")
                    found = book.color(font.color, None) if font.color is not None else None
                    if found:
                        css.append(f"color:#{found}")
                parts.append(f'<span style="{";".join(css)}">{html.escape(block.text)}</span>')
            runs = "".join(parts)
            return str(value), False, False, None, None, runs
        if cell.data_type == "e":
            return str(value), False, False, None, None, None
        if isinstance(value, str):
            text, color = format_value(value, code, book.date1904, book.short_date)
            return text, False, False, None, color, None
        if isinstance(value, bool):
            return ("TRUE" if value else "FALSE"), False, False, None, None, None
        text, color = format_value(value, code, book.date1904, book.short_date)
        general = (code or "General").strip().lower() == "general"
        raw = None
        try:
            raw = float(value) if not isinstance(value, datetime) and not hasattr(value, "year") else None
        except (TypeError, ValueError):
            raw = None
        return text, True, general, raw, color, None

    # -- borders on the grid's lines ------------------------------------------------------------

    def edges(self, columns, rows, cells_by_pos):
        """Lines between cells: each grid line's border is the stronger of the two cells' sides."""
        sheet, book = self.sheet, self.book
        col_index = {column: i for i, (column, _) in enumerate(columns)}
        row_index = {row: i for i, (row, _) in enumerate(rows)}
        horizontal, vertical = {}, {}

        def put(table, key, side):
            style = getattr(side, "style", None)
            if not style:
                return
            color = book.color(getattr(side, "color", None), "000000")
            old = table.get(key)
            if old is None or STRENGTH.get(style, 0) > STRENGTH.get(old[0], 0):
                table[key] = (style, color)
        merged_at = {}
        for merged in sheet.merged_cells.ranges:
            merged_at[(merged.min_row, merged.min_col)] = merged
        for (r, c), cell in sheet._cells.items():
            if not cell.has_style or r not in row_index or c not in col_index:
                continue
            border = cell.border
            if border is None:
                continue
            ri, ci = row_index[r], col_index[c]
            # a cell's top and left are the lines above and before it; its bottom and right the next ones
            put(horizontal, (ri, ci), border.top)
            put(horizontal, (ri + 1, ci), border.bottom)
            put(vertical, (ri, ci), border.left)
            put(vertical, (ri, ci + 1), border.right)
            merged = merged_at.get((r, c))
            if merged is not None:
                # a merged cell's outline runs all along the merged block
                for cc in range(merged.min_col, merged.max_col + 1):
                    if cc in col_index:
                        put(horizontal, (ri, col_index[cc]), border.top)
                        bottom_row = max((row_index[rr] for rr in range(merged.min_row, merged.max_row + 1) if rr in row_index), default=ri)
                        put(horizontal, (bottom_row + 1, col_index[cc]), border.bottom)
                for rr in range(merged.min_row, merged.max_row + 1):
                    if rr in row_index:
                        put(vertical, (row_index[rr], ci), border.left)
                        right_col = max((col_index[cc] for cc in range(merged.min_col, merged.max_col + 1) if cc in col_index), default=ci)
                        put(vertical, (row_index[rr], right_col + 1), border.right)
        # lines inside a merged block are not drawn
        for merged in sheet.merged_cells.ranges:
            rs = [row_index[rr] for rr in range(merged.min_row, merged.max_row + 1) if rr in row_index]
            cs = [col_index[cc] for cc in range(merged.min_col, merged.max_col + 1) if cc in col_index]
            for ri in rs[1:]:
                for ci in cs:
                    horizontal.pop((ri, ci), None)
            for ri in rs:
                for ci in cs[1:]:
                    vertical.pop((ri, ci), None)
        out = []
        for (ri, ci), (style, color) in horizontal.items():
            width, kind = BORDERS.get(style, (0.75, "solid"))
            out.append({"o": "h", "r": ri, "c": ci, "w": width, "s": kind, "k": color})
        for (ri, ci), (style, color) in vertical.items():
            width, kind = BORDERS.get(style, (0.75, "solid"))
            out.append({"o": "v", "r": ri, "c": ci, "w": width, "s": kind, "k": color})
        return out

    # -- drawings ---------------------------------------------------------------------------------

    def _drawing_part(self):
        if not self.part:
            return None
        drawings = PartView(self.book.package, self.part).by_type("/drawing")
        return drawings[0] if drawings else None

    def _anchors(self):
        """((col, colOff, row, rowOff) from, to) of each object, cells counted from 0."""
        part = self._drawing_part()
        root = part.xml() if part is not None else None
        out = []
        for anchor in (root if root is not None else []):
            kind = local(anchor.tag)
            start = anchor.find(XDR + "from")
            end = anchor.find(XDR + "to")
            if kind == "twoCellAnchor" and start is not None and end is not None:
                out.append((self._marker(start), self._marker(end)))
            elif kind == "oneCellAnchor" and start is not None:
                # only a size: walk the default columns and rows it covers
                begin = self._marker(start)
                extent = anchor.find(XDR + "ext")
                width = emu(extent.get("cx")) if extent is not None else 0.0
                height = emu(extent.get("cy")) if extent is not None else 0.0
                col_pt = self.book.default_column_px(self.sheet) * 0.75
                row_pt = float(self.sheet.sheet_format.defaultRowHeight or self.book.line * 0.75)
                cols = int((begin[1] + width) // max(col_pt, 1.0))
                rows = int((begin[3] + height) // max(row_pt, 1.0))
                out.append((begin, (begin[0] + cols, 0.0, begin[2] + rows, 0.0)))
        return out

    @staticmethod
    def _marker(marker):
        get = lambda name: marker.findtext(XDR + name) or "0"
        return int(get("col")), emu(get("colOff")), int(get("row")), emu(get("rowOff"))

    def objects(self, columns, rows):
        """Pictures, charts and shapes, each with its anchor and its drawing."""
        part = self._drawing_part()
        root = part.xml() if part is not None else None
        if root is None:
            return []
        renderer = ShapeRenderer(part, self.book.palette, _u, lambda node: (TextStyle(), None, self.book.font_size), {}, self.book.font_size)
        for frame in root.iter(XDR + "graphicFrame"):
            chart = next(frame.iter(C_NS + "chart"), None)
            chart_part = part.related(chart.get(R_NS + "id")) if chart is not None else None
            if chart_part is not None and chart_part.xml() is not None:
                self.book.fill_chart_caches(chart_part.xml())
        col_width = {column: width for column, width in columns}
        row_height = {row: (height if height is not None else self.book.line * 0.75) for row, height in rows}
        default_w = self.book.default_column_px(self.sheet) * 0.75
        default_h = self.book.line * 0.75
        out = []
        for anchor in root:
            kind = local(anchor.tag)
            if kind not in ("twoCellAnchor", "oneCellAnchor", "absoluteAnchor"):
                continue
            node = next((child for child in anchor if local(child.tag) in ("sp", "grpSp", "graphicFrame", "cxnSp", "pic")), None)
            if node is None:
                alternate = next((child for child in anchor if local(child.tag) == "AlternateContent"), None)
                if alternate is not None:
                    from .dml_shapes import resolve_alternate

                    node = next(iter(resolve_alternate(alternate)), None)
            if node is None:
                continue
            item = {}
            if kind == "absoluteAnchor":
                position, extent = anchor.find(XDR + "pos"), anchor.find(XDR + "ext")
                x, y = emu(position.get("x")), emu(position.get("y"))
                w, h = emu(extent.get("cx")), emu(extent.get("cy"))
                item["abs"] = [x, y]
            else:
                start = self._marker(anchor.find(XDR + "from"))
                item["from"] = [start[0] + 1, start[1], start[2] + 1, start[3]]
                if kind == "twoCellAnchor":
                    end = self._marker(anchor.find(XDR + "to"))
                    item["to"] = [end[0] + 1, end[1], end[2] + 1, end[3]]
                    w = sum(col_width.get(c, default_w if c not in col_width else 0) for c in range(start[0] + 1, end[0] + 1)) - start[1] + end[1]
                    h = sum(row_height.get(r, default_h) for r in range(start[2] + 1, end[2] + 1)) - start[3] + end[3]
                else:
                    extent = anchor.find(XDR + "ext")
                    w, h = emu(extent.get("cx")), emu(extent.get("cy"))
            w, h = max(w, 1.0), max(h, 1.0)
            item["w"], item["h"] = w, h
            try:
                item["html"] = renderer.node_html(node, box=(0.0, 0.0, w, h))
            except Exception:
                log.exception("could not draw an object on %s", self.sheet.title)
                continue
            if item["html"]:
                out.append(item)
        return out

    # -- page setup -----------------------------------------------------------------------------------

    def setup(self, total_pages_hint: int = 0) -> dict:
        sheet = self.sheet
        raw = self.raw
        main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        setup = sheet.page_setup
        size = int(setup.paperSize) if setup.paperSize else 9
        width, height = PAPER.get(size, PAPER[9])
        if setup.orientation == "landscape":
            width, height = height, width
        has_margins = raw is not None and raw.find(main + "pageMargins") is not None
        margins = sheet.page_margins
        inch = 72.0
        if has_margins:
            m = {"l": margins.left * inch, "r": margins.right * inch, "t": margins.top * inch, "b": margins.bottom * inch,
                 "h": margins.header * inch, "f": margins.footer * inch}
        else:                                   # Excel's Normal margins
            m = {"l": 0.7 * inch, "r": 0.7 * inch, "t": 0.75 * inch, "b": 0.75 * inch, "h": 0.3 * inch, "f": 0.3 * inch}
        fit = bool(getattr(sheet.sheet_properties.pageSetUpPr, "fitToPage", False)) if sheet.sheet_properties.pageSetUpPr else False
        options = sheet.print_options
        titles_rows = _title_span(sheet.print_title_rows)
        titles_cols = _title_span(sheet.print_title_cols, columns=True)
        return {
            "paper": [width, height], "m": m,
            "scale": int(setup.scale) if setup.scale and not fit else 100,
            "fit": [int(setup.fitToWidth if setup.fitToWidth is not None else 1),
                    int(setup.fitToHeight if setup.fitToHeight is not None else 1)] if fit else None,
            "order": "over" if setup.pageOrder == "overThenDown" else "down",
            "center": [bool(options.horizontalCentered), bool(options.verticalCentered)],
            "grid": bool(options.gridLines),
            "rtl": bool(getattr(sheet.sheet_view, "rightToLeft", False)),
            "titleRows": titles_rows, "titleCols": titles_cols,
            "rowBreaks": [b.id for b in sheet.row_breaks.brk] if sheet.row_breaks else [],
            "colBreaks": [b.id for b in sheet.col_breaks.brk] if sheet.col_breaks else [],
            "first": int(setup.firstPageNumber) if setup.firstPageNumber and setup.useFirstPageNumber else None,
        }

    def header_footer(self) -> dict:
        hf = self.sheet.HeaderFooter if hasattr(self.sheet, "HeaderFooter") else None
        out = {}
        if hf is None:
            return out
        for name, part in (("head", hf.oddHeader), ("foot", hf.oddFooter), ("firstHead", hf.firstHeader),
                           ("firstFoot", hf.firstFooter), ("evenHead", hf.evenHeader), ("evenFoot", hf.evenFooter)):
            if part is None:
                continue
            sections = {}
            for side in ("left", "center", "right"):
                section = getattr(part, side, None)
                text = getattr(section, "text", None) if section is not None else None
                if text:
                    sections[side] = _header_html(text, section, self.sheet.title, self.book)
            if sections:
                out[name] = sections
        out["differentFirst"] = bool(getattr(hf, "differentFirst", False))
        out["differentOddEven"] = bool(getattr(hf, "differentOddEven", False))
        return out


def _title_span(text, columns: bool = False):
    if not text:
        return None
    from openpyxl.utils.cell import column_index_from_string

    first = str(text).split(",")[0].split("!")[-1].replace("$", "")
    if ":" not in first:
        return None
    a, b = first.split(":")
    try:
        if columns:
            return [column_index_from_string(a), column_index_from_string(b)]
        return [int(a), int(b)]
    except ValueError:
        return None


def _header_html(text: str, section, sheet_name: str, book: Book) -> str:
    """A header or footer section: its codes as page fields, its fonts as styles."""
    out, index = [], 0
    css = []
    if getattr(section, "font", None):
        css.append(f"font-family:'{section.font}'")
    if getattr(section, "size", None):
        css.append(f"font-size:{_u(float(section.size))}")
    if getattr(section, "color", None):
        css.append(f"color:#{section.color}")
    codes = {"P": '<span class="hf-page"></span>', "N": '<span class="hf-pages"></span>',
             "D": datetime.now().strftime("%d/%m/%Y"), "T": datetime.now().strftime("%H:%M"),
             "F": html.escape(book.path.name), "A": html.escape(sheet_name), "Z": html.escape(str(book.path.parent) + "\\")}
    while index < len(text):
        char = text[index]
        if char == "&" and index + 1 < len(text):
            code = text[index + 1]
            if code == "&":
                out.append("&amp;")
                index += 2
                continue
            if code.upper() in codes:
                out.append(codes[code.upper()])
                index += 2
                continue
            if code == '"':
                end = text.find('"', index + 2)
                index = (end + 1) if end > 0 else len(text)
                continue
            if code.isdigit():
                index += 2
                while index < len(text) and text[index].isdigit():
                    index += 1
                continue
            if code == "K":
                index += 8
                continue
            index += 2
            continue
        out.append(html.escape(char))
        index += 1
    return f'<span style="{";".join(css)}">{"".join(out)}</span>' if css else "".join(out)


BASE_CSS = """
html, body { margin: 0; padding: 0; }
body { -webkit-print-color-adjust: exact; print-color-adjust: exact; text-rendering: geometricPrecision; color: #000; }
.page { position: relative; overflow: hidden; break-after: page; }
.page:last-of-type { break-after: auto; }
.area, .slice, .scaled { position: absolute; }
.slice { overflow: hidden; }
.cell { position: absolute; box-sizing: border-box; overflow: visible; }
.cell > .v { position: absolute; white-space: pre; line-height: var(--lh); }
.cell.wrap > .v { white-space: pre-wrap; overflow-wrap: break-word; }
.edge { position: absolute; box-sizing: border-box; }
.obj { position: absolute; }
.obj > .inner { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.dml { position: absolute; }
.dml-text { position: absolute; display: flex; flex-direction: column; }
.dml-flow { display: flow-root; min-width: 0; }
.dml-text .p { margin: 0; overflow-wrap: break-word; }
.unwrapped .p { white-space: pre; }
.hf { position: absolute; display: flex; white-space: pre; }
.hf > div { flex: 1 1 0; }
.measure { position: absolute; left: -100000px; top: 0; visibility: hidden; }
"""


def document_html(path: Path) -> str:
    book = Book(path)
    try:
        models = []
        styles = []
        for number, sheet in enumerate(book.workbook.worksheets):
            if sheet.sheet_state != "visible":
                continue
            model = SheetModel(book, sheet, number)
            bounds = model.bounds()
            if bounds is None:
                continue
            first_col, first_row, last_col, last_row = bounds
            columns = model.columns(first_col, last_col)
            rows = model.rows(first_row, last_row)
            if not columns or not rows:
                continue
            cells = model.cells(columns, rows)
            data = {
                "name": sheet.title,
                "cols": [round(width, 3) for _, width in columns],
                "colIds": [column for column, _ in columns],
                "rows": [None if height is None else round(height, 3) for _, height in rows],
                "rowIds": [row for row, _ in rows],
                "defaultRow": round(book.line * 0.75, 3),
                "cells": cells,
                "edges": model.edges(columns, rows, None),
                "objects": model.objects(columns, rows),
                "setup": model.setup(),
                "hf": model.header_footer(),
                "pad": 2 * 0.75,
            }
            models.append(data)
            styles.extend(f".{name} {{ {css} }}" for css, name in model.styles.items())
        if not models:
            raise ValueError("nothing to print")
        first = models[0]["setup"]["paper"]
        payload = json.dumps({"k": SCALE, "sheets": models}, ensure_ascii=False).replace("</", "<\\/")
        script = PAGES_SCRIPT.read_text("utf-8")
        title = html.escape(Path(path).stem)
        return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
                f'<meta name="eshab-print-scale" content="{SCALE}">'
                f"<style>@page {{ size: {first[0] * SCALE:.3f}pt {first[1] * SCALE:.3f}pt; margin: 0; }}{BASE_CSS}"
                f"{''.join(styles)}</style></head><body>"
                f'<script type="application/json" id="eshab-book">{payload}</script>'
                f"<script>{script}</script></body></html>")
    finally:
        book.close()
