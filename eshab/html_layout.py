"""Documents laid out as print-ready HTML, for Edge to turn into PDF.

Word files are read in full by :mod:`eshab.docx_layout`. For the rest,
every paragraph, list item, heading and table cell picks its own direction
(``dir="auto"``), so Arabic lines start on the right and English ones on
the left in the same document; a document that is mostly Arabic is right
to left as a whole (tables included).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import render

_BLOCKS = re.compile(r"<(p|li|h[1-6]|td|th|caption|blockquote|dd|dt)(\s|>)", re.IGNORECASE)
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")
_EXTRA_CSS = """
hr.page-break { display: block; height: 0; border: 0; margin: 0; padding: 0; visibility: hidden;
                break-before: page; page-break-before: always; }
img { max-width: 100%; height: auto; }
html[dir=rtl] body { font-family: Arial, "Segoe UI", Tahoma, sans-serif; }
table { border-collapse: collapse; }
td, th { border: 1px solid #555; padding: 3pt 7pt; vertical-align: top; }
"""


def _mostly_arabic(html: str) -> bool:
    text = re.sub(r"<[^>]+>", " ", html)
    return len(_ARABIC.findall(text)) > len(_LATIN.findall(text))


def _finish(html: str) -> str:
    html = _BLOCKS.sub(lambda m: f'<{m.group(1)} dir="auto"{m.group(2)}', html)
    direction = "rtl" if _mostly_arabic(html) else "ltr"
    html = html.replace("<html>", f'<html dir="{direction}" lang="{"ar" if direction == "rtl" else "en"}">', 1)
    return html.replace("</style>", _EXTRA_CSS + "</style>", 1)


def document_html(path: Path) -> str:
    from . import documents

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":                 # read in full, laid out the way Word lays it out
        from . import docx_layout

        return docx_layout.document_html(path)
    if suffix == ".pptx":                 # each slide as PowerPoint draws it
        from . import pptx_layout

        return pptx_layout.document_html(path)
    if suffix == ".xlsx":                 # each sheet as Excel prints it
        from . import xlsx_layout

        return xlsx_layout.document_html(path)
    options = render.print_options()
    if suffix == ".xlsx":
        html = render.xlsx_to_html(path, path.stem, options)
    elif suffix == ".csv":
        html = render.csv_to_html(path, path.stem, options)
    elif suffix == ".md":
        html = render.markdown_to_html(path.read_text("utf-8", errors="replace"), path.stem, options)
    elif suffix == ".rtf":
        html = render.paragraphs_to_html(documents._read_rtf_text(path), path.stem, options)
    elif suffix == ".odt":
        html = render.paragraphs_to_html(documents._read_odt_text(path), path.stem, options)
    else:
        html = render.paragraphs_to_html(path.read_text("utf-8", errors="replace"), path.stem, options)
    return _finish(html)
