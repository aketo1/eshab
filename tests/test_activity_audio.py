"""Desktop island lifecycle, file references, and real audio exports."""
import math
import struct
import time
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QWidget

from eshab import tools
from eshab.editors.audio import audio_peaks
from eshab.island import ActivityIsland
from eshab.progress import ProgressWindow
from eshab.jobs import Job
from eshab.studio import StudioBridge


def audio_file(path):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"".join(struct.pack("<h", round(15000 * math.sin(i * 2 * math.pi * 440 / 8000)))
                                    for i in range(24000)))
    return path


def pump(app, condition, seconds=8):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert condition()


def test_island_reference_width_shelf_dedup_and_originals(qapp, tmp_path):
    original = tmp_path / "ملف.txt"
    original.write_text("keep me", encoding="utf-8")
    island = ActivityIsland()
    compact = island._compact_rect()
    area = island._display.availableGeometry()
    assert compact.width() == 104
    assert abs(island.geometry().center().x() - area.center().x()) <= 1
    assert island.y() == island._display.geometry().top()
    assert island.width() <= 408
    assert island.width() <= round(area.width() * .31875)
    island.add([original, original, tmp_path / "missing"])
    assert island.files == [original]
    island.clear_shelf()
    assert not island.files and original.read_text(encoding="utf-8") == "keep me"
    island.close()


def test_compact_island_reaches_its_size_and_is_transparent(qapp):
    island = ActivityIsland()
    island.present()
    island._hover_timer.stop()
    pump(qapp, lambda: not island.motion.running)
    assert island._surface_rect().height() == 38
    assert island._surface_rect().width() == 104
    image = island.grab().toImage()
    assert image.pixelColor(image.width() // 2, 33).alpha() < 100
    island.close()


def test_island_collapses_after_leaving_shelf_or_drop(qapp, monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor
    island = ActivityIsland()
    island.present()
    island.set_expanded(True)
    island._drop_hover = True
    monkeypatch.setattr(QCursor, "pos", lambda: QPoint(island.x() - 50, island.y() + 60))
    island._check_hover()
    island._candidate_since -= island.LEAVE_DELAY + .01
    island._check_hover()
    assert not island.expanded and not island._drop_hover
    island._hover_timer.stop()
    pump(qapp, lambda: not island.motion.running)
    assert island._surface_rect().height() == 38 and island._surface_rect().width() == 104
    island.close()


def test_island_accepts_local_file_drop_as_copy(qapp, tmp_path):
    original = tmp_path / "tone.wav"
    original.write_bytes(b"unchanged")
    island = ActivityIsland()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(original)), QUrl("https://example.com/remote")])
    event = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                       mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    island.dropEvent(event)
    assert event.isAccepted() and event.dropAction() == Qt.DropAction.CopyAction
    assert island.files == [original] and original.read_bytes() == b"unchanged"
    island.close()


def test_jobs_do_not_create_or_present_the_shelf(qapp, monkeypatch):
    from eshab import island as shelf_module
    monkeypatch.setattr(shelf_module, "_island", None)
    first = ProgressWindow("first", Job(lambda ctx: []))
    second = ProgressWindow("second", Job(lambda ctx: []))
    first.job.progress.emit(.25)
    second.job.progress.emit(.75)
    assert first.bar.value() == 250 and second.bar.value() == 750
    first.job.finished.emit([])
    second.job.failed.emit("Readable failure details")
    assert first._job_done and not first.failed
    assert second.failed and second.description.toolTip() == "Readable failure details"
    assert shelf_module._island is None
    first.close()
    second.close()


def test_waveform_is_bounded_and_trim_keeps_original(qapp, tmp_path):
    source = audio_file(tmp_path / "اختبار.wav")
    before = source.read_bytes()
    peaks = audio_peaks(source, buckets=80)
    assert 1 <= len(peaks) <= 80 and max(peaks) > .3
    result = tools.trim_audio(source, .4, 1.65, tools.Ctx(), set())
    assert result != source and source.read_bytes() == before
    assert abs(tools.probe_duration_seconds(result) - 1.25) < .02


def test_audio_bridge_validates_time_and_exports_in_background(qapp, tmp_path):
    source = audio_file(tmp_path / "original.wav")
    host = QWidget()
    host.controller = None
    bridge = StudioBridge(host, "audio", source)
    bridge._audio_data = {"duration": 3., "peaks": [.3] * 10}
    for start, end in ((-1, 1), (1, 1), (2, 1), (0, 4), (float("nan"), 2), (0, float("inf"))):
        with pytest.raises(ValueError):
            bridge.dispatch("saveAudio", {"start": start, "end": end})
    received = []
    bridge.event.connect(lambda name, data: received.append(name))
    bridge.dispatch("saveAudio", {"start": .5, "end": 2.})
    handle = bridge.windows[-1]
    pump(qapp, lambda: handle._job_done)
    assert not handle.failed and "saved" in received
    assert abs(tools.probe_duration_seconds(handle.outputs[0]) - 1.5) < .02
    host.close()
