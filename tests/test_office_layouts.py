"""Excel and PowerPoint files printed the way Excel and PowerPoint print them."""
import io
from datetime import date, datetime, time

import pytest

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl writes the sample workbooks")
pptx = pytest.importorskip("pptx", reason="python-pptx writes the sample decks")
pymupdf = pytest.importorskip("pymupdf", reason="PyMuPDF reads the printed pages")
from openpyxl.chart import BarChart, Reference  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from pptx.chart.data import CategoryChartData  # noqa: E402
from pptx.enum.chart import XL_CHART_TYPE  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402
from pptx.util import Inches  # noqa: E402

from eshab import numfmt, office, pptx_layout, xlsx_layout  # noqa: E402


@pytest.mark.parametrize("value, code, shown", [
    (1234.5, "#,##0", "1,235"), (0.256, "0%", "26%"), (-3.5, "0.0;(0.0)", "(3.5)"), (2500, '"$"#,##0', "$2,500"),
    (1500000, "0.0E+00", "1.5E+06"), (45000, "d/m/yyyy", "15/3/2023"), (45000.5, "h:mm AM/PM", "12:00 PM"),
    (0, '0.00;-0.00;"zero"', "zero"), (1234567, "#,##0,", "1,235"), (1234567, '#,##0.0,,"M"', "1.2M"),
    (1.75, "# ?/?", "1 3/4"), (1.5, "[h]:mm", "36:00"), (datetime(2024, 2, 29, 13, 5, 9), "yyyy-mm-dd hh:mm:ss", "2024-02-29 13:05:09"),
    (date(2024, 1, 5), "dddd, mmmm d", "Friday, January 5"), (time(9, 30), "h:mm AM/PM", "9:30 AM"), ("text", '"Name: "@', "Name: text"),
    (True, "General", "TRUE"), (3, "00000", "00003"), (150, '[>=100]"big";[<0]"neg";0', "big"), (12345, "##0.0E+0", "12.3E+3"),
    (123456789012, "General", "1.23457E+11"), (-1234.5, "#,##0.00 ;(#,##0.00)", "(1,234.50)"),
])
def test_number_formats_show_values_as_excel_does(value, code, shown):
    assert numfmt.format_value(value, code)[0] == shown


def test_a_format_can_colour_its_value():
    assert numfmt.format_value(-12, "[Red]0.0;[Blue]-0.0") == ("-12.0", "0000FF")


def _printed(path, tmp_path):
    browser = office.edge()
    if browser is None:
        pytest.skip("Microsoft Edge is not installed")
    target = tmp_path / (path.stem + ".pdf")
    assert office._edge(browser, path, target)
    return pymupdf.open(target)


# -- PowerPoint -----------------------------------------------------------------------------

def _deck(tmp_path):
    deck = pptx.Presentation()
    title = deck.slides.add_slide(deck.slide_layouts[0])
    title.shapes.title.text = "Quarterly review"
    title.placeholders[1].text = "Subtitle text"
    shapes = deck.slides.add_slide(deck.slide_layouts[5])
    shapes.shapes.title.text = "Shapes"
    box = shapes.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(2), Inches(3), Inches(1.5))
    box.text_frame.text = "Plan"
    table = shapes.shapes.add_table(3, 2, Inches(5), Inches(2), Inches(4), Inches(1.5)).table
    table.cell(0, 0).text = "Region"
    table.cell(1, 0).text = "North"
    chart_slide = deck.slides.add_slide(deck.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["Q1", "Q2"]
    data.add_series("North", (1.0, 2.0))
    chart_slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(6), Inches(4), data)
    arabic = deck.slides.add_slide(deck.slide_layouts[1])
    arabic.shapes.title.text = "نتائج الربع"
    paragraph = arabic.shapes.title.text_frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.RIGHT
    paragraph._p.get_or_add_pPr().set("rtl", "1")
    hidden = deck.slides.add_slide(deck.slide_layouts[5])
    hidden.shapes.title.text = "Hidden slide"
    hidden._element.set("show", "0")
    path = tmp_path / "deck.pptx"
    deck.save(path)
    return path


def test_every_shown_slide_is_a_page_of_the_slides_size(tmp_path):
    with _printed(_deck(tmp_path), tmp_path) as pdf:
        assert pdf.page_count == 4                                    # the hidden slide is left out
        assert pdf[0].rect.width == pytest.approx(720, abs=1) and pdf[0].rect.height == pytest.approx(540, abs=1)
        text = "".join(page.get_text() for page in pdf)
    assert "Quarterly review" in text and "Plan" in text and "North" in text and "Hidden slide" not in text


def test_slide_text_takes_its_shapes_and_tables_colours_and_its_own_alignment(tmp_path):
    html = pptx_layout.document_html(_deck(tmp_path))
    plan = html[html.index(">Plan<") - 400:html.index(">Plan<")]
    assert "color:#FFFFFF" in plan                                   # the shape style's text colour beats the master's
    region = html[html.index(">Region<") - 400:html.index(">Region<")]
    assert "color:#FFFFFF" in region                                 # and so does the table style's header colour
    arabic = html[html.index("نتائج") - 600:html.index("نتائج")]
    assert 'dir="rtl"' in arabic and "text-align:right" in arabic    # PowerPoint's right is the page's right


# -- Excel -----------------------------------------------------------------------------------

def _workbook(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Sales"
    sheet["A1"] = "Region"
    sheet["A1"].font = Font(bold=True)
    sheet["A1"].fill = PatternFill("solid", fgColor="4472C4")
    sheet["B1"] = "Amount"
    sheet["A2"], sheet["B2"] = "North", 1234567890123
    sheet["B2"].number_format = "#,##0.00"
    sheet["A3"] = "Text that runs over the empty cells to its right."
    sheet["D1"] = "A note that wraps in its cell over several lines."
    sheet["D1"].alignment = Alignment(wrap_text=True)
    sheet["B4"], sheet["B5"] = 10, 20
    chart = BarChart()
    chart.add_data(Reference(sheet, min_col=2, min_row=4, max_row=5))
    sheet.add_chart(chart, "A8")
    long = book.create_sheet("Long")
    long["A1"] = "Heading"
    for row in range(2, 160):
        long.cell(row=row, column=1, value=f"Row {row}")
    long.print_title_rows = "1:1"
    long.oddFooter.center.text = "Page &P of &N"
    right = book.create_sheet("عربي")
    right.sheet_view.rightToLeft = True
    right["A1"] = "المنطقة"
    path = tmp_path / "book.xlsx"
    book.save(path)
    return path


def test_sheets_print_as_excel_prints_them(tmp_path):
    with _printed(_workbook(tmp_path), tmp_path) as pdf:
        pages = [page.get_text() for page in pdf]
    sales = pages[0]
    assert "North" in sales and "#####" in sales                      # too wide for its column
    assert "Text that runs over the empty cells to its right." in sales
    long_pages = [text for text in pages if "Row " in text]
    assert len(long_pages) >= 3 and all("Heading" in text for text in long_pages)      # the title row on every page
    total = len(pages)
    assert any(f"Page 2 of {total}" in text for text in long_pages)
    assert "المنطقة" in pages[-1]


def test_a_chart_without_its_own_numbers_reads_them_from_the_sheet(tmp_path):
    html = xlsx_layout.document_html(_workbook(tmp_path))
    assert "<rect" in html and "Sales" in html
    book = xlsx_layout.Book(_workbook(tmp_path))
    try:
        assert book._reference_values("Sales!$B$4:$B$5") == [10, 20]
        assert book._reference_values("'Sales'!$A$1:$B$1") == ["Region", "Amount"]
    finally:
        book.close()


def test_right_to_left_sheets_run_from_the_right(tmp_path):
    html = xlsx_layout.document_html(_workbook(tmp_path))
    assert '"rtl": true' in html


def test_word_files_keep_only_their_own_page_numbers(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for index in range(80):
        document.add_paragraph(f"Line {index} of a document long enough for two pages.")
    source = tmp_path / "plain.docx"
    document.save(source)
    if office.edge() is None:
        pytest.skip("Microsoft Edge is not installed")
    from eshab import documents
    from eshab.engines import Ctx

    target = tmp_path / "plain.pdf"
    ctx = Ctx.__new__(Ctx)
    ctx.status = lambda *_: None
    ctx.progress = lambda *_: None
    assert documents._render_pdf(source, target, ctx)
    with pymupdf.open(target) as pdf:
        assert pdf.page_count >= 2
        assert not any("1 / " in page.get_text() for page in pdf)
        assert pdf.metadata.get("producer", "").startswith("Eshab")
