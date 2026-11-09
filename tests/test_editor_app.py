"""Eshab's editors (eshab/editor_app.py): every tool is described, each tool's
work makes the right file from what the window sends, and the PDF editor's
changes reach the document."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from eshab import editor_app, naming, tools
from eshab.engines import Ctx
from eshab.media import StreamInfo, ffmpeg_path

PREVIEWS = {"image", "crop", "boxes", "annotate", "order", "waveform", "video", "info", "pdf"}
FIELD_TYPES = {"choice", "slider", "toggle", "color", "text", "number", "picture", "button"}


def _photo(path: Path, size=(320, 200), color=(40, 120, 200), exif=None, dot=True) -> Path:
    picture = Image.new("RGB", size, color)
    if dot:
        ImageDraw.Draw(picture).ellipse((60, 40, 160, 140), fill=(250, 200, 40))
    if exif:
        data = Image.Exif()
        for tag, value in exif.items():
            data[tag] = value
        picture.save(path, exif=data)
    else:
        picture.save(path)
    return path


def _job(key, files, options=None, state=None):
    editor = SimpleNamespace(tool_key=key, order=[], files=list(files), duration=0.0)
    return editor_app.Job(list(files), options or {}, state or {}, Ctx(), set(), editor)


def _run(key, files, options=None, state=None):
    job = _job(key, files, options, state)
    with naming.operation_scope(job.files, key):
        return [Path(p) for p in editor_app.tool(key).run(job)]


# -- descriptions -------------------------------------------------------------------------------

def test_every_tool_the_tray_opens_has_an_editor():
    from eshab.app import EDITOR_TOOLS

    for key in EDITOR_TOOLS:
        assert editor_app.tool(key) is not None, key


def test_every_editor_is_described_completely():
    for key, spec in editor_app._tools().items():
        assert spec.preview in PREVIEWS, key
        keys = set()
        for field in spec.fields:
            assert field["type"] in FIELD_TYPES, (key, field)
            assert field["label"] and not field["label"].startswith("ed."), (key, field["key"])
            assert field["key"] not in keys, (key, field["key"])
            keys.add(field["key"])
            for name in (field.get("when") or {}):
                assert name in keys, f"{key}: {field['key']} depends on {name}, which comes later or is missing"
            if field["type"] == "choice":
                values = [o["value"] for o in field["options"]]
                assert field["default"] in values, (key, field["key"])
                assert all(o["label"] and not o["label"].startswith("ed.") for o in field["options"]), (key, field["key"])
        json.dumps(spec.fields)          # the window reads them as JSON


def test_details_typed_for_several_files_keep_each_files_own():
    one = _job("img.metadata", [Path("a.jpg")])
    many = _job("img.metadata", [Path("a.jpg"), Path("b.jpg")])
    fields = {"title": "  New  ", "artist": ""}
    assert editor_app._written(one, fields) == {"title": "New", "artist": ""}
    assert editor_app._written(many, fields) == {"title": "New"}


# -- the work of each tool ----------------------------------------------------------------------

def test_crop_keeps_the_box(tmp_path):
    out, = _run("img.crop", [_photo(tmp_path / "p.png")], state={"box": {"x": 10, "y": 20, "w": 100, "h": 50}})
    assert Image.open(out).size == (100, 50)


def test_crop_without_a_box_says_what_to_do(tmp_path):
    with pytest.raises(ValueError):
        _run("img.crop", [_photo(tmp_path / "p.png")], state={"box": {"x": 0, "y": 0, "w": 0, "h": 0}})


def test_hidden_areas_are_filled(tmp_path):
    out, = _run("img.redact", [_photo(tmp_path / "p.png")], {"mode": "solid", "color": "#FF0000"},
                {"boxes": [{"x": 0, "y": 0, "w": 40, "h": 30}]})
    assert Image.open(out).convert("RGB").getpixel((10, 10)) == (255, 0, 0)


def test_marks_are_drawn_where_they_were_made(qapp, tmp_path):
    marks = [{"type": "rect", "x1": 200, "y1": 20, "x2": 300, "y2": 180, "color": "#FF0000", "width": 8},
             {"type": "text", "text": "Hi", "x1": 10, "y1": 150, "x2": 120, "y2": 200, "size": 30, "color": "#00FF00"}]
    out, = _run("img.annotate", [_photo(tmp_path / "p.png")], state={"marks": marks})
    picture = Image.open(out).convert("RGB")
    assert picture.getpixel((200, 100))[0] > 200          # the box's left edge
    assert picture.getpixel((250, 100)) == (40, 120, 200)  # inside it, untouched


def test_photo_tools_make_their_files(tmp_path):
    photo = _photo(tmp_path / "p.png")
    clear = tmp_path / "c.png"
    Image.new("RGBA", (100, 80), (0, 0, 0, 0)).save(clear)
    assert _run("img.edit", [photo], {"preset": "warm", "exposure": 20})[0].exists()
    background, = _run("img.background", [clear], {"fill": "color", "color": "#FFFFFF", "aspect": "1:1", "margin": 10, "radius": 0})
    assert Image.open(background).size == (120, 120)
    small, = _run("img.compress", [photo], {"strength": "strong", "size": "1280"})
    assert small.exists()


def test_photos_go_into_the_pdf_in_the_order_shown(tmp_path):
    import pymupdf

    files = [_photo(tmp_path / f"{name}.png", size, color, dot=False) for name, size, color in
             (("b", (200, 100), (255, 0, 0)), ("a", (100, 200), (0, 255, 0)), ("c", (150, 150), (0, 0, 255)))]
    out, = _run("img.pdf", files, {"order": "name", "rows": 1, "columns": 1}, {"order": [2, 0, 1]})
    with pymupdf.open(out) as document:
        assert document.page_count == 3
        first = document[0].get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
        red, green, blue = first.pixel(first.width // 2, first.height // 2)[:3]
        assert blue > 240 and red < 15 and green < 15        # c (blue) first, as shown


def test_collage_follows_the_order(tmp_path):
    files = [_photo(tmp_path / f"{i}.png", color=(60 * i, 0, 0)) for i in range(3)]
    out, = _run("img.collage", files, {"layout": "horizontal", "spacing": 0, "padding": 0, "corner_radius": 0,
                                        "background": "white", "resolution": "100", "fit": "fill"}, {"order": [2, 1, 0]})
    picture = Image.open(out).convert("RGB")
    assert picture.size == (300, 100)
    assert picture.getpixel((10, 10))[0] == 120       # file 2 first


def test_photo_details_are_written(tmp_path):
    photo = _photo(tmp_path / "p.jpg", exif={270: "Old", 315: "Me"})
    out, = _run("img.metadata", [photo], {"description": "New", "artist": "Me", "copyright": "(c) Test",
                                          "keep_location": True, "strip_all": False})
    exif = Image.open(out).getexif()
    assert (exif.get(270), exif.get(315), exif.get(33432)) == ("New", "Me", "(c) Test")


def test_pdf_details_are_written(tmp_path):
    import pymupdf

    source = tmp_path / "d.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.set_metadata({"title": "Old", "author": "Someone"})
        document.save(str(source))
    out, = _run("pdf.metadata", [source], {"title": "New", "author": "Someone", "subject": "", "keywords": ""})
    with pymupdf.open(out) as document:
        assert document.metadata["title"] == "New"
        assert document.metadata["author"] == "Someone"


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_path(), reason="FFmpeg is not installed")


def _clip(path: Path, seconds=2) -> Path:
    import subprocess

    subprocess.run([str(ffmpeg_path()), "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=15:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, creationflags=0x08000000)
    return path


@needs_ffmpeg
def test_snapshots_are_pictures_inside_an_editor_job(tmp_path):
    clip = _clip(tmp_path / "v.mp4")
    outputs = _run("vid.snapshots", [clip], {"every": 0}, {"times": [0.5, 1.0]})
    assert len(outputs) == 2
    assert all(p.suffix == ".png" and p.exists() for p in outputs)


@needs_ffmpeg
def test_video_crop_keeps_the_box(tmp_path):
    from eshab.media import probe

    clip = _clip(tmp_path / "v.mp4", 1)
    out, = _run("vid.crop", [clip], state={"box": {"x": 11, "y": 20, "w": 101, "h": 81}})
    video = probe(out).video()
    assert (video.width, video.height) == (100, 80)


def test_a_phone_video_is_measured_upright():
    stream = StreamInfo(kind="video", width=1920, height=1080, rotation=-90)
    assert stream.display_size() == (1080, 1920)
    assert StreamInfo(kind="video", width=1920, height=1080).display_size() == (1920, 1080)


# -- the editor itself ----------------------------------------------------------------------------

def _wait(editor, seconds=20):
    from PySide6.QtCore import QCoreApplication

    end = time.time() + seconds
    while editor.loading and time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    QCoreApplication.processEvents()
    assert not editor.loading


def test_details_start_from_what_the_file_says(qapp, tmp_path):
    photo = _photo(tmp_path / "p.jpg", exif={270: "A sample photo", 315: "Test author"})
    editor = editor_app.Editor("img.metadata", [photo], editor_app.Pictures())
    _wait(editor)
    assert editor.initialOptions == {"description": "A sample photo", "artist": "Test author"}
    spec = json.loads(editor.spec)
    assert spec["preview"] == "image" and spec["mode"] == "metadata"
    editor.cleanup()


def test_several_files_start_with_empty_details(qapp, tmp_path):
    files = [_photo(tmp_path / f"{i}.jpg", exif={270: f"Photo {i}"}) for i in range(2)]
    editor = editor_app.Editor("img.metadata", files, editor_app.Pictures())
    _wait(editor)
    assert editor.initialOptions == {}
    editor.cleanup()


def test_pdf_editor_changes_reach_the_document(qapp, tmp_path, monkeypatch):
    import pymupdf
    from PySide6.QtCore import QCoreApplication, QSize

    source = tmp_path / "r.pdf"
    with pymupdf.open() as document:
        for n in range(2):
            page = document.new_page(width=595, height=842)
            page.insert_text((60, 90), f"Page {n + 1} title", fontsize=20)
            page.insert_text((60, 130), "Revenue grew by 12 percent.", fontsize=12)
        document.save(str(source))

    pictures = editor_app.Pictures()
    editor = editor_app.Editor("pdf.edit", [source], pictures)
    _wait(editor)
    assert editor.pdfCount == 2 and not editor.canUndo

    elements = json.loads(editor.pdfElements(0))
    at = next(i for i, e in enumerate(elements) if e["text"].startswith("Revenue"))
    assert editor.pdfEditText(0, at, "Sales rose by 20 percent.") == ""
    assert editor.pdfAddText(0, 60, 300, 400, 330, "Added by Eshab", 14) == ""
    assert editor.pdfRedact(0, 50, 70, 300, 100) == ""
    assert editor.pdfDuplicate(1) == "" and editor.pdfCount == 3
    assert editor.pdfMove(2, -2) == 0
    assert editor.pdfRotate(0) == ""
    assert editor.canUndo
    editor.pdfUndo()
    assert editor.canRedo
    editor.pdfRedo()

    # Pages are drawn when the window asks for them, at the size it asks.
    url = editor.pdfPage(1, 0.5)
    assert url.startswith("image://editor/pdf/1/0.5/")
    image = pictures.requestImage(url.split("image://editor/", 1)[1], QSize(), QSize())
    assert (image.width(), image.height()) == (298, 421)

    outputs = []
    monkeypatch.setattr(editor_app, "announce", lambda title, outs: outputs.extend(outs))
    editor.run("{}", "{}")
    end = time.time() + 30
    while not outputs and time.time() < end and not editor.error:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert outputs, editor.error
    with pymupdf.open(outputs[0]) as saved:
        assert saved.page_count == 3
        text = saved[1].get_text()        # the first page, now second
        assert "Sales rose by 20 percent." in text and "Revenue" not in text
        assert "Added by Eshab" in text
        assert "title" not in text        # hidden for good
    editor.cleanup()


def test_pictures_answer_unknown_names_with_a_clear_pixel(qapp):
    from PySide6.QtCore import QSize

    image = editor_app.Pictures().requestImage("nothing/1", QSize(), QSize())
    assert (image.width(), image.height()) == (1, 1)
    checker = editor_app.Pictures().requestImage("checker-dark/1", QSize(), QSize())
    assert (checker.width(), checker.height()) == (16, 16)
