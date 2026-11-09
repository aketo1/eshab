"""What Word draws: theme colours, shapes, charts, SmartArt, and text wrapping around them."""

import pytest

docx = pytest.importorskip("docx", reason="python-docx is required")
pymupdf = pytest.importorskip("pymupdf", reason="PyMuPDF is required")
pptx = pytest.importorskip("pptx", reason="python-pptx writes the sample charts")
from docx.opc.packuri import PackURI  # noqa: E402
from docx.opc.part import Part  # noqa: E402
from docx.oxml import parse_xml  # noqa: E402
from lxml import etree  # noqa: E402
from lxml import html as lxml_html  # noqa: E402
from pptx.chart.data import CategoryChartData, XyChartData  # noqa: E402
from pptx.chart.xmlwriter import ChartXmlWriter  # noqa: E402
from pptx.enum.chart import XL_CHART_TYPE as CHART  # noqa: E402

from eshab import chartex, charts, docx_layout, drawingml, office  # noqa: E402

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex" '
      'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:v="urn:schemas-microsoft-com:vml"')
EMU = 12700
URI = {"wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
       "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
       "chart": "http://schemas.openxmlformats.org/drawingml/2006/chart",
       "chartex": "http://schemas.microsoft.com/office/drawing/2014/chartex",
       "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram"}
SHAPE_STYLE = ('<wps:style><a:lnRef idx="2"><a:schemeClr val="accent1"><a:shade val="50000"/></a:schemeClr></a:lnRef>'
               '<a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef><a:effectRef idx="0"><a:schemeClr val="accent1"/></a:effectRef>'
               '<a:fontRef idx="minor"><a:schemeClr val="lt1"/></a:fontRef></wps:style>')
_counter = iter(range(1, 100000))


def _unit(points):
    return f"{points}pt"


def _palette():
    return drawingml.Palette(fonts={"minorLatin": "Arial", "minorBidi": "Arial"})


def _graphic(kind, inner, width, height, anchor=None):
    number = next(_counter)
    size = f'<wp:extent cx="{int(width * EMU)}" cy="{int(height * EMU)}"/>'
    body = (f'<wp:docPr id="{number}" name="Object {number}"/><wp:cNvGraphicFramePr/><a:graphic>'
            f'<a:graphicData uri="{URI[kind]}">{inner}</a:graphicData></a:graphic>')
    if anchor is None:
        return f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">{size}{body}</wp:inline></w:drawing>'
    return (f'<w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="5" behindDoc="0" locked="0" '
            f'layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="column"><wp:posOffset>{int(anchor[0] * EMU)}</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{int(anchor[1] * EMU)}</wp:posOffset></wp:positionV>{size}{anchor[2]}{body}</wp:anchor></w:drawing>')


def _shape(prst="rect", width=120, height=50, fill="", text=None, body="", style=SHAPE_STYLE, anchor=None):
    words = (f"<wps:txbx><w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:txbxContent></wps:txbx>" if text else "")
    inner = (f'<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width * EMU}" cy="{height * EMU}"/></a:xfrm>'
             f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>{fill}</wps:spPr>{style}{words}<wps:bodyPr {body}/></wps:wsp>')
    return _graphic("wps", inner, width, height, anchor)


def _put(document, *drawings, text=None):
    paragraph = document.add_paragraph()
    if text:
        paragraph.add_run(text)
    for drawing in drawings:
        run = paragraph.add_run()
        run._r.append(parse_xml(f"<w:r {NS}>{drawing}</w:r>")[0])
    return paragraph


def _related(document, name, content_type, rel_type, xml):
    part = Part(PackURI(f"/word/charts/{name}.xml"), content_type, xml.encode("utf-8") if isinstance(xml, str) else xml, document.part.package)
    return document.part.relate_to(part, rel_type)


def _chart_part(document, xml):
    return _related(document, f"chart{next(_counter)}", "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart", xml)


def _html(document, tmp_path):
    path = tmp_path / "drawn.docx"
    document.save(path)
    return docx_layout.document_html(path)


def _printed(document, tmp_path):
    browser = office.edge()
    if browser is None:
        pytest.skip("Microsoft Edge is not installed")
    source, target = tmp_path / "drawn.docx", tmp_path / "drawn.pdf"
    document.save(source)
    assert office._edge(browser, source, target)
    return pymupdf.open(target)


def _ink(page, rect, dpi=96):
    """The set of colours inside a part of the page (pixels, as RGB)."""
    picture = page.get_pixmap(dpi=dpi, clip=pymupdf.Rect(rect))
    return {picture.pixel(x, y) for x in range(picture.width) for y in range(picture.height)}


def _category_data():
    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3"]
    data.add_series("North", (4.0, 2.0, 3.0))
    data.add_series("South", (1.0, 4.0, 2.0))
    return data


# -- colours and outlines ---------------------------------------------------------------

def _scheme(name, *changes):
    inner = "".join(f'<a:{tag} val="{value}"/>' for tag, value in changes)
    return etree.fromstring(f'<a:schemeClr {NS} val="{name}">{inner}</a:schemeClr>')


def test_theme_colours_change_the_way_office_changes_them():
    palette = _palette()
    assert palette.color(_scheme("accent1"))[0] == "4472C4"
    assert palette.color(_scheme("accent1", ("shade", 50000)))[0] == "2F528F"      # the outline Word gives a default shape
    assert palette.color(_scheme("tx1", ("lumMod", 65000), ("lumOff", 35000)))[0] == "595959"
    assert palette.color(_scheme("tx1", ("lumMod", 15000), ("lumOff", 85000)))[0] == "D9D9D9"
    assert palette.color(_scheme("bg1"))[0] == "FFFFFF"
    assert palette.color(_scheme("accent2", ("alpha", 50000)))[1] == pytest.approx(0.5)


@pytest.mark.parametrize("name", ["rect", "roundRect", "ellipse", "triangle", "diamond", "star5", "rightArrow", "chevron", "heart", "cloud", "can",
                                  "cube", "wedgeRectCallout", "wedgeEllipseCallout", "flowChartDecision", "flowChartDocument", "bracePair",
                                  "blockArc", "pie", "arc", "chord", "wave", "line", "bentConnector3", "no such shape"])
def test_every_shape_has_an_outline(name):
    pieces = drawingml.preset_paths(name, 100.0, 60.0, {})
    assert pieces and all(d.startswith("M") for d, _ in pieces)


def test_a_custom_outline_uses_the_shapes_own_units():
    custom = etree.fromstring(f'<a:custGeom {NS}><a:pathLst><a:path w="100" h="100"><a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
                              '<a:lnTo><a:pt x="100" y="50"/></a:lnTo><a:close/></a:path></a:pathLst></a:custGeom>')
    (d, _), = drawingml._custom_geometry(custom, 200.0, 40.0)
    assert d == "M0.000 0.000L200.000 20.000Z"


ALL_PRESETS = """line lineInv triangle rtTriangle rect diamond parallelogram trapezoid nonIsoscelesTrapezoid pentagon hexagon heptagon
octagon decagon dodecagon star4 star5 star6 star7 star8 star10 star12 star16 star24 star32 roundRect round1Rect round2SameRect
round2DiagRect snipRoundRect snip1Rect snip2SameRect snip2DiagRect plaque ellipse teardrop homePlate chevron pieWedge pie blockArc donut
noSmoking rightArrow leftArrow upArrow downArrow stripedRightArrow notchedRightArrow bentUpArrow leftRightArrow upDownArrow leftUpArrow
leftRightUpArrow quadArrow leftArrowCallout rightArrowCallout upArrowCallout downArrowCallout leftRightArrowCallout upDownArrowCallout
quadArrowCallout bentArrow uturnArrow circularArrow leftCircularArrow leftRightCircularArrow curvedRightArrow curvedLeftArrow curvedUpArrow
curvedDownArrow swooshArrow cube can lightningBolt heart sun moon smileyFace irregularSeal1 irregularSeal2 foldedCorner bevel frame
halfFrame corner diagStripe chord arc leftBracket rightBracket leftBrace rightBrace bracketPair bracePair straightConnector1 bentConnector2
bentConnector3 bentConnector4 bentConnector5 curvedConnector2 curvedConnector3 curvedConnector4 curvedConnector5 callout1 callout2 callout3
accentCallout1 accentCallout2 accentCallout3 borderCallout1 borderCallout2 borderCallout3 accentBorderCallout1 accentBorderCallout2
accentBorderCallout3 wedgeRectCallout wedgeRoundRectCallout wedgeEllipseCallout cloudCallout cloud ribbon ribbon2 ellipseRibbon
ellipseRibbon2 leftRightRibbon verticalScroll horizontalScroll wave doubleWave plus flowChartProcess flowChartDecision flowChartInputOutput
flowChartPredefinedProcess flowChartInternalStorage flowChartDocument flowChartMultidocument flowChartTerminator flowChartPreparation
flowChartManualInput flowChartManualOperation flowChartConnector flowChartPunchedCard flowChartPunchedTape flowChartSummingJunction
flowChartOr flowChartCollate flowChartSort flowChartExtract flowChartMerge flowChartOfflineStorage flowChartOnlineStorage
flowChartMagneticTape flowChartMagneticDisk flowChartMagneticDrum flowChartDisplay flowChartDelay flowChartAlternateProcess
flowChartOffpageConnector actionButtonBlank actionButtonHome actionButtonHelp actionButtonInformation actionButtonForwardNext
actionButtonBackPrevious actionButtonEnd actionButtonBeginning actionButtonReturn actionButtonDocument actionButtonSound
actionButtonMovie gear6 gear9 funnel mathPlus mathMinus mathMultiply mathDivide mathEqual mathNotEqual cornerTabs squareTabs plaqueTabs
chartX chartStar chartPlus""".split()


def test_all_187_presets_have_their_own_outline():
    assert len(ALL_PRESETS) == 187
    box = drawingml.preset_paths("rect", 60.0, 60.0, {})
    plain = {"rect", "flowChartProcess", "actionButtonBlank"}         # Word draws these as plain boxes too
    for name in ALL_PRESETS:
        pieces = drawingml.preset_paths(name, 60.0, 60.0, {})
        assert pieces and all(d.startswith("M") for d, _ in pieces), name
        assert (pieces == box) == (name in plain), name


def test_shapes_word_paints_in_parts_fill_and_stroke_apart():
    # A bracket fills its whole inside but strokes only its curve; a cube's faces are shaded.
    assert [mode for _, mode in drawingml.preset_paths("leftBracket", 20.0, 100.0, {})] == ["nostroke", "nofill"]
    assert [mode for _, mode in drawingml.preset_paths("cube", 80.0, 60.0, {})] == ["nostroke", "darkenLess", "lightenLess", "nofill"]
    svg = drawingml.painted_pieces([("M0 0L10 0L10 10Z", "darkenLess")], 'fill="#4472C4"', 'stroke="#000"')
    assert 'fill="#000000" fill-opacity=".2"' in svg


def test_outlines_word_draws_from_its_table_scale_to_the_shape():
    pieces = drawingml.preset_paths("gear6", 120.0, 60.0, {})
    numbers = [float(n) for d, _ in pieces for n in drawingml._PATH_TOKENS.findall(d) if not n.isalpha()]
    xs, ys = numbers[0::2], numbers[1::2]
    assert -1 <= min(xs) and max(xs) <= 121 and -1 <= min(ys) and max(ys) <= 61 and max(xs) > 100


@pytest.mark.parametrize("name, size, area", [
    ("chevron", (200.0, 60.0), (30.0, 0.0, 170.0, 60.0)), ("chevron", (60.0, 60.0), (0.0, 0.0, 60.0, 60.0)),
    ("hexagon", (60.0, 60.0), (10.0, 10.0, 50.0, 50.0)), ("parallelogram", (60.0, 60.0), (11.25, 11.25, 48.75, 48.75)),
    ("rightArrow", (60.0, 60.0), (0.0, 15.0, 45.0, 45.0)), ("cloud", (100.0, 50.0), (14.0, 7.85, 79.4, 40.15)),
])
def test_text_sits_where_word_puts_it_in_a_shape(name, size, area):
    sp_pr = etree.fromstring(f'<wps:spPr {NS}><a:prstGeom prst="{name}"><a:avLst/></a:prstGeom></wps:spPr>')
    assert drawingml.text_area(sp_pr, *size) == pytest.approx(area, abs=0.05)


def _line(attributes="", inner=""):
    return etree.fromstring(f'<a:ln {NS} {attributes}><a:solidFill><a:srgbClr val="000000"/></a:solidFill>{inner}</a:ln>')


def test_arrow_heads_take_word_sizes_from_at_least_a_2pt_line():
    canvas = drawingml.Canvas(_palette())
    canvas.stroke(_line('w="12700"', '<a:tailEnd type="triangle"/>'))
    assert 'markerWidth="6.000" markerHeight="6.000"' in canvas.definitions()          # 3 x 2pt, though the line is 1pt
    canvas = drawingml.Canvas(_palette())
    canvas.stroke(_line('w="38100"', '<a:tailEnd type="triangle" w="lg" len="lg"/>'))
    assert 'markerWidth="15.000" markerHeight="15.000"' in canvas.definitions()        # 5 x 3pt
    # and the line itself stops under the head, so a thick line does not poke through its tip
    assert drawingml._shortened("M0 0L100 0", (0.0, 13.5)) == "M0.000 0.000L86.500 0.000"


def test_compound_lines_are_drawn_as_their_parts():
    sp_pr = etree.fromstring(f'<wps:spPr {NS}><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:ln w="76200" cmpd="dbl">'
                             '<a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln></wps:spPr>')
    svg = drawingml.Canvas(_palette()).shape_paths(sp_pr, None, 90.0, 0.0)
    assert svg.count('stroke-width="2.000"') == 2


def test_patterns_are_word_tiles_printed_as_one_crisp_picture():
    sp_pr = etree.fromstring(f'<wps:spPr {NS}><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:pattFill prst="smCheck">'
                             '<a:fgClr><a:srgbClr val="1F4E79"/></a:fgClr><a:bgClr><a:srgbClr val="DEEAF6"/></a:bgClr></a:pattFill></wps:spPr>')
    svg = drawingml.Canvas(_palette()).shape_paths(sp_pr, None, 44.0, 30.0)
    assert "<image" in svg and "image/png" in svg and "clip-path" in svg
    assert len(drawingml.PATTERNS) == 54 and all(len(rows) == 16 for rows in drawingml.PATTERNS.values())   # every preset


def test_gradients_run_across_the_shape_as_word_runs_them():
    canvas = drawingml.Canvas(_palette())
    stops = ('<a:gsLst><a:gs pos="0"><a:srgbClr val="FF0000"/></a:gs><a:gs pos="100000"><a:srgbClr val="0000FF"/></a:gs></a:gsLst>')
    linear = etree.fromstring(f'<a:gradFill {NS}>{stops}<a:lin ang="0" scaled="0"/></a:gradFill>')
    canvas.paint(linear, size=(90.0, 50.0))
    assert 'x1="0.0000" y1="25.0000" x2="90.0000" y2="25.0000"' in canvas.definitions()
    circle = etree.fromstring(f'<a:gradFill {NS}>{stops}<a:path path="circle"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/>'
                              '</a:path></a:gradFill>')
    canvas.paint(circle, size=(90.0, 50.0))
    assert 'r="51.4782"' in canvas.definitions()                 # out to the corners, round
    square = etree.fromstring(f'<a:gradFill {NS}>{stops}<a:path path="rect"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/>'
                              '</a:path></a:gradFill>')
    assert canvas.paint(square, size=(90.0, 50.0)).startswith('fill="url(#g')
    assert canvas.definitions().count("<linearGradient") == 5   # the linear one, then four sides of the rings


def test_the_themes_third_effect_casts_a_soft_shadow():
    style = etree.fromstring(f'<wps:style {NS}><a:lnRef idx="0"><a:schemeClr val="accent1"/></a:lnRef><a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef>'
                             '<a:effectRef idx="3"><a:schemeClr val="accent1"/></a:effectRef><a:fontRef idx="minor"/></wps:style>')
    sp_pr = etree.fromstring(f'<wps:spPr {NS}><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr>')
    canvas = drawingml.Canvas(_palette())
    svg = canvas.shape_paths(sp_pr, style, 70.0, 40.0)
    assert "feGaussianBlur" in canvas.definitions() and 'fill-opacity="0.630"' in svg


# -- numbers and axes -------------------------------------------------------------------

@pytest.mark.parametrize("value, code, shown", [
    (1234.5, "#,##0", "1,235"), (0.256, "0%", "26%"), (3.14159, "0.00", "3.14"), (-3.5, "0.0;(0.0)", "(3.5)"),
    (2500, '"$"#,##0', "$2,500"), (0.1 + 0.2, "General", "0.3"), (1500000, "0.0E+00", "1.5E+06"),
    (45000, "d/m/yyyy", "15/3/2023"), (45000, "mmm-yy", "Mar-23"), (45000.5, "h:mm AM/PM", "12:00 PM"),
    (7, '0 "items"', "7 items"), (12, "[Red]0.0", "12.0"),
])
def test_number_formats(value, code, shown):
    assert charts.format_number(value, code) == shown


def test_axes_start_at_zero_unless_the_values_sit_close_together():
    assert charts.auto_scale(2.0, 5.0, 150, 9) == (0.0, 6.0, 1.0)
    low, high, _ = charts.auto_scale(95.0, 100.0, 150, 9)
    assert 90 <= low < 95 and 100 < high <= 105
    low, high, _ = charts.auto_scale(-3.0, 5.0, 150, 9)
    assert low < -3 and high > 5
    assert charts.auto_scale(1.0, 5.0, 150, 9, fixed_min=1.0, fixed_max=10.0, unit=3.0) == (1.0, 10.0, 3.0)


# -- charts ---------------------------------------------------------------------------------

def _draw(kind, data=None, width=400.0, height=260.0):
    xml = ChartXmlWriter(kind, data or _category_data()).xml
    return etree.fromstring(charts.chart_html(etree.fromstring(xml.encode("utf-8")), _palette(), width, height, _unit))


SVG = "{http://www.w3.org/2000/svg}"


def _words(svg):
    return [t.text for t in svg.iter(SVG + "text")]


@pytest.mark.parametrize("kind", [CHART.COLUMN_CLUSTERED, CHART.COLUMN_STACKED, CHART.COLUMN_STACKED_100, CHART.BAR_CLUSTERED, CHART.BAR_STACKED,
                                  CHART.LINE, CHART.LINE_MARKERS, CHART.AREA, CHART.AREA_STACKED, CHART.RADAR, CHART.RADAR_FILLED])
def test_chart_kinds_show_their_categories_and_series(kind):
    words = _words(_draw(kind))
    assert {"Q1", "Q2", "Q3"} <= set(words)
    if "<c:legend>" in ChartXmlWriter(kind, _category_data()).xml:
        assert {"North", "South"} <= set(words)


def test_chart_settings_left_out_mean_yes_except_in_word_2007_files():
    xml = ChartXmlWriter(CHART.COLUMN_CLUSTERED, _category_data()).xml
    assert "roundedCorners" not in xml
    root = etree.fromstring(xml.encode("utf-8"))
    assert 'rx="10"' in charts.chart_html(root, _palette(), 400.0, 260.0, _unit)                     # Office rounds the frame
    assert 'rx="10"' not in charts.chart_html(root, _palette(), 400.0, 260.0, _unit, None, False)     # Word 2007 wrote its noes


@pytest.mark.parametrize("kind, order", [(CHART.BAR_CLUSTERED, ["South", "North"]), (CHART.COLUMN_CLUSTERED, ["North", "South"])])
def test_bars_across_list_their_series_from_the_bottom_up(kind, order):
    xml = ChartXmlWriter(kind, _category_data()).xml
    xml = xml.replace("</c:plotArea>", '</c:plotArea><c:legend><c:legendPos val="r"/><c:overlay val="0"/></c:legend>')
    words = _words(etree.fromstring(charts.chart_html(etree.fromstring(xml.encode("utf-8")), _palette(), 400.0, 260.0, _unit)))
    assert [w for w in words if w in ("North", "South")] == order


def test_value_axes_step_as_word_steps_them():
    # The smallest 1, 2 or 5 step whose labels keep their spacing; the top 5% above the highest value.
    assert charts.auto_scale(0.0, 4.0, 150.0, 9.0) == (0.0, 4.5, 0.5)
    assert charts.auto_scale(0.0, 4.0, 40.0, 9.0) == (0.0, 6.0, 2.0)                # too short for five steps of 1


def _painted_rects(svg):
    return [r for r in svg.iter(SVG + "rect") if (r.get("fill") or "none").upper() not in ("NONE", "#FFFFFF")]


def test_each_column_is_as_tall_as_its_value():
    svg = _draw(CHART.COLUMN_CLUSTERED)
    # Columns are the coloured rectangles (the chart and its plot area are white).
    columns = [r for r in _painted_rects(svg) if float(r.get("width")) > 8 and float(r.get("height")) > 0]
    heights = [float(r.get("height")) for r in columns][:6]
    ratio = heights[0] / 4.0
    assert heights == pytest.approx([4 * ratio, 2 * ratio, 3 * ratio, 1 * ratio, 4 * ratio, 2 * ratio], abs=0.2)


def test_100_percent_stacks_all_reach_the_same_height():
    svg = _draw(CHART.COLUMN_STACKED_100)
    rects = [r for r in _painted_rects(svg) if float(r.get("width")) > 8]
    per_category = {}
    for rect in rects[:6]:
        per_category.setdefault(rect.get("x"), []).append(float(rect.get("height")))
    totals = [sum(v) for v in per_category.values()]
    assert len(totals) == 3 and max(totals) - min(totals) < 0.1


def test_a_lone_series_names_the_chart_unless_told_not_to():
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("Revenue", (1.0, 2.0))
    xml = ChartXmlWriter(CHART.COLUMN_CLUSTERED, data).xml
    assert '<c:autoTitleDeleted val="0"/>' in xml
    assert "Revenue" in _words(etree.fromstring(charts.chart_html(etree.fromstring(xml.encode("utf-8")), _palette(), 300.0, 200.0, _unit)))
    xml = xml.replace('<c:autoTitleDeleted val="0"/>', '<c:autoTitleDeleted val="1"/>')
    assert "Revenue" not in _words(etree.fromstring(charts.chart_html(etree.fromstring(xml.encode("utf-8")), _palette(), 300.0, 200.0, _unit)))


def test_pie_slices_fill_the_circle():
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S", (1.0, 1.0, 2.0))
    svg = _draw(CHART.PIE, data)
    slices = [p for p in svg.iter(SVG + "path") if "A" in (p.get("d") or "")]
    assert len(slices) == 3


def test_scatter_points_land_on_their_values():
    data = XyChartData()
    series = data.add_series("Trial")
    for x, y in ((1.0, 1.0), (2.0, 2.0)):
        series.add_data_point(x, y)
    assert "Trial" in _words(_draw(CHART.XY_SCATTER, data))


def _axis_chart(value_axis="", category_axis="", series_extra="", values=(10.0, 1000.0), direction="col"):
    """A small column chart with parts of its axes spelled out."""
    points = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
    names = "".join(f'<c:pt idx="{i}"><c:v>Cat{i}</c:v></c:pt>' for i in range(len(values)))
    return etree.fromstring(
        f'<c:chartSpace {NS}><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:barChart><c:barDir val="{direction}"/><c:grouping val="clustered"/>'
        f'<c:ser><c:idx val="0"/><c:order val="0"/>{series_extra}<c:cat><c:strLit><c:ptCount val="{len(values)}"/>{names}</c:strLit></c:cat>'
        f'<c:val><c:numLit><c:formatCode>General</c:formatCode><c:ptCount val="{len(values)}"/>{points}</c:numLit></c:val></c:ser>'
        '<c:axId val="1"/><c:axId val="2"/></c:barChart>'
        f'<c:catAx><c:axId val="1"/><c:scaling/><c:delete val="0"/><c:axPos val="b"/>{category_axis}<c:crossAx val="2"/></c:catAx>'
        f'<c:valAx><c:axId val="2"/>{value_axis}<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="1"/></c:valAx>'
        "</c:plotArea></c:chart></c:chartSpace>")


def _chart_words(root):
    return _words(etree.fromstring(charts.chart_html(root, _palette(), 400.0, 260.0, _unit)))


def test_a_logarithmic_axis_marks_powers():
    words = _chart_words(_axis_chart('<c:scaling><c:logBase val="10"/></c:scaling>', values=(10.0, 1000.0)))
    assert {"10", "100", "1000"} <= set(words)


def test_a_display_unit_divides_the_axis_and_names_itself():
    root = _axis_chart('<c:scaling/><c:dispUnits><c:builtInUnit val="thousands"/><c:dispUnitsLbl/></c:dispUnits>', values=(2000.0, 6000.0))
    words = _chart_words(root)
    assert "Thousands" in words and "6" in words and "6000" not in words


def test_axis_labels_turn_when_the_file_says_so():
    turned = '<c:txPr><a:bodyPr rot="-2700000" vert="horz"/><a:p/></c:txPr>'
    svg = etree.fromstring(charts.chart_html(_axis_chart(category_axis=turned), _palette(), 400.0, 260.0, _unit))
    label = next(t for t in svg.iter(SVG + "text") if t.text == "Cat0")
    assert "rotate(-45.0" in label.get("transform")


def test_the_files_automatic_angle_is_not_an_angle():
    automatic = '<c:txPr><a:bodyPr rot="-60000000" vert="horz"/><a:p/></c:txPr>'
    svg = etree.fromstring(charts.chart_html(_axis_chart(category_axis=automatic), _palette(), 400.0, 260.0, _unit))
    label = next(t for t in svg.iter(SVG + "text") if t.text == "Cat0")
    assert label.get("transform") is None


def test_bars_growing_leftwards_keep_their_names_on_the_right():
    root = _axis_chart('<c:scaling><c:orientation val="maxMin"/></c:scaling>', direction="bar", values=(10.0, 20.0))
    svg = etree.fromstring(charts.chart_html(root, _palette(), 400.0, 260.0, _unit))
    label = next(t for t in svg.iter(SVG + "text") if t.text == "Cat0")
    rects = [r for r in list(svg.iter(SVG + "rect"))[1:]]
    assert float(label.get("x")) > max(float(r.get("x")) + float(r.get("width")) for r in rects) - 1


def test_a_series_can_carry_a_trendline_and_error_bars():
    extra = ('<c:trendline><c:trendlineType val="linear"/></c:trendline>'
             '<c:errBars><c:errBarType val="both"/><c:errValType val="fixedVal"/><c:val val="1"/></c:errBars>')
    plain = etree.fromstring(charts.chart_html(_axis_chart(values=(2.0, 4.0, 6.0)), _palette(), 400.0, 260.0, _unit))
    marked = etree.fromstring(charts.chart_html(_axis_chart(series_extra=extra, values=(2.0, 4.0, 6.0)), _palette(), 400.0, 260.0, _unit))
    added = len(list(marked.iter(SVG + "path"))) - len(list(plain.iter(SVG + "path")))
    assert added == 1 + 3 * 4       # the trendline, and a stem and a cap each way for three columns


def test_outer_category_names_are_not_lost():
    element = etree.fromstring(f'<c:cat {NS}><c:multiLvlStrRef><c:multiLvlStrCache><c:ptCount val="2"/>'
                               '<c:lvl><c:pt idx="0"><c:v>Jan</c:v></c:pt><c:pt idx="1"><c:v>Feb</c:v></c:pt></c:lvl>'
                               '<c:lvl><c:pt idx="0"><c:v>2026</c:v></c:pt></c:lvl></c:multiLvlStrCache></c:multiLvlStrRef></c:cat>')
    assert charts._strings(element) == ["Jan 2026", "Feb"]


def test_a_trendline_runs_through_its_points():
    points = charts._trend_points("linear", [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)])
    assert points == [(1.0, pytest.approx(2.0)), (3.0, pytest.approx(6.0))]
    assert charts._trend_points("movingAvg", [(1, 1.0), (2, 3.0), (3, 5.0)], period=2) == [(2, 2.0), (3, 4.0)]
    curve = charts._trend_points("poly", [(0.0, 0.0), (1.0, 1.0), (2.0, 4.0), (3.0, 9.0)], order=2)
    assert curve[-1] == (pytest.approx(3.0), pytest.approx(9.0))


def _chartex_xml(layout, levels, values, extra=""):
    cats = "".join(f'<cx:lvl ptCount="{len(level)}">' + "".join(f'<cx:pt idx="{i}">{c}</cx:pt>' for i, c in enumerate(level) if c) + "</cx:lvl>" for level in levels)
    dims = f'<cx:strDim type="cat">{cats}</cx:strDim>' if levels else ""
    points = "".join(f'<cx:pt idx="{i}">{v}</cx:pt>' for i, v in enumerate(values))
    return (f'<cx:chartSpace {NS}><cx:chartData><cx:data id="0">{dims}<cx:numDim type="val"><cx:lvl ptCount="{len(values)}" formatCode="General">{points}</cx:lvl></cx:numDim></cx:data></cx:chartData>'
            f'<cx:chart><cx:title><cx:tx><cx:txData><cx:v>The title</cx:v></cx:txData></cx:tx></cx:title><cx:plotArea><cx:plotAreaRegion><cx:series layoutId="{layout}"><cx:dataLabels/>'
            f'<cx:dataId val="0"/>{extra}</cx:series></cx:plotAreaRegion><cx:axis id="0"><cx:catScaling gapWidth="0.5"/></cx:axis><cx:axis id="1"><cx:valScaling/></cx:axis></cx:plotArea></cx:chart></cx:chartSpace>')


@pytest.mark.parametrize("layout, levels, values, extra, expected", [
    ("waterfall", [["Start", "Up", "Down", "End"]], [10, 5, -3, 12], '<cx:layoutPr><cx:subtotals><cx:idx val="0"/><cx:idx val="3"/></cx:subtotals></cx:layoutPr>', "Up"),
    ("funnel", [["Seen", "Paid"]], [100, 20], "", "Seen"),
    ("treemap", [["Oak", "Rose"], ["Trees", "Flowers"]], [5, 7], "", "Oak"),
    ("sunburst", [["Oak", "Rose"], ["Trees", "Flowers"]], [5, 7], "", "Trees"),
    ("boxWhisker", [["A", "A", "A", "A"]], [1, 2, 3, 4], "", "A"),
    ("clusteredColumn", [], [1, 2, 2, 3, 3, 3], '<cx:layoutPr><cx:binning intervalClosed="r"><cx:binSize val="1"/></cx:binning></cx:layoutPr>', "[1, 2]"),
    ("regionMap", [["Riyadh", "Jeddah"]], [40, 25], "", "Riyadh"),
])
def test_office_2016_chart_kinds_draw(layout, levels, values, extra, expected):
    root = etree.fromstring(_chartex_xml(layout, levels, values, extra))
    svg = etree.fromstring(chartex.chartex_html(root, _palette(), 400.0, 260.0, _unit))
    words = _words(svg)
    assert "The title" in words
    assert expected in words


def test_a_treemap_uses_the_whole_area():
    tiles = chartex._squarify([("a", 6.0), ("b", 6.0), ("c", 4.0), ("d", 3.0), ("e", 2.0), ("f", 2.0), ("g", 1.0)], (0.0, 0.0, 300.0, 200.0))
    assert sum(w * h for _, (_, _, w, h) in tiles) == pytest.approx(60000.0)
    assert all(x >= -1e-6 and y >= -1e-6 and x + w <= 300.001 and y + h <= 200.001 for _, (x, y, w, h) in tiles)


def test_a_histogram_counts_every_value_once():
    root = etree.fromstring(f'<cx:binning {NS} intervalClosed="r"><cx:binSize val="2"/></cx:binning>')
    names, counts = chartex._histogram([1.0, 2.0, 3.0, 4.0, 5.0, 9.0], root)
    assert sum(counts) == 6
    assert names[0] == "[1, 3]"


# -- in a Word file --------------------------------------------------------------------------

def test_a_chart_in_a_document_becomes_a_drawing_of_its_size(tmp_path):
    document = docx.Document()
    rid = _chart_part(document, ChartXmlWriter(CHART.COLUMN_CLUSTERED, _category_data()).xml)
    _put(document, _graphic("chart", f'<c:chart r:id="{rid}"/>', 300, 180))
    html = _html(document, tmp_path)
    tree = lxml_html.fromstring(html)
    frame = tree.xpath('//span[@class="drawn"]')[0]
    assert f"width:{300 * 4}.000pt" in frame.get("style") and f"height:{180 * 4}.000pt" in frame.get("style")
    assert tree.xpath('//span[@class="drawn"]//*[local-name()="svg"]')
    assert 'class="p pictured"' in html              # alone on its line, like a picture


def test_chart_labels_do_not_change_how_the_paragraph_reads(tmp_path):
    document = docx.Document()
    data = CategoryChartData()
    data.categories = ["الربع 1", "الربع 2"]
    data.add_series("المبيعات", (1.0, 2.0))
    rid = _chart_part(document, ChartXmlWriter(CHART.COLUMN_CLUSTERED, data).xml)
    _put(document, _graphic("chart", f'<c:chart r:id="{rid}"/>', 300, 180), text="Plain English text")
    html = _html(document, tmp_path)
    assert "font-kerning:none" in html.split("Plain English text")[0].rsplit("<span", 1)[1]     # still set as Latin
    assert ">الربع 1<" in html                       # digits in the chart stay plain SVG text


def test_shape_text_takes_the_colour_of_its_style_and_sits_in_the_shape(tmp_path):
    document = docx.Document()
    _put(document, _shape(text="Inside", body='anchor="ctr"'))
    html = _html(document, tmp_path)
    tree = lxml_html.fromstring(html)
    text = tree.xpath('//span[contains(@class,"shape-text")]')[0]
    assert "justify-content:center" in text.get("style")
    assert "color:#FFFFFF" in etree.tostring(text, encoding="unicode")


def test_a_paragraph_holding_only_a_shape_has_no_text_line_of_its_own(tmp_path):
    document = docx.Document()
    _put(document, _shape(text="Words in the shape do not make it a text line"))
    assert 'class="p pictured"' in _html(document, tmp_path)


def test_a_broken_chart_keeps_its_place_and_the_rest_of_the_document(tmp_path):
    document = docx.Document()
    rid = _chart_part(document, "<not a chart")
    _put(document, _graphic("chart", f'<c:chart r:id="{rid}"/>', 300, 180))
    document.add_paragraph("Still here")
    html = _html(document, tmp_path)
    assert "Still here" in html and f"height:{180 * 4}.000pt" in html


def test_alternate_content_falls_back_only_when_it_must():
    choice = parse_xml(f'<mc:AlternateContent {NS}><mc:Choice Requires="am3d"><w:t>3D</w:t></mc:Choice><mc:Fallback><w:t>Picture</w:t></mc:Fallback></mc:AlternateContent>')
    assert docx_layout._alternate(choice).tag.endswith("Fallback")
    choice = parse_xml(f'<mc:AlternateContent {NS}><mc:Choice Requires="wps"><w:t>Shape</w:t></mc:Choice><mc:Fallback><w:t>Old</w:t></mc:Fallback></mc:AlternateContent>')
    assert docx_layout._alternate(choice).tag.endswith("Choice")


def test_printed_drawings_keep_their_text_colours_and_gradients(tmp_path):
    document = docx.Document()
    rid = _chart_part(document, ChartXmlWriter(CHART.COLUMN_CLUSTERED, _category_data()).xml)
    gradient = ('<a:gradFill><a:gsLst><a:gs pos="0"><a:srgbClr val="FF0000"/></a:gs><a:gs pos="100000"><a:srgbClr val="0000FF"/></a:gs></a:gsLst>'
                '<a:lin ang="5400000" scaled="0"/></a:gradFill>')
    _put(document, _graphic("chart", f'<c:chart r:id="{rid}"/>', 300, 150))
    _put(document, _shape(fill=gradient, style="", width=200, height=100))
    _put(document, _shape(text="Words in a shape", body='anchor="ctr"'))
    with _printed(document, tmp_path) as pdf:
        assert pdf.page_count == 1
        page = pdf[0]
        text = page.get_text()
        for word in ("Q1", "Words in a shape"):
            assert word in text
        gradient_top = page.rect.height                   # find the gradient by its colours
        picture = page.get_pixmap(dpi=72)
        reds = [y for y in range(picture.height) if picture.pixel(picture.width // 4, y)[0] > 220 and picture.pixel(picture.width // 4, y)[2] < 80]
        blues = [y for y in range(picture.height) if picture.pixel(picture.width // 4, y)[2] > 220 and picture.pixel(picture.width // 4, y)[0] < 80]
        assert reds and blues and min(reds) < min(blues) < gradient_top       # red at the top, blue at the bottom


def _line_ends(page):
    """Each visual line's text and its left and right edges."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                lines.append((round(line["bbox"][1]), line["bbox"][0], line["bbox"][2], text))
    return sorted(lines)


FILLER = "Word flows this paragraph around whatever floats beside it on the page. " * 8


def test_text_wraps_beside_a_floating_shape_and_returns_below_it(tmp_path):
    document = docx.Document()
    float_box = _shape("ellipse", 100, 60, anchor=(332, 0, '<wp:wrapSquare wrapText="bothSides"/>'), text="Float")
    _put(document, float_box, text=FILLER)
    with _printed(document, tmp_path) as pdf:
        lines = [line for line in _line_ends(pdf[0]) if "Float" not in line[3]]
    top = lines[0][0]
    beside = [line for line in lines if line[0] < top + 50]
    below = [line for line in lines if line[0] > top + 66]
    right_edge = 90 + 332            # default template: 90pt left margin
    assert beside and below
    assert all(line[2] <= right_edge + 0.5 for line in beside)
    assert max(line[2] for line in below) > right_edge


def test_top_and_bottom_wrap_keeps_lines_above_and_below_the_object(tmp_path):
    document = docx.Document()
    block = _shape("rect", 300, 60, anchor=(0, 40, "<wp:wrapTopAndBottom/>"), fill='<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>', style="")
    paragraph = _put(document, block, text=FILLER)
    assert paragraph is not None
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        lines = _line_ends(page)
        picture = page.get_pixmap(dpi=72)
        greens = [y for y in range(picture.height) if picture.pixel(100, y)[1] > 200 and picture.pixel(100, y)[0] < 60]
    assert len(greens) > 40
    assert not [line for line in lines if min(greens) - 2 < line[0] < max(greens) - 12]      # no words across it
    assert any(line[0] < min(greens) for line in lines) and any(line[0] > max(greens) for line in lines)


def _boxes(page, color=(0, 255, 0)):
    """The rectangles drawn in one colour on a page."""
    return [d["rect"] for d in page.get_drawings()
            if d.get("fill") and all(abs(a * 255 - b) < 3 for a, b in zip(d["fill"], color))]


def test_text_runs_on_both_sides_of_an_object_in_the_middle(tmp_path):
    document = docx.Document()
    green = '<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>'
    _put(document, _shape("rect", 80, 60, fill=green, style="", anchor=(180, 0, '<wp:wrapSquare wrapText="bothSides"/>')), text=FILLER)
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        box, = _boxes(page)
        words = [w for w in page.get_text("words") if w[1] < box.y1 - 4]
    left = [w for w in words if w[2] <= box.x0]
    right = [w for w in words if w[0] >= box.x1]
    assert left and right and not [w for w in words if w[2] > box.x0 + 1 and w[0] < box.x1 - 1]
    assert {round(w[3]) for w in left} & {round(w[3]) for w in right}          # the same lines, both sides


def test_text_only_on_the_side_the_wrap_asks_for(tmp_path):
    document = docx.Document()
    green = '<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>'
    _put(document, _shape("rect", 80, 60, fill=green, style="", anchor=(180, 0, '<wp:wrapSquare wrapText="left"/>')), text=FILLER)
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        box, = _boxes(page)
        beside = [w for w in page.get_text("words") if w[1] < box.y1 - 4]
    assert beside and all(w[2] <= box.x0 for w in beside)


def test_a_side_too_narrow_for_a_word_sends_the_lines_below(tmp_path):
    document = docx.Document()
    green = '<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>'
    _put(document, _shape("rect", 80, 60, fill=green, style="", anchor=(25, 0, '<wp:wrapSquare wrapText="left"/>')), text=FILLER)
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        box, = _boxes(page)
        words = page.get_text("words")
    assert words and all(w[1] >= box.y1 - 1 for w in words)        # nothing fits in the 16pt on its left


def test_objects_never_push_each_other_about(tmp_path):
    # Two boxes on the left whose wrapping bands overlap: Word leaves each where its anchor says.
    document = docx.Document()
    green = '<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>'
    square = '<wp:wrapSquare wrapText="bothSides"/>'
    _put(document, _shape("rect", 60, 90, fill=green, style="", anchor=(0, 0, square)), text="A short first paragraph.")
    _put(document, _shape("rect", 60, 40, fill=green, style="", anchor=(0, 10, square)), text=FILLER)
    with _printed(document, tmp_path) as pdf:
        boxes = _boxes(pdf[0])
    assert len(boxes) == 2 and all(abs(box.x0 - 90) < 0.5 for box in boxes)


def test_a_float_in_a_right_to_left_paragraph_prints_where_it_stands(tmp_path):
    # Edge used to print it mirrored once another page followed.
    document = docx.Document()
    green = '<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>'
    paragraph = _put(document, _shape("rect", 80, 50, fill=green, style="", anchor=(0, 0, '<wp:wrapSquare wrapText="bothSides"/>')),
                     text="يمر هذا النص العربي بجانب الشكل العائم ويعود إلى العرض الكامل تحته. " * 4)
    paragraph._p.get_or_add_pPr().append(parse_xml(f'<w:bidi {NS}/>'))
    document.add_page_break()
    document.add_paragraph("A second page.")
    with _printed(document, tmp_path) as pdf:
        box, = _boxes(pdf[0])
    assert box.x0 == pytest.approx(90, abs=0.5)


def test_a_tight_wrap_follows_the_polygon_the_file_keeps(tmp_path):
    document = docx.Document()
    polygon = ('<wp:wrapTight wrapText="bothSides"><wp:wrapPolygon edited="0"><wp:start x="0" y="0"/><wp:lineTo x="0" y="21600"/>'
               '<wp:lineTo x="21600" y="21600"/><wp:lineTo x="21600" y="0"/><wp:lineTo x="0" y="0"/></wp:wrapPolygon></wp:wrapTight>')
    _put(document, _shape("ellipse", 100, 60, anchor=(0, 0, polygon)), text=FILLER)
    html = _html(document, tmp_path)
    assert 'data-wrap="wrapTight"' in html and 'data-poly="0.00,0.00 0.00,240.00 400.00,240.00 400.00,0.00' in html


def test_a_line_shorter_than_the_font_keeps_the_fonts_line(tmp_path):
    # A paragraph holding only a flat line shape is as tall as a line of its font, the shape on the baseline.
    document = docx.Document()
    line = ('<wps:wsp><wps:cNvCnPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="6096000" cy="0"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
            '<a:ln w="19050"><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln></wps:spPr><wps:bodyPr/></wps:wsp>')
    for _ in range(3):
        _put(document, _graphic("wps", line, 480, 0))
    html = _html(document, tmp_path)
    assert html.count('class="p pictured low"') == 3 and "--below:" in html


def test_an_empty_paragraph_with_only_a_floating_shape_keeps_its_line(tmp_path):
    document = docx.Document()
    document.add_paragraph("First line")
    _put(document, _shape("rect", 80, 20, anchor=(300, 0, "<wp:wrapNone/>")))
    document.add_paragraph("Third line")
    with _printed(document, tmp_path) as pdf:
        lines = _line_ends(pdf[0])
    gap = lines[1][0] - lines[0][0]
    assert gap > 30         # one spaced line more than two neighbours would be


def test_smartart_shows_the_shapes_the_file_keeps(tmp_path):
    document = docx.Document()
    shape = ('<dsp:sp modelId="{1}"><dsp:nvSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvSpPr/></dsp:nvSpPr><dsp:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1270000" cy="635000"/></a:xfrm>'
             '<a:prstGeom prst="chevron"><a:avLst/></a:prstGeom><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></dsp:spPr>'
             '<dsp:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr sz="1400"/><a:t>Step one</a:t></a:r></a:p></dsp:txBody>'
             '<dsp:txXfrm><a:off x="0" y="0"/><a:ext cx="1270000" cy="635000"/></dsp:txXfrm></dsp:sp>')
    dsp = 'xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram"'
    drawing = f'<dsp:drawing {dsp} {NS}><dsp:spTree><dsp:nvGrpSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvGrpSpPr/></dsp:nvGrpSpPr><dsp:grpSpPr/>{shape}</dsp:spTree></dsp:drawing>'
    drawing_id = _related(document, "drawing1", "application/vnd.ms-office.drawingml.diagramDrawing+xml", "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing", drawing)
    data = (f'<dgm:dataModel {NS}><dgm:ptLst/><dgm:cxnLst/><dgm:bg/><dgm:whole/><dgm:extLst><a:ext uri="http://schemas.microsoft.com/office/drawing/2008/diagram">'
            f'<dsp:dataModelExt {dsp} relId="{drawing_id}"/></a:ext></dgm:extLst></dgm:dataModel>')
    data_id = _related(document, "data1", "application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData", data)
    _put(document, _graphic("dgm", f'<dgm:relIds r:dm="{data_id}" r:lo="" r:qs="" r:cs=""/>', 300, 80))
    html = _html(document, tmp_path)
    assert "Step one" in html and "<svg" in html


def test_smartart_with_only_its_text_lists_it(tmp_path):
    document = docx.Document()
    data = (f'<dgm:dataModel {NS}><dgm:ptLst><dgm:pt modelId="0" type="doc"/><dgm:pt modelId="1"><dgm:t><a:bodyPr/><a:p><a:r><a:t>Only text</a:t></a:r></a:p></dgm:t></dgm:pt>'
            "</dgm:ptLst></dgm:dataModel>")
    data_id = _related(document, "data2", "application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData", data)
    _put(document, _graphic("dgm", f'<dgm:relIds r:dm="{data_id}" r:lo="" r:qs="" r:cs=""/>', 300, 80))
    assert "Only text" in _html(document, tmp_path)


def test_a_group_places_its_members_through_its_own_coordinates(tmp_path):
    document = docx.Document()
    member = ('<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="100" y="50"/><a:ext cx="100" cy="50"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr><wps:bodyPr/></wps:wsp>')
    group = (f'<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{200 * EMU}" cy="{100 * EMU}"/><a:chOff x="0" y="0"/><a:chExt cx="200" cy="100"/></a:xfrm></wpg:grpSpPr>{member}</wpg:wgp>')
    _put(document, _graphic("wpg", group, 200, 100))
    tree = lxml_html.fromstring(_html(document, tmp_path))
    inner = tree.xpath('//span[@class="drawn"]/span[@class="layer"]/span[@class="layer"]')[0]
    style = inner.get("style")
    assert "left:400.000pt" in style and "top:200.000pt" in style and "width:400.000pt" in style     # at 4x


def _in_header(document, *drawings):
    paragraph = document.sections[0].header.paragraphs[0]
    for drawing in drawings:
        run = paragraph.add_run()
        run._r.append(parse_xml(f"<w:r {NS}>{drawing}</w:r>")[0])


def test_a_watermark_is_big_faint_text_behind_the_page(tmp_path):
    document = docx.Document()
    _in_header(document, '<w:pict><v:shape id="PowerPlusWaterMarkObject" type="#_x0000_t136" style="position:absolute;margin-left:0;margin-top:0;width:400pt;height:150pt;'
                         'rotation:315;z-index:-251658752;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;'
                         'mso-position-vertical-relative:margin" fillcolor="#c00000" stroked="f"><v:fill opacity=".5"/><v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt" string="DRAFT"/></v:shape></w:pict>')
    document.add_paragraph("Text over the watermark")
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        assert "Text over the watermark" in page.get_text()
        assert "DRAFT" in page.get_text()
        middle = page.get_pixmap(dpi=36)
        reddish = sum(1 for x in range(middle.width) for y in range(middle.height)
                      if middle.pixel(x, y)[0] > middle.pixel(x, y)[1] + 40)
        assert reddish > 200             # letters, not a filled rectangle covering the page
        assert reddish < middle.width * middle.height * 0.3


def test_objects_anchored_in_a_header_land_where_the_page_says(tmp_path):
    document = docx.Document()
    logo = ('<a:solidFill><a:srgbClr val="00FF00"/></a:solidFill>')
    _in_header(document, _shape("rect", 60, 30, fill=logo, style="", anchor=(10, 5, "<wp:wrapNone/>")),      # measured from the column
               _shape("rect", 60, 80, fill=logo, style="", anchor=(300, 0, '<wp:wrapSquare wrapText="bothSides"/>')))
    document.add_paragraph("Body text begins here")
    with _printed(document, tmp_path) as pdf:
        page = pdf[0]
        lines = _line_ends(page)
        picture = page.get_pixmap(dpi=72)
        greens = [x for x in range(picture.width) if any(picture.pixel(x, y)[1] > 200 and picture.pixel(x, y)[0] < 60 for y in range(0, picture.height, 4))]
    assert min(greens) == pytest.approx(90 + 10, abs=2) and max(greens) == pytest.approx(90 + 360, abs=2)
    # The tall object floats in the header, and doesn't push the body text down.
    assert [line for line in lines if "Body text" in line[3]][0][0] < 80


def test_old_vml_shapes_draw(tmp_path):
    document = docx.Document()
    _put(document, '<w:pict><v:rect style="width:100pt;height:40pt" fillcolor="#ffc000" strokecolor="red"><v:textbox><w:txbxContent><w:p><w:r><w:t>Old box</w:t></w:r></w:p></w:txbxContent></v:textbox></v:rect></w:pict>',
         '<w:pict><v:oval style="width:50pt;height:50pt" stroked="f" fillcolor="#00f"/></w:pict>')
    html = _html(document, tmp_path)
    assert "Old box" in html and 'fill="#FFC000"' in html and 'stroke="#FF0000"' in html
    assert 'fill="#0000FF" stroke="none"' in html
