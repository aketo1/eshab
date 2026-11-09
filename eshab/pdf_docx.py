"""PDF to Word that keeps what matters: reading order, Arabic, images, tables.

The PDF only records where each glyph is drawn. This rebuilds the document
from those positions instead of trusting the order text was written in,
which differs between Word, Chrome (Google Docs) and other producers:

1. every character with its position (PyMuPDF ``rawdict``);
2. fragments on one baseline become one visual line;
3. the line is put back into logical order: visual runs of right-to-left
   and left-to-right text are found (numbers stay left-to-right, spaces and
   punctuation follow their neighbours), the runs are reversed for an Arabic
   line and the Arabic runs are reversed inside; glyphs drawn as one
   ligature (لا) are emitted lam first;
4. lines become paragraphs (alignment, size, bold, bullets, headings);
5. tables are rebuilt cell by cell with the same text order, images are
   placed where they were, and each page ends with a page break.

The result is a flowing document (no floating text boxes), so it opens the
same in Word and in Google Docs.
"""
from __future__ import annotations

import io
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

RTL_RANGES = ((0x0590, 0x08FF), (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF))
MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
ALEFS = set("اأإآ")
BULLETS = set("•●▪■◦○‣–-")


def _is_rtl(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in RTL_RANGES)


def _kind(ch: str) -> str:
    """R, L, N (number) or W (weak/neutral)."""
    if _is_rtl(ch):
        if unicodedata.category(ch) == "Nd":
            return "N"            # Arabic-Indic digits read left to right too
        return "R"
    if ch.isdigit():
        return "N"
    if unicodedata.category(ch)[0] in "LM":
        return "L"
    return "W"


@dataclass
class Glyph:
    text: str          # one or more characters drawn as one glyph
    x0: float
    x1: float
    size: float
    bold: bool
    font: str


@dataclass
class Line:
    glyphs: list[Glyph]
    top: float
    bottom: float
    x0: float
    x1: float
    text: str = ""
    rtl: bool = False
    size: float = 11.0
    bold: bool = False
    font: str = ""


@dataclass
class Block:
    """Something placed on the page, in reading order by ``top``."""
    kind: str                      # paragraph | table | image | break
    top: float
    lines: list[Line] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    rtl: bool = False
    image: bytes = b""
    width: float = 0.0             # points
    align: str = "start"           # start | center | end | justify
    style: str = ""                # heading1 | heading2 | bullet | ""


# -- text order ----------------------------------------------------------------

def _with_spaces(glyphs: list[Glyph]) -> list[Glyph]:
    """Left-to-right glyphs with word spaces put back from the gaps between
    them: the PDF's own space glyphs often sit in odd places."""
    visual = sorted((g for g in glyphs if g.text.strip()), key=lambda g: (g.x0, g.x1))
    spaced: list[Glyph] = []
    for g in visual:
        if spaced:
            last = spaced[-1]
            if g.x0 - last.x1 > 0.15 * max(g.size, last.size):
                spaced.append(Glyph(" ", last.x1, g.x0, g.size, False, g.font))
        spaced.append(g)
    return spaced


def logical_text(glyphs: list[Glyph], rtl: bool | None = None) -> tuple[str, bool]:
    """Logical text of one visual line, and whether the line reads right to left."""
    visual = _with_spaces(glyphs)
    if rtl is None:
        r = sum(1 for g in visual if any(_kind(c) == "R" for c in g.text))
        l_ = sum(1 for g in visual if any(_kind(c) == "L" for c in g.text))
        rtl = r > 0 and r >= l_
    kinds = []
    for g in visual:
        strong = [_kind(c) for c in g.text if _kind(c) in "RL"]
        kinds.append(strong[0] if strong else _kind(g.text[0]) if g.text else "W")
    # Separators inside numbers (1,000 · 3.5 · 12:30) and terminators next to
    # them (15% · $20 · 30°) belong to the number (UBA W4/W5).
    for i, g in enumerate(visual):
        if kinds[i] != "W" or not g.text:
            continue
        prev_n = i > 0 and kinds[i - 1] == "N"
        next_n = i + 1 < len(kinds) and kinds[i + 1] == "N"
        if prev_n and next_n and g.text in ",.:/٫٬":
            kinds[i] = "N"
        # "15%" drawn left to right keeps its sign; drawn "%15" in an Arabic
        # line the sign comes after the number when read, so it stays apart.
        elif g.text in "%٪‰°$€£¥+#" and (prev_n or (next_n and rtl is False)):
            kinds[i] = "N"
    base = "R" if rtl else "L"
    # Numbers behave like R towards their neutral neighbours (UBA N1) in an
    # Arabic line; they still read left to right inside.
    resolved = list(kinds)
    i = 0
    while i < len(kinds):
        if kinds[i] != "W":
            i += 1
            continue
        j = i
        while j < len(kinds) and kinds[j] == "W":
            j += 1
        before = kinds[i - 1] if i > 0 else base
        after = kinds[j] if j < len(kinds) else base
        side = lambda k: "R" if k == "R" or (k == "N" and rtl) else ("L" if k in "LN" else base)
        fill = side(before) if side(before) == side(after) else base
        for k in range(i, j):
            resolved[k] = fill
        i = j
    # Runs of one direction (numbers and Latin both read left to right).
    runs: list[tuple[str, list[Glyph]]] = []
    for g, k in zip(visual, resolved):
        direction = "R" if k == "R" else "L"
        if runs and runs[-1][0] == direction:
            runs[-1][1].append(g)
        else:
            runs.append((direction, [g]))
    if rtl:
        runs.reverse()
    parts = []
    for direction, items in runs:
        if direction == "R":
            text = "".join(_glyph_text(g, reverse=True) for g in reversed(items))
            parts.append(text.translate(MIRROR))
        else:
            parts.append("".join(_glyph_text(g, reverse=False) for g in items))
    text = unicodedata.normalize("NFKC", "".join(parts))
    return " ".join(text.split()), rtl


def _glyph_text(g: Glyph, reverse: bool) -> str:
    text = g.text
    if len(text) == 2 and (set(text) & {"ل"}) and (set(text) & ALEFS):
        return "ل" + next(c for c in text if c in ALEFS)     # lam-alef: lam first
    return text


# -- page analysis --------------------------------------------------------------

def _glyphs_of(page) -> list[tuple[float, float, Glyph]]:
    """(baseline, height, glyph) for every glyph on the page, ligatures merged."""
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
    found = []
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            if abs(line["dir"][1]) > 0.2:
                continue          # rotated text: not part of the flow
            for span in line["spans"]:
                bold = bool(span["flags"] & 16) or "bold" in span["font"].lower()
                height = span["bbox"][3] - span["bbox"][1]
                previous = None
                pending = ""         # zero-width characters waiting for their glyph
                for char in span["chars"]:
                    c = char["c"]
                    if not c.strip():
                        continue    # spaces come back from the gaps (_with_spaces)
                    x0, x1 = char["bbox"][0], char["bbox"][2]
                    if x1 - x0 < 0.05:
                        # One glyph, several characters (لا): the extra one
                        # comes first, with no width, at the edge of the
                        # glyph that draws both.
                        pending += c
                        continue
                    if previous is not None and abs(previous.x0 - x0) < 0.01 and abs(previous.x1 - x1) < 0.01:
                        previous.text += c          # same box twice: a ligature
                        continue
                    previous = Glyph(pending + c, x0, x1, span["size"], bold, span["font"])
                    pending = ""
                    found.append((char["origin"][1], height, previous))
                if pending and previous is not None:
                    previous.text += pending
    return found


def _lines_from(glyphs, skip_rects) -> list[Line]:
    buckets: list[list] = []
    for baseline, height, glyph in sorted(glyphs, key=lambda t: t[0]):
        mid = (glyph.x0 + glyph.x1) / 2.0
        if any(r.x0 - 1 <= mid <= r.x1 + 1 and r.y0 - 1 <= baseline - height / 2 <= r.y1 + 1 for r in skip_rects):
            continue
        tolerance = max(1.5, glyph.size * 0.35)
        if buckets and abs(buckets[-1][0] - baseline) <= tolerance:
            buckets[-1][2].append(glyph)
            buckets[-1][1] = max(buckets[-1][1], height)
        else:
            buckets.append([baseline, height, [glyph]])
    lines = []
    for baseline, height, items in buckets:
        if not any(g.text.strip() for g in items):
            continue
        sizes = [g.size for g in items if g.text.strip()] or [11.0]
        line = Line(items, baseline - height * 0.8, baseline + height * 0.2,
                    min(g.x0 for g in items if g.text.strip()), max(g.x1 for g in items if g.text.strip()))
        line.text, line.rtl = logical_text(items)
        line.size = statistics.median(sizes)
        visible = [g for g in items if g.text.strip()]
        line.bold = sum(g.bold for g in visible) * 2 > len(visible)
        line.font = statistics.mode([g.font for g in visible])
        lines.append(line)
    return lines


def _paragraphs(lines: list[Line], left: float, right: float) -> list[Block]:
    blocks: list[Block] = []
    body = statistics.median([l.size for l in lines]) if lines else 11.0
    width = max(1.0, right - left)
    current: Block | None = None
    for line in lines:
        bullet = line.text[:1] in BULLETS and len(line.text) > 1
        if current is not None:
            last = current.lines[-1]
            gap = line.top - last.bottom
            same_edge = abs((last.x1 if line.rtl else last.x0) - (line.x1 if line.rtl else line.x0)) < 4
            last_full = (last.x1 - last.x0) > width * 0.82
            continues = (not bullet and line.rtl == last.rtl and abs(line.size - last.size) < 0.6
                         and gap < line.size * 0.7 and same_edge and last_full and current.style != "heading1")
            if continues:
                current.lines.append(line)
                continue
        current = Block("paragraph", line.top, [line], rtl=line.rtl)
        if bullet:
            current.style = "bullet"
        elif line.size >= body * 1.45:
            current.style = "heading1"
        elif line.size >= body * 1.18 or (line.bold and line.size >= body * 1.1):
            current.style = "heading2"
        blocks.append(current)
    for block in blocks:
        first = block.lines[0]
        gap_left, gap_right = first.x0 - left, right - first.x1
        if len(block.lines) == 1 and abs(gap_left - gap_right) < 8 and gap_left > 24:
            block.align = "center"
        elif len(block.lines) > 1 and all((l.x1 - l.x0) > width * 0.9 for l in block.lines[:-1]):
            block.align = "justify"
        elif (block.rtl and gap_right > width * 0.4) or (not block.rtl and gap_left > width * 0.4):
            block.align = "end"
    return blocks


def _tables(page, glyphs) -> tuple[list[Block], list]:
    blocks, rects = [], []
    try:
        found = page.find_tables().tables
    except Exception:
        return blocks, rects
    for table in found:
        rect = pymupdf.Rect(table.bbox)
        rects.append(rect)
        grid = []
        rtl_cells = 0
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell is None:
                    cells.append(None)
                    continue
                box = pymupdf.Rect(cell)
                inside = [(b, h, g) for b, h, g in glyphs
                          if box.x0 - 0.5 <= (g.x0 + g.x1) / 2 <= box.x1 + 0.5 and box.y0 - 1 <= b - h / 2 <= box.y1 + 1]
                lines = _lines_from(inside, [])
                text = "\n".join(l.text for l in lines)
                rtl_cells += sum(1 for l in lines if l.rtl) - sum(1 for l in lines if not l.rtl)
                cells.append((box.x0, text))
            grid.append(cells)
        rtl = rtl_cells > 0
        rows = []
        for cells in grid:
            present = [c for c in cells if c is not None]
            present.sort(key=lambda c: -c[0] if rtl else c[0])   # first column is the start side
            rows.append([text for _, text in present])
        blocks.append(Block("table", rect.y0, rows=rows, rtl=rtl))
    return blocks, rects


def _images(document, page) -> tuple[list[Block], list]:
    blocks, rects = [], []
    for info in page.get_images(full=True):
        xref = info[0]
        try:
            placements = page.get_image_rects(xref)
            data = document.extract_image(xref)
        except Exception:
            continue
        for rect in placements:
            if rect.width < 12 or rect.height < 12:
                continue
            image = data.get("image", b"")
            if data.get("ext") not in ("png", "jpeg", "jpg", "bmp", "gif", "tiff"):
                pix = pymupdf.Pixmap(document, xref)
                if pix.alpha or pix.n > 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                image = pix.tobytes("png")
            rects.append(rect)
            blocks.append(Block("image", rect.y0, image=image, width=rect.width,
                                align="center" if abs((rect.x0 + rect.x1) / 2 - page.rect.width / 2) < 30 else "start"))
    # Vector drawings (charts, diagrams): render the area as a picture.
    try:
        drawings = [d["rect"] for d in page.get_drawings() if d["rect"].width > 40 and d["rect"].height > 40]
    except Exception:
        drawings = []
    for rect in _merge(drawings):
        if any(rect.intersects(r) for r in rects) or rect.width * rect.height < 4000:
            continue
        pix = page.get_pixmap(clip=rect, dpi=200)
        rects.append(rect)
        blocks.append(Block("image", rect.y0, image=pix.tobytes("png"), width=rect.width, align="center"))
    return blocks, rects


def _merge(rects):
    merged = []
    for rect in sorted(rects, key=lambda r: (r.y0, r.x0)):
        for i, other in enumerate(merged):
            if rect.intersects(other + (-6, -6, 6, 6)):
                merged[i] = other | rect
                break
        else:
            merged.append(pymupdf.Rect(rect))
    return merged


# -- writing the document -----------------------------------------------------------

def convert(source: Path, target: Path, progress=lambda f: None, cancelled=lambda: False) -> Path:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    pdf = pymupdf.open(source)
    out = docx.Document()
    first = pdf[0].rect if pdf.page_count else pymupdf.Rect(0, 0, 595, 842)
    section = out.sections[0]
    section.page_width, section.page_height = Pt(first.width), Pt(first.height)
    margins = _margins(pdf)
    section.left_margin, section.top_margin, section.right_margin, section.bottom_margin = (Pt(m) for m in margins)
    usable = first.width - margins[0] - margins[2]

    for number, page in enumerate(pdf):
        if cancelled():
            raise RuntimeError("cancelled")
        glyphs = _glyphs_of(page)
        tables, table_rects = _tables(page, glyphs)
        images, image_rects = _images(pdf, page)
        lines = _lines_from(glyphs, table_rects + image_rects)
        if not lines and not tables and not images:
            # A scanned page: keep it as a picture rather than lose it.
            pix = page.get_pixmap(dpi=150)
            images = [Block("image", 0, image=pix.tobytes("png"), width=usable, align="center")]
        blocks = _paragraphs(lines, margins[0], first.width - margins[2]) + tables + images
        blocks.sort(key=lambda b: b.top)
        for block in blocks:
            if block.kind == "paragraph":
                _write_paragraph(out, block, qn, OxmlElement, WD_ALIGN_PARAGRAPH, Pt)
            elif block.kind == "table":
                _write_table(out, block, qn, OxmlElement, Pt)
            elif block.kind == "image":
                paragraph = out.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if block.align == "center" else None
                paragraph.add_run().add_picture(io.BytesIO(block.image), width=Pt(min(block.width, usable)))
        if number < pdf.page_count - 1:
            out.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        progress((number + 1) / max(pdf.page_count, 1))
    out.save(str(target))
    return target


def _margins(pdf) -> tuple[float, float, float, float]:
    boxes = []
    for page in pdf:
        try:
            words = page.get_text("words")
        except Exception:
            continue
        if words:
            boxes.append((min(w[0] for w in words), min(w[1] for w in words),
                          page.rect.width - max(w[2] for w in words), page.rect.height - max(w[3] for w in words)))
    if not boxes:
        return (72.0, 72.0, 72.0, 72.0)
    return tuple(max(18.0, min(108.0, min(b[i] for b in boxes) - 2)) for i in range(4))


def _set_rtl_paragraph(paragraph, qn, OxmlElement):
    ppr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    style = ppr.find(qn("w:pStyle"))
    if style is not None:
        style.addnext(bidi)
    else:
        ppr.insert(0, bidi)


def _add_run(paragraph, text, rtl, size, bold, qn, OxmlElement, Pt):
    run = paragraph.add_run(text)
    run.font.size = Pt(round(size * 2) / 2)
    run.bold = bold
    rpr = run._r.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("ascii", "hAnsi", "cs"):
        fonts.set(qn("w:" + attr), "Arial")
    if bold:
        rpr.append(OxmlElement("w:bCs"))
    size_cs = OxmlElement("w:szCs")
    size_cs.set(qn("w:val"), str(int(round(size * 2))))
    rpr.append(size_cs)
    if rtl:
        rpr.append(OxmlElement("w:rtl"))
    return run


def _write_paragraph(out, block, qn, OxmlElement, WD_ALIGN_PARAGRAPH, Pt):
    text = " ".join(l.text for l in block.lines)
    style = {"heading1": "Heading 1", "heading2": "Heading 2", "bullet": "List Bullet"}.get(block.style)
    if block.style == "bullet":
        text = text[1:].strip()
    paragraph = out.add_paragraph(style=style) if style else out.add_paragraph()
    if block.rtl:
        _set_rtl_paragraph(paragraph, qn, OxmlElement)
    align = {"center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}.get(block.align)
    if block.align == "end":
        align = WD_ALIGN_PARAGRAPH.LEFT if block.rtl else WD_ALIGN_PARAGRAPH.RIGHT
    if align is not None:
        paragraph.alignment = align
    size = block.lines[0].size
    bold = all(l.bold for l in block.lines)
    _add_run(paragraph, text, block.rtl, size, bold, qn, OxmlElement, Pt)
    paragraph.paragraph_format.space_after = Pt(size * 0.4)


def _write_table(out, block, qn, OxmlElement, Pt):
    columns = max((len(r) for r in block.rows), default=0)
    if not columns:
        return
    table = out.add_table(rows=len(block.rows), cols=columns)
    table.style = "Table Grid"
    if block.rtl:
        tblpr = table._tbl.tblPr
        visual = OxmlElement("w:bidiVisual")
        style = tblpr.find(qn("w:tblStyle"))
        (style.addnext if style is not None else tblpr.append)(visual)
    for r, row in enumerate(block.rows):
        for c in range(columns):
            text = row[c] if c < len(row) else ""
            cell = table.cell(r, c)
            paragraph = cell.paragraphs[0]
            rtl = any(_is_rtl(ch) for ch in text)
            if rtl:
                _set_rtl_paragraph(paragraph, qn, OxmlElement)
            _add_run(paragraph, text, rtl, 11, r == 0, qn, OxmlElement, Pt)
    out.add_paragraph()
