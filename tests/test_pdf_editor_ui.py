"""The PDF editor window: click-to-edit text, move images, add text, undo, save."""

import io

import pymupdf as fitz
import pytest
from PIL import Image
from PySide6.QtCore import QPointF

from eshab import pdf_editor


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "letter.pdf"
    doc = fitz.open()
    page = doc.new_page(width=500, height=650)
    page.insert_text((40, 70), "Hello old title", fontsize=20)
    page.insert_text((40, 115), "A second line stays.", fontsize=12)
    image = io.BytesIO()
    Image.new("RGB", (120, 80), "#888888").save(image, format="PNG")
    page.insert_image((40, 180, 160, 260), stream=image.getvalue())
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def editor(qapp, document):
    window = pdf_editor.PdfEditor(document)
    window.canvas.zoom = 1.0
    window._refresh_all()
    yield window
    window.session.dirty = False
    window.close()


def _text(path):
    with fitz.open(path) as doc:
        return doc[0].get_text()


def test_click_text_edit_and_save_in_place(editor, document):
    editor.canvas.select_at(QPointF(60, 62))
    assert editor.canvas.selected is not None
    assert editor.canvas.selected.kind == "text"
    assert editor.stack.currentIndex() == 1
    editor.text_edit.setPlainText("مرحبا New title")
    editor._apply_text()
    assert editor.session.dirty
    assert editor.save()
    text = _text(document)
    assert "New title" in text
    assert "Hello old title" not in text
    assert "A second line stays." in text
    backups = list(document.parent.glob("letter - *.pdf"))
    assert len(backups) == 1 and "Hello old title" in _text(backups[0])


def test_move_an_image_by_dragging(editor):
    editor.canvas.select_at(QPointF(100, 220))
    assert editor.canvas.selected.kind == "image"
    editor.move_selected((260, 300, 380, 380))
    images = [e for e in editor.session.elements(0) if e.kind == "image"]
    assert len(images) == 1
    x0, y0, x1, y1 = images[0].rect
    assert abs(x0 - 260) < 2 and abs(y0 - 300) < 2


def test_add_text_then_undo(editor):
    before = editor.session.count()
    editor.add_text_at(QPointF(60, 450))
    assert any(e.text and "New text" in e.text for e in editor.session.elements(0))
    editor.undo()
    assert not any(e.text and "New text" in e.text for e in editor.session.elements(0))
    assert editor.session.count() == before


def test_page_tools(editor):
    editor._duplicate()
    assert editor.session.count() == 2
    editor._move_page(1)
    editor._delete_page()
    assert editor.session.count() == 1
    assert editor.pages.count() == 1
