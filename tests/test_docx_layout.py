"""Word files laid out the way Word lays them out, for Edge to print."""

import pytest

docx = pytest.importorskip("docx", reason="python-docx is required")
pymupdf = pytest.importorskip("pymupdf", reason="PyMuPDF is required")
from docx.oxml import parse_xml  # noqa: E402
from docx.oxml.ns import nsdecls  # noqa: E402
from docx.shared import Pt  # noqa: E402
from lxml import html as lxml_html  # noqa: E402

from eshab import docx_layout, office, winfonts  # noqa: E402


def _rtl(paragraph):
    paragraph._p.get_or_add_pPr().append(parse_xml(f"<w:bidi {nsdecls('w')}/>"))
    return paragraph


def _page(document, tmp_path):
    path = tmp_path / "sample.docx"
    document.save(path)
    html = docx_layout.document_html(path)
    tree = lxml_html.fromstring(html)
    scale = int(tree.xpath(f'//meta[@name="{docx_layout.SCALE_META}"]/@content')[0])
    return html, tree, scale


def _paragraphs(tree):
    return tree.xpath('//div[@class="section"]/*[@dir]')


def test_arabic_paragraph_runs_right_to_left_in_its_arabic_size(tmp_path):
    document = docx.Document()
    run = _rtl(document.add_paragraph()).add_run("مرحبا بالعالم")
    run.font.size = Pt(14)                                       # Latin size only
    run._r.get_or_add_rPr().append(parse_xml(f'<w:szCs {nsdecls("w")} w:val="32"/>'))   # Arabic size: 16pt

    _, tree, scale = _page(document, tmp_path)

    paragraph = _paragraphs(tree)[0]
    assert paragraph.get("dir") == "rtl"
    style = paragraph.xpath(".//span")[0].get("style")
    assert f"font-size:{16 * scale:.3f}pt" in style            # Word uses the Arabic size for Arabic text


def test_lists_count_and_bullet_like_word(tmp_path):
    document = docx.Document()
    for text in ("أول", "ثاني", "ثالث"):
        document.add_paragraph(text, style="List Number")
    document.add_paragraph("بند", style="List Bullet")

    _, tree, _ = _page(document, tmp_path)

    markers = tree.xpath('//span[contains(@class, "marker")]')
    assert [m.text for m in markers[:3]] == ["1.", "2.", "3."]
    bullet = markers[3]
    assert bullet.text == chr(0xF0B7)                           # Symbol's bullet, drawn in Symbol as Word does
    assert "font-family:'Symbol'" in bullet.get("style")


def test_page_break_keeps_its_mark_and_the_next_page_starts_flush(tmp_path):
    document = docx.Document()
    document.add_paragraph("قبل")
    document.add_page_break()
    document.add_heading("بعد", level=2)

    _, tree, _ = _page(document, tmp_path)

    blocks = tree.xpath('//div[@class="section"]/*')
    kinds = [b.get("class") if b.tag == "div" else b.tag for b in blocks]
    assert kinds == ["p", "p", "page-break", "h2"]               # no empty line on the new page
    assert "margin-top:0.000pt" in blocks[-1].get("style")      # and no space before the heading


def test_a_page_begun_by_page_break_before_has_no_space_before(tmp_path):
    document = docx.Document()
    document.add_paragraph("First page")
    later = document.add_paragraph("Second page")
    later.paragraph_format.page_break_before = True
    later.paragraph_format.space_before = Pt(18)

    _, tree, _ = _page(document, tmp_path)

    second = _paragraphs(tree)[1]
    assert "break-before:page" in second.get("style") and "margin-top:0.000pt" in second.get("style")


def test_arabic_is_measured_in_the_letters_it_joins_into():
    lam_alef = winfonts._joined(chr(0x0644) + chr(0x0627))
    assert lam_alef == [0xFEFB]                                   # one letter, as printed
    word = winfonts._joined(chr(0x0628) + chr(0x0628) + chr(0x0628))
    assert word == [0xFE91, 0xFE92, 0xFE90]                       # first, middle and last forms


def test_a_strings_first_letter_knows_its_ink():
    if "calibri" not in winfonts.font_files():
        pytest.skip("Calibri is not installed")
    assert 0.05 < winfonts.left_bearing("DRAFT", "Calibri") < 0.12     # D starts a little in from its origin


def test_merged_cells_span_rows_and_columns(tmp_path):
    document = docx.Document()
    table = document.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(1, 2).merge(table.cell(2, 2))

    _, tree, _ = _page(document, tmp_path)

    rows = tree.xpath("//table/tbody/tr")
    assert [len(row.xpath("td")) for row in rows] == [2, 3, 2]
    assert rows[0].xpath("td")[0].get("colspan") == "2"
    assert rows[1].xpath("td")[2].get("rowspan") == "2"


def test_header_page_numbers_stay_live(tmp_path):
    document = docx.Document()
    document.add_paragraph("نص")
    header = document.sections[0].header.paragraphs[0]
    header.add_run("صفحة ")
    header._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>'))

    html, _, _ = _page(document, tmp_path)

    assert "<template" in html and "صفحة" in html and 'data-field="PAGE"' in html


def test_digits_in_arabic_runs_use_the_latin_font(tmp_path):
    document = docx.Document()
    run = _rtl(document.add_paragraph()).add_run("عددها 120 ملفا")
    run._r.get_or_add_rPr().append(parse_xml(f"<w:rtl {nsdecls('w')}/>"))
    fonts = run._r.get_or_add_rPr().get_or_add_rFonts()
    for slot, name in (("ascii", "Cambria"), ("hAnsi", "Cambria"), ("cs", "Arial")):
        fonts.set(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{slot}", name)

    _, tree, _ = _page(document, tmp_path)

    outer = _paragraphs(tree)[0].xpath("./span")[0]
    assert "font-family:'Arial'" in outer.get("style")
    digits = outer.xpath("./span")[0]
    assert digits.text == "120" and "font-family:'Cambria'" in digits.get("style")


def test_facing_paragraph_spaces_collapse_to_the_larger(tmp_path):
    document = docx.Document()
    for text, before, after in (("a", 0, 10), ("b", 24, 0)):
        paragraph = document.add_paragraph(text)
        paragraph.paragraph_format.space_before = Pt(before)
        paragraph.paragraph_format.space_after = Pt(after)

    _, tree, scale = _page(document, tmp_path)

    first, second = _paragraphs(tree)
    assert f"margin-bottom:{10 * scale:.3f}pt" in first.get("style")     # CSS margins collapse as Word does
    assert f"margin-top:{24 * scale:.3f}pt" in second.get("style")


FOOTNOTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"


def _with_footnote(document, run, text):
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part

    run._r.append(parse_xml(f'<w:footnoteReference {nsdecls("w")} w:id="1"/>'))
    run.font.superscript = True
    xml = (f'<w:footnotes {nsdecls("w")}><w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p>'
           f'</w:footnote><w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r><w:r><w:t xml:space="preserve"> {text}'
           "</w:t></w:r></w:p></w:footnote></w:footnotes>")
    part = Part(PackURI("/word/footnotes.xml"), FOOTNOTES, xml.encode("utf-8"), document.part.package)
    document.part.relate_to(part, RELATIONSHIP_TYPE.FOOTNOTES)


def test_pages_carry_their_numbers_footnotes_and_flow(tmp_path):
    browser = office.edge()
    if browser is None:
        pytest.skip("Microsoft Edge is not installed")
    document = docx.Document()
    footer = document.sections[0].footer.paragraphs[0]
    footer.add_run("Page ")
    footer._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr=" PAGE "><w:r><w:t>9</w:t></w:r></w:fldSimple>'))
    footer.add_run(" of ")
    footer._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr=" NUMPAGES "><w:r><w:t>9</w:t></w:r></w:fldSimple>'))
    words = "Word lays this line out and fills the page. "
    for index in range(90):
        paragraph = document.add_paragraph(f"{index:03d} " + words * 3)
    _with_footnote(document, paragraph.add_run(), "A note for the last paragraph.")
    source, target = tmp_path / "long.docx", tmp_path / "long.pdf"
    document.save(source)

    assert office._edge(browser, source, target)

    with pymupdf.open(target) as pdf:
        count = pdf.page_count
        assert count >= 3
        texts = [page.get_text() for page in pdf]
        joined = "".join(texts)
        for index in range(90):                                 # nothing lost, nothing repeated
            assert joined.count(f"{index:03d} Word lays") == 1
        for number, text in enumerate(texts, 1):
            assert f"Page {number} of {count}" in " ".join(text.split())
        assert "A note for the last paragraph." not in "".join(texts[:-1])
        last = pdf[count - 1]
        note = last.search_for("A note for the last paragraph.")[0]
        assert note.y1 > last.rect.height - 72 - 20             # at the foot of its page, above the margin
        for page in pdf:                                        # text stays between the margins
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    assert 72 - 1 <= line["bbox"][1] or line["bbox"][3] < 72


def test_page_is_laid_out_larger_than_it_prints(tmp_path):
    document = docx.Document()                                   # Letter, as python-docx makes it
    document.add_paragraph("x")

    html, _, scale = _page(document, tmp_path)

    assert scale == docx_layout.SCALE
    assert f"size: {612 * scale:.3f}pt {792 * scale:.3f}pt" in html


def test_line_height_comes_from_the_font_itself():
    if "arial" not in winfonts.font_files():
        pytest.skip("Arial is not installed")
    metrics = docx_layout.font_info("Arial")
    assert metrics.line == pytest.approx(2355 / 2048, abs=0.0005)   # Word's single line for Arial


def test_shrink_pdf_scales_pages_text_and_links(tmp_path):
    path = tmp_path / "big.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=2448, height=3168)
    page.insert_text((400, 400), "Eshab", fontsize=48)
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(400, 360, 600, 410), "uri": "https://example.com"})
    pdf.save(path)
    pdf.close()

    office.shrink_pdf(path, 0.25)

    with pymupdf.open(path) as shrunk:
        page = shrunk[0]
        assert (page.rect.width, page.rect.height) == pytest.approx((612, 792))
        word = page.get_text("words")[0]
        assert word[4] == "Eshab"
        assert word[0] == pytest.approx(100, abs=1) and word[3] == pytest.approx(102, abs=2)
        link = page.get_links()[0]
        assert link["uri"] == "https://example.com"
        assert tuple(link["from"]) == pytest.approx((100, 90, 150, 102.5), abs=0.5)


def test_edge_prints_an_arabic_document_where_word_does(tmp_path):
    browser = office.edge()
    if browser is None:
        pytest.skip("Microsoft Edge is not installed")
    document = docx.Document()
    for text in ("تقرير تجربة التحويل", "هذا مستند تجريبي فيه أرقام مثل 2026 وكلمات English."):
        run = _rtl(document.add_paragraph()).add_run(text)
        run._r.get_or_add_rPr().append(parse_xml(f"<w:rtl {nsdecls('w')}/>"))
    source, target = tmp_path / "ar.docx", tmp_path / "ar.pdf"
    document.save(source)

    assert office._edge(browser, source, target)

    with pymupdf.open(target) as pdf:
        page = pdf[0]
        assert (page.rect.width, page.rect.height) == pytest.approx((612, 792))   # Letter, shrunk back
        lines = [l for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
        right_edges = {round(l["bbox"][2]) for l in lines}
        assert right_edges <= {521, 522, 523}                     # every line starts at the right margin
        assert "التحويل" in page.get_text()
