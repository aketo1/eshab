"""Native bridge and full-resolution output behind the visual studio."""
from pathlib import Path

import pymupdf as fitz
from PIL import Image
import pytest
from PySide6.QtWidgets import QWidget

from eshab import tools
from eshab.studio import StudioBridge, export_image, _asset_root


def test_studio_assets_ship_together():
    for name in ("studio.html", "studio.css", "studio.js"):
        assert (_asset_root() / name).is_file()


def test_image_preview_is_bounded_and_keeps_original_dimensions(qapp, tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (2500, 2000), "orange").save(source)
    host = QWidget()
    bridge = StudioBridge(host, "image", source)
    state = bridge.dispatch("init", {})
    assert (state["width"], state["height"]) == (2500, 2000)
    import base64, io
    with Image.open(io.BytesIO(base64.b64decode(state["image"].split(",")[1]))) as preview:
        assert max(preview.size) <= 1800
    with pytest.raises(ValueError, match="Choose this file"):
        bridge.dispatch("edit", {"path": str(tmp_path / "not-picked.pdf")})
    host.close()


def test_clearing_the_workspace_removes_native_file_state(qapp, tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (12, 12), "white").save(source)
    host = QWidget()
    bridge = StudioBridge(host)
    bridge.add_files([source])
    assert len(bridge.file_items()) == 1
    assert bridge.dispatch("clear", {}) == []
    assert not bridge.files and not bridge.allowed
    bridge.add_files([source])
    assert len(bridge.file_items()) == 1
    host.close()


def test_export_replays_crop_rotate_and_cover_at_source_resolution(qapp, tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (1200, 800), "white").save(source)
    before = source.read_bytes()
    output = tmp_path / "edited.png"
    operations = [{"type": "crop", "box": [.25, .25, .5, .5]}, {"type": "rotate"},
                  {"type": "redact", "box": [0, 0, .5, .5], "color": "#000000"}]
    export_image(source, {}, operations, output, tools.Ctx())
    with Image.open(output) as result:
        assert result.size == (400, 600)
        assert result.getpixel((30, 30))[:3] == (0, 0, 0)
        assert result.getpixel((350, 550))[:3] == (255, 255, 255)
    assert source.read_bytes() == before


def test_inline_pdf_changes_real_text_and_saves_a_copy(qapp, tmp_path):
    source = tmp_path / "source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=500, height=650)
    page.insert_text((40, 70), "Old title", fontsize=20)
    page.insert_text((40, 120), "Keep this line", fontsize=12)
    doc.save(source)
    doc.close()
    original = source.read_bytes()
    host = QWidget()
    bridge = StudioBridge(host, "pdf", source)
    page = bridge.dispatch("init", {})["pdf"]
    element = next(item for item in page["elements"] if item["text"] == "Old title")
    updated = bridge.dispatch("pdfText", {**element, "text": "New title"})
    assert updated["dirty"]
    output = Path(bridge.dispatch("pdfSave", {}))
    assert output != source and source.read_bytes() == original
    with fitz.open(output) as saved:
        text = saved[0].get_text()
        assert "New title" in text and "Old title" not in text
        assert "Keep this line" in text
    bridge.session.close()
    host.close()


def test_pdf_name_reports_current_edits_after_undo_and_redo(qapp, tmp_path):
    source = tmp_path / "letter.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((40, 70), "Original title", fontsize=18)
    doc.save(source)
    doc.close()
    host = QWidget()
    bridge = StudioBridge(host, "pdf", source)
    element = bridge.dispatch("init", {})["pdf"]["elements"][0]
    bridge.dispatch("pdfText", {**element, "text": "Changed title"})
    bridge.dispatch("pdfRedact", {"rect": [300, 300, 340, 340]})
    bridge.dispatch("pdfUndo", {})
    first = Path(bridge.dispatch("pdfSave", {}))
    assert first.name == "letter - edit 1 - text.pdf"
    bridge.dispatch("pdfRedo", {})
    second = Path(bridge.dispatch("pdfSave", {}))
    assert second.name == "letter - edit 2 - text + redact.pdf"
    bridge.session.close()
    host.close()
