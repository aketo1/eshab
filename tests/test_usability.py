"""Regression checks for file choices, pending edits and cached wheel rendering."""
from pathlib import Path

from PIL import Image
import pymupdf as fitz
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter

from eshab import catalog, settings
from eshab.editors.images import AnnotateDialog
from eshab.pdf_editor import PdfEditor
from eshab.wheel import FanItem, LiquidWheel
from eshab.workspace import HomeWindow


@pytest.mark.parametrize("suffix", ["jpg", "jpeg", "png", "heic", "tiff", "webp"])
def test_images_never_offer_word_even_when_ocr_is_installed(monkeypatch, suffix):
    monkeypatch.setattr(catalog, "available_engines", lambda: {"pillow", "heic", "docx", "ocr", "pdfium"})
    source = Path("photo." + suffix)
    targets = {item.target_ext for item in catalog.conversions_for([source])}
    assert "docx" not in targets
    assert "pdf" in targets
    assert catalog.conversion_paths("docx", [source]) == []
    assert ("jpg" if suffix == "jpeg" else suffix) not in targets


def test_merge_tools_need_two_matching_files(monkeypatch):
    monkeypatch.setattr(catalog, "available_engines", lambda: {"pillow", "ffmpeg"})
    for name, tool_id in (("photo.jpg", "img.collage"), ("paper.pdf", "pdf.merge"), ("clip.mp4", "vid.join")):
        first = Path(name)
        second = first.with_stem("second")
        assert tool_id not in {t.id for t in catalog.tools_for([first])}
        assert tool_id in {t.id for t in catalog.tools_for([first, second])}


def test_unavailable_media_and_qr_tools_are_hidden(monkeypatch):
    monkeypatch.setattr(catalog, "available_engines", lambda: {"pillow"})
    assert "aud.trim" not in {t.id for t in catalog.tools_for([Path("sound.mp3")])}
    assert "qr.read" not in {t.id for t in catalog.tools_for([Path("photo.jpg")])}


def test_home_shows_exact_subset_for_a_mixed_conversion(qapp, tmp_path):
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 48), "orange").save(photo)
    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((30, 50), "A document")
    doc.save(pdf)
    doc.close()
    window = HomeWindow()
    window.add_files([photo, pdf, photo])
    assert len(window.selected_paths()) == 2
    window.formats.setCurrentIndex(window.formats.findData("docx"))
    assert window.convert_btn.isEnabled()
    assert "1" in window.conversion_hint.text() and "2" in window.conversion_hint.text()
    window.file_list.clearSelection()
    assert not window.convert_btn.isEnabled()
    window.clear_files()
    assert window.stack.currentIndex() == 0
    window.close()


def test_pdf_save_commits_text_without_an_extra_apply_click(qapp, tmp_path):
    source = tmp_path / "note.pdf"
    doc = fitz.open()
    doc.new_page(width=500, height=600).insert_text((40, 70), "Before", fontsize=18)
    doc.save(source)
    doc.close()
    window = PdfEditor(source)
    window.canvas.select_at(QPointF(60, 63))
    window.text_edit.setPlainText("After save")
    assert window._has_pending_text()
    assert window.save()
    with fitz.open(source) as saved:
        assert "After save" in saved[0].get_text()
        assert "Before" not in saved[0].get_text()
    assert not window._has_pending_text()
    window.close()


def test_pdf_selecting_another_item_keeps_the_text_edit(qapp, tmp_path):
    source = tmp_path / "note.pdf"
    doc = fitz.open()
    page = doc.new_page(width=500, height=600)
    page.insert_text((40, 70), "Before", fontsize=18)
    page.insert_text((40, 120), "Second", fontsize=18)
    doc.save(source)
    doc.close()
    window = PdfEditor(source)
    window.canvas.select_at(QPointF(60, 63))
    window.text_edit.setPlainText("Changed")
    window.canvas.select_at(QPointF(60, 113))
    assert "Changed" in window.session.doc[0].get_text()
    assert window.text_edit.toPlainText() == "Second"
    window.session.dirty = False
    window.close()


def test_annotation_inline_text_and_redo(qapp, tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (100, 100), "white").save(source)
    dialog = AnnotateDialog(source)
    dialog._select_tool("text")
    dialog.annotation_text.setText("A note")
    assert dialog.canvas.text_provider() == "A note"
    dialog.canvas.ops.append({"type": "text", "x": 10, "y": 20, "text": "A note"})
    dialog.canvas.undo()
    assert not dialog.canvas.ops
    dialog.canvas.redo()
    assert dialog.canvas.ops[0]["text"] == "A note"
    dialog.close()


def test_wheel_reuses_settled_drop_layer_and_invalidates_on_change(qapp, monkeypatch):
    wheel = LiquidWheel()
    scene = wheel.scene
    scene.set_items([FanItem("png", "PNG"), FanItem("pdf", "PDF")], False)
    scene.fade.snap(1)
    scene.orb.snap(1)
    calls = []
    original = scene._paint_drop
    monkeypatch.setattr(scene, "_paint_drop", lambda *args: (calls.append(True), original(*args)))
    first = scene._paint_layer()
    assert len(calls) == 2
    assert scene._paint_layer() is first
    assert len(calls) == 2
    scene.hovers[0].snap(1)
    scene._paint_layer()
    assert len(calls) == 3
    scene.backdrop.reset()
    scene._paint_layer()
    assert len(calls) == 5
    wheel.close()
