"""PDF to Word: logical order from glyph positions, Arabic first."""

import unicodedata

import pymupdf
import pytest

from eshab import pdf_docx
from eshab.pdf_docx import Glyph, logical_text


def _visual(*pieces, size=12.0):
    """Glyphs laid out left to right as they appear on the page; a piece of
    " " leaves a word gap, anything else is drawn glyph by glyph."""
    glyphs, x = [], 10.0
    for piece in pieces:
        if piece == " ":
            x += size * 0.3
            continue
        for ch in piece:
            glyphs.append(Glyph(ch, x, x + size * 0.5, size, False, "Arial"))
            x += size * 0.5
    return glyphs


def test_arabic_words_read_right_to_left():
    # "مرحبا بك" is drawn with its last word on the left.
    text, rtl = logical_text(_visual("كب", " ", "ابحرم"))
    assert (text, rtl) == ("مرحبا بك", True)


def test_numbers_and_percent_keep_their_place_in_arabic():
    # Word draws "سعر 15% اليوم" as "اليوم %15 سعر" from left to right.
    text, _ = logical_text(_visual("مويلا", " ", "%15", " ", "رعس"))
    assert text == "سعر 15% اليوم"


def test_english_inside_arabic_and_arabic_inside_english():
    assert logical_text(_visual("ةلمجلا", " ", "English", " ", "تاملك"))[0] == "كلمات English الجملة"
    assert logical_text(_visual("Hello", " ", "ابحرم", " ", "world")) == ("Hello مرحبا world", False)


def test_brackets_mirror_in_arabic():
    # Drawn "(ملف)" appears with the closing glyph on the left.
    assert logical_text(_visual("(فلم)"))[0] == "(ملف)"


def test_a_lam_alef_ligature_reads_lam_first():
    glyphs = [Glyph("ر", 10, 16, 12, False, "Arial"), Glyph("ال", 16, 24, 12, False, "Arial")]
    assert logical_text(glyphs)[0] == "لار"


def _arabic_pdf(path):
    document = pymupdf.open()
    page = document.new_page()
    html = ("<div dir='rtl' style='font-size:14px'>"
            "<p>تقرير الاختبار</p><p>هذه فقرة فيها 2026 و English</p></div>")
    css = "@font-face {font-family: ar; src: url(arial.ttf);} * {font-family: ar;}"
    page.insert_htmlbox(pymupdf.Rect(60, 60, 540, 400), html, css=css,
                        archive=pymupdf.Archive("C:/Windows/Fonts"))
    document.save(path)


def test_a_generated_arabic_pdf_round_trips(tmp_path):
    import docx

    source = tmp_path / "عربي.pdf"
    _arabic_pdf(source)
    if "ت" not in unicodedata.normalize("NFKC", pymupdf.open(source)[0].get_text()):
        pytest.skip("this PyMuPDF build has no Arabic font for HTML boxes")
    target = pdf_docx.convert(source, tmp_path / "عربي.docx")
    paragraphs = [p.text for p in docx.Document(str(target)).paragraphs if p.text.strip()]
    assert "تقرير الاختبار" in paragraphs
    assert "هذه فقرة فيها 2026 و English" in paragraphs
