"""DrawingML tables (PowerPoint's), with their table styles, as HTML.

A cell takes its fill, borders and text colour from the table style's parts
in Office's order (whole table, banded rows and columns, last and first
column, last and first row), then from its own properties. Styles come from
the file's tableStyles part, or for the ones Office keeps built in (the
default "Medium Style 2" family and the plain ones) from here.
"""
from __future__ import annotations

from lxml import etree

from .drawingml import A, Canvas, emu
from .dml_text import TextRenderer, TextStyle

NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def _medium_two(color: str) -> str:
    line = lambda width: f'<a:ln w="{width}" cmpd="sng"><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:ln>'
    edges = "".join(f"<a:{side}>{line(12700)}</a:{side}>" for side in ("left", "right", "top", "bottom", "insideH", "insideV"))
    strong = f'<a:tcTxStyle b="on"><a:fontRef idx="minor"><a:prstClr val="black"/></a:fontRef><a:schemeClr val="lt1"/></a:tcTxStyle>'
    solid = f'<a:fill><a:solidFill><a:schemeClr val="{color}"/></a:solidFill></a:fill>'
    return (f'<a:tblStyle {NS}><a:wholeTbl><a:tcTxStyle><a:fontRef idx="minor"><a:prstClr val="black"/></a:fontRef>'
            f'<a:schemeClr val="dk1"/></a:tcTxStyle><a:tcStyle><a:tcBdr>{edges}</a:tcBdr><a:fill><a:solidFill>'
            f'<a:schemeClr val="{color}"><a:tint val="20000"/></a:schemeClr></a:solidFill></a:fill></a:tcStyle></a:wholeTbl>'
            f'<a:band1H><a:tcStyle><a:tcBdr/><a:fill><a:solidFill><a:schemeClr val="{color}"><a:tint val="40000"/></a:schemeClr>'
            f'</a:solidFill></a:fill></a:tcStyle></a:band1H><a:band2H><a:tcStyle><a:tcBdr/></a:tcStyle></a:band2H>'
            f'<a:band1V><a:tcStyle><a:tcBdr/><a:fill><a:solidFill><a:schemeClr val="{color}"><a:tint val="40000"/></a:schemeClr>'
            f'</a:solidFill></a:fill></a:tcStyle></a:band1V><a:band2V><a:tcStyle><a:tcBdr/></a:tcStyle></a:band2V>'
            f'<a:lastCol>{strong}<a:tcStyle><a:tcBdr/>{solid}</a:tcStyle></a:lastCol>'
            f'<a:firstCol>{strong}<a:tcStyle><a:tcBdr/>{solid}</a:tcStyle></a:firstCol>'
            f'<a:lastRow>{strong}<a:tcStyle><a:tcBdr><a:top>{line(38100)}</a:top></a:tcBdr>{solid}</a:tcStyle></a:lastRow>'
            f'<a:firstRow>{strong}<a:tcStyle><a:tcBdr><a:bottom>{line(38100)}</a:bottom></a:tcBdr>{solid}</a:tcStyle></a:firstRow>'
            "</a:tblStyle>")


def _plain(grid: bool) -> str:
    edges = ""
    if grid:
        line = '<a:ln w="12700" cmpd="sng"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill></a:ln>'
        edges = "".join(f"<a:{side}>{line}</a:{side}>" for side in ("left", "right", "top", "bottom", "insideH", "insideV"))
    return (f'<a:tblStyle {NS}><a:wholeTbl><a:tcTxStyle><a:fontRef idx="minor"/><a:schemeClr val="tx1"/></a:tcTxStyle>'
            f"<a:tcStyle><a:tcBdr>{edges}</a:tcBdr><a:fill><a:noFill/></a:fill></a:tcStyle></a:wholeTbl></a:tblStyle>")


BUILT_IN = {
    "{073A0DAA-6AF3-43AB-8588-CEC1D06C72B9}": _medium_two("dk1"),
    "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}": _medium_two("accent1"),
    "{21E4AEA4-8DFA-4A89-87EB-49C32662AFE8}": _medium_two("accent2"),
    "{F5AB1C69-6EDB-4FF4-983F-18BD219EF322}": _medium_two("accent3"),
    "{00A15C55-8517-42AA-B614-E9B94910E393}": _medium_two("accent4"),
    "{7DF18680-E054-41AD-8BC1-D1AEF772440D}": _medium_two("accent5"),
    "{93296810-A885-4BE3-A3E7-6D5BEEA58F35}": _medium_two("accent6"),
    "{2D5ABB26-0587-4C30-8999-92F81FD0307C}": _plain(False),
    "{5940675A-B579-460E-94D1-54222C63F5DA}": _plain(True),
}
DEFAULT_STYLE = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"
_PARSED: dict = {}


def style_named(styles: dict, style_id: str | None):
    """The a:tblStyle for an id: the file's own, else Office's built-in one."""
    style_id = style_id or styles.get("__default__") or DEFAULT_STYLE
    if style_id in styles:
        return styles[style_id]
    if style_id not in _PARSED:
        _PARSED[style_id] = etree.fromstring(BUILT_IN.get(style_id, BUILT_IN[DEFAULT_STYLE]))
    return _PARSED[style_id]


def _flag(value) -> bool:
    return value in ("1", "true", "on")


def _parts_for(style, props, row: int, col: int, rows: int, cols: int) -> list:
    """The style parts that apply to one cell, weakest first."""
    get = props.get if props is not None else (lambda *_: None)
    first_row, last_row = _flag(get("firstRow")), _flag(get("lastRow"))
    first_col, last_col = _flag(get("firstCol")), _flag(get("lastCol"))
    names = ["wholeTbl"]
    if _flag(get("bandRow")):
        body_row = row - (1 if first_row else 0)
        if not (first_row and row == 0) and not (last_row and row == rows - 1):
            names.append("band1H" if body_row % 2 == 0 else "band2H")
    if _flag(get("bandCol")):
        body_col = col - (1 if first_col else 0)
        if not (first_col and col == 0) and not (last_col and col == cols - 1):
            names.append("band1V" if body_col % 2 == 0 else "band2V")
    if last_col and col == cols - 1:
        names.append("lastCol")
    if first_col and col == 0:
        names.append("firstCol")
    if last_row and row == rows - 1:
        names.append("lastRow")
    if first_row and row == 0:
        names.append("firstRow")
    corners = {("firstRow", "firstCol"): "nwCell", ("firstRow", "lastCol"): "neCell", ("lastRow", "firstCol"): "swCell",
               ("lastRow", "lastCol"): "seCell"}
    for (a, b), corner in corners.items():
        if a in names and b in names:
            names.append(corner)
    return [style.find(A + name) for name in names if style is not None and style.find(A + name) is not None]


def _edge_line(part, side: str, row: int, col: int, rows: int, cols: int, span_right: int, span_down: int):
    """A part's line for one edge of a cell (outer edges and the inside lines)."""
    borders = part.find(f"{A}tcStyle/{A}tcBdr")
    if borders is None:
        return None
    if side == "left":
        name = "left" if col == 0 else "insideV"
    elif side == "right":
        name = "right" if col + span_right >= cols else "insideV"
    elif side == "top":
        name = "top" if row == 0 else "insideH"
    else:
        name = "bottom" if row + span_down >= rows else "insideH"
    holder = borders.find(A + name)
    if holder is None and part.tag in (A + "firstRow", A + "lastRow", A + "firstCol", A + "lastCol"):
        holder = borders.find(A + side)
    return holder.find(A + "ln") if holder is not None and holder.find(A + "ln") is not None else (holder if holder is not None and holder.find(A + "lnRef") is not None else None)


def table_html(renderer, table, width: float, height: float) -> str:
    unit = renderer.unit
    palette = renderer.palette
    props = table.find(A + "tblPr")
    style_id = props.findtext(A + "tableStyleId") if props is not None else None
    style = style_named(renderer.table_styles, style_id)
    if props is not None and props.find(A + "tableStyleId") is None and props.find(A + "tableStyle") is not None:
        style = props.find(A + "tableStyle")
    grid = [emu(col.get("w")) for col in table.findall(f"{A}tblGrid/{A}gridCol")]
    rows = table.findall(A + "tr")
    count_rows, count_cols = len(rows), len(grid)
    canvas = Canvas(palette, renderer.part.image_uri if renderer.part is not None else None)
    chain = getattr(renderer, "table_text", None) or TextStyle()
    out = [f'<table class="dml-table" style="width:{unit(sum(grid))};table-layout:fixed;border-collapse:collapse">',
           "<colgroup>" + "".join(f'<col style="width:{unit(w)}">' for w in grid) + "</colgroup>"]
    rtl = props is not None and _flag(props.get("rtl"))
    for r, row in enumerate(rows):
        out.append(f'<tr style="height:{unit(emu(row.get("h")))}">')
        c = 0
        for cell in row.findall(A + "tc"):
            span_right = int(cell.get("gridSpan") or 1)
            span_down = int(cell.get("rowSpan") or 1)
            if _flag(cell.get("hMerge")) or _flag(cell.get("vMerge")):
                c += 1
                continue
            parts = _parts_for(style, props, r, c, count_rows, count_cols)
            cell_props = cell.find(A + "tcPr")
            css = []
            fill = None
            bold, color = False, None
            for part in parts:
                text_style = part.find(A + "tcTxStyle")
                if text_style is not None:
                    if text_style.get("b") is not None:
                        bold = text_style.get("b") == "on"
                    found = palette.first_color(text_style)
                    if found:
                        color = found[0]
                    elif text_style.find(A + "fontRef") is not None:
                        inner = palette.first_color(text_style.find(A + "fontRef"))
                        color = inner[0] if inner else color
                holder = part.find(f"{A}tcStyle/{A}fill")
                if holder is not None and len(holder):
                    fill = holder[0]
            own_fill = canvas.fill_of(cell_props)
            if own_fill is not None:
                fill = own_fill
            if fill is not None:
                paint = canvas.paint(fill)
                if 'fill="#' in paint:
                    color_hex = paint.split('fill="#')[1][:6]
                    opacity = paint.split('fill-opacity="')[1][:5] if "fill-opacity" in paint else None
                    css.append(f"background:#{color_hex}" if not opacity else f"background:rgba({int(color_hex[0:2], 16)},{int(color_hex[2:4], 16)},{int(color_hex[4:6], 16)},{opacity})")
            for side, own_name in (("left", "lnL"), ("right", "lnR"), ("top", "lnT"), ("bottom", "lnB")):
                line = None
                for part in parts:
                    found_line = _edge_line(part, side, r, c, count_rows, count_cols, span_right, span_down)
                    if found_line is not None:
                        line = found_line
                own = cell_props.find(A + own_name) if cell_props is not None else None
                if own is not None:
                    line = own
                css.append(f"border-{side}:{_border_css(canvas, line, unit)}")
            get = cell_props.get if cell_props is not None else (lambda *_: None)
            css.append(f"padding:{unit(emu(get('marT'), 3.6))} {unit(emu(get('marR'), 7.2))} "
                       f"{unit(emu(get('marB'), 3.6))} {unit(emu(get('marL'), 7.2))}")
            css.append("vertical-align:" + {"ctr": "middle", "b": "bottom"}.get(get("anchor") or "", "top"))
            body = cell.find(A + "txBody")
            text = TextRenderer(palette, unit, chain, color, 1.0, 0.0, renderer.fields, 18.0,
                                renderer.part.image_uri if renderer.part is not None else None, color is not None)
            inner = text.body_html(body) if body is not None else ""
            if bold:
                inner = f'<div style="font-weight:bold">{inner}</div>'
            spans = (f' colspan="{span_right}"' if span_right > 1 else "") + (f' rowspan="{span_down}"' if span_down > 1 else "")
            out.append(f'<td{spans} style="{";".join(css)}">{inner}</td>')
            c += span_right
        out.append("</tr>")
    out.append("</table>")
    direction = ' dir="rtl"' if rtl else ""
    return f'<div class="dml-table-box"{direction}>' + "".join(out) + "</div>"


def _border_css(canvas, line, unit) -> str:
    if line is None or line.find(A + "noFill") is not None:
        return "none"
    if line.tag == A + "lnRef" or line.find(A + "lnRef") is not None:
        return f"{unit(0.75)} solid #000"
    stroke = canvas.stroke(line)
    if 'stroke="none"' in stroke or 'stroke="#' not in stroke:
        return "none"
    color = stroke.split('stroke="#')[1][:6]
    width = float(stroke.split('stroke-width="')[1].split('"')[0]) if "stroke-width" in stroke else 0.75
    dashed = "dashed" if "stroke-dasharray" in stroke else "solid"
    if line.get("cmpd") == "dbl":
        dashed = "double"
    return f"{unit(width)} {dashed} #{color}"
