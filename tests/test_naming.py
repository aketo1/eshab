from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

from eshab import naming, i18n
from eshab.jobs import Job


def test_name_keeps_original_and_increments_across_edit_types(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "is_rtl", lambda: True)
    source = tmp_path / "الصورة.jpg"
    source.write_bytes(b"original")
    crop = naming.edited_path(source, "قص", ".png")
    crop.write_bytes(b"cropped")
    text = naming.edited_path(source, "نص", ".png")
    assert crop.name == "الصورة - تعديل 1 - قص.png"
    assert text.name == "الصورة - تعديل 2 - نص.png"
    assert source.read_bytes() == b"original"


def test_reediting_a_copy_continues_the_original_sequence(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "is_rtl", lambda: True)
    source = tmp_path / "العقد - تعديل 4 - نص.pdf"
    source.write_bytes(b"copy")
    output = naming.edited_path(source, "حجب", ".pdf")
    assert output.name == "العقد - تعديل 5 - حجب.pdf"


def test_parallel_exports_reserve_different_numbers(tmp_path):
    source = tmp_path / "photo.jpg"
    with ThreadPoolExecutor(max_workers=8) as pool:
        outputs = list(pool.map(lambda _: naming.edited_path(source, "crop", ".png"), range(20)))
    assert len(set(outputs)) == 20


def test_naming_context_is_carried_into_background_job(qapp, tmp_path):
    source = tmp_path / "photo.jpg"
    outputs = []
    def work(ctx):
        result = naming.unique_path(tmp_path, "photo Cropped", ".png")
        outputs.append(result)
        return result
    with naming.operation_scope([source], "crop"):
        job = Job(work)
    worker = threading.Thread(target=job._run)
    worker.start()
    worker.join(5)
    assert not worker.is_alive()
    assert outputs[0].name == "photo - edit 1 - crop.png"


def test_conversion_context_uses_original_name_and_output_extension(tmp_path):
    source = tmp_path / "report.docx"
    with naming.operation_scope([source], "convert to PDF"):
        output = naming.unique_path(tmp_path, source.stem, ".pdf")
    assert output.name == "report - edit 1 - convert to PDF.pdf"


def test_unsafe_label_characters_do_not_create_paths(tmp_path):
    output = naming.edited_path(tmp_path / "file.png", 'crop / edit: "test"', ".png")
    assert output.parent == tmp_path
    assert all(c not in output.name for c in '<>:"/\\|?*')
