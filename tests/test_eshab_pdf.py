from pathlib import Path
import io
import pytest
import pymupdf as fitz
from PIL import Image
from eshab.pdf_model import PdfSession,Element

@pytest.fixture
def source(tmp_path):
    p=tmp_path/'source.pdf';doc=fitz.open()
    page=doc.new_page(width=500,height=650)
    page.insert_text((40,70),'Original heading',fontsize=20)
    page.insert_text((40,115),'Keep this nearby text.',fontsize=12)
    im=Image.new('RGB',(180,100),'#c287f2');b=io.BytesIO();im.save(b,format='PNG');page.insert_image((40,180,220,280),stream=b.getvalue())
    doc.new_page(width=500,height=650).insert_text((40,70),'Second page',fontsize=20)
    doc.save(p);doc.close();return p

def test_replaces_actual_glyphs_and_preserves_neighbors(source,tmp_path):
    s=PdfSession(source);original=s.at(0,70,60,'text');assert original
    s.change_text(0,original,'Replacement title',(40,45,370,90),18)
    out=tmp_path/'edited.pdf';s.save(out)
    with fitz.open(out) as d:
        text=d[0].get_text();assert 'Replacement title' in text;assert 'Original heading' not in text;assert 'Keep this nearby text.' in text
    with fitz.open(source) as d:assert 'Original heading' in d[0].get_text()
    s.close()

def test_arabic_remains_selectable_text(source,tmp_path):
    s=PdfSession(source);s.change_text(0,None,'مرحبا من اسحب',(40,320,400,385),22)
    out=tmp_path/'arabic.pdf';s.save(out)
    with fitz.open(out) as d:
        text=d[0].get_text();assert any('\u0600'<=c<='\u06ff' for c in text)
        assert len(d[0].get_text('words'))>=9
    s.close()

def test_image_replacement_and_move_do_not_remove_text(source,tmp_path):
    s=PdfSession(source);e=s.at(0,80,220,'image');assert e
    b=io.BytesIO();Image.new('RGB',(60,90),'#2244ff').save(b,format='PNG')
    s.change_image(0,e,b.getvalue(),(280,200,340,290));out=tmp_path/'image.pdf';s.save(out)
    with fitz.open(out) as d:
        pix=d[0].get_pixmap();im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        assert im.getpixel((310,240))[2]>200;assert im.getpixel((90,220))==(255,255,255)
        assert 'Original heading' in d[0].get_text()
    s.close()

def test_undo_redo_and_page_order(source):
    s=PdfSession(source);s.reorder([1,0,1]);assert s.count()==3;assert 'Second' in s.doc[0].get_text()
    s.undo();assert s.count()==2;assert 'Original' in s.doc[0].get_text()
    s.redo();assert s.count()==3;s.close()

def test_same_file_save_creates_original_backup(source):
    before=source.read_bytes();s=PdfSession(source);s.change_text(0,None,'Saved',(40,390,260,425),15)
    backup=s.save(source,overwrite=True);assert backup.read_bytes()==before
    with fitz.open(source) as d:assert 'Saved' in d[0].get_text()
    s.close()

def test_failed_edit_rolls_back(source):
    s=PdfSession(source);before=s.doc[0].get_text()
    with pytest.raises(Exception):s.change_image(0,s.at(0,80,220,'image'),b'not an image',(10,10,100,100))
    assert s.doc[0].get_text()==before;s.close()

def test_rotated_page_edits_match_display(source,tmp_path):
    d=fitz.open(source);d[0].set_rotation(90);rot=tmp_path/'rotated.pdf';d.save(rot);d.close()
    s=PdfSession(rot);assert s.doc[0].rotation==0
    e=next(e for e in s.elements(0) if 'heading' in e.text)
    s.change_text(0,e,'Rotated edit',(e.rect[0],e.rect[1],e.rect[0]+180,e.rect[1]+45),12)
    assert 'Rotated edit' in s.doc[0].get_text();assert 'Original heading' not in s.doc[0].get_text();s.close()
