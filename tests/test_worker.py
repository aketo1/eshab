"""The worker process: JSON lines in, conversions out, gone when idle."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def _start(tmp_path, idle="60"):
    env = dict(os.environ, APPDATA=str(tmp_path / "appdata"), ESHAB_WORKER_IDLE_S=idle)
    return subprocess.Popen(
        [sys.executable, str(ROOT / "main.py"), "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, cwd=str(tmp_path),
    )


_READERS: dict = {}


def _lines(process):
    """The worker's output lines, read on a thread so a silent worker fails the
    test at its deadline instead of hanging it."""
    import queue
    import threading

    if process not in _READERS:
        lines = queue.Queue()

        def pump():
            for line in iter(process.stdout.readline, b""):
                lines.put(line)
            lines.put(None)
        threading.Thread(target=pump, daemon=True).start()
        _READERS[process] = lines
    return _READERS[process]


def _events(process, job_id, timeout=60):
    import queue

    deadline = time.monotonic() + timeout
    events = []
    lines = _lines(process)
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
        except queue.Empty:
            break
        if line is None:
            break
        event = json.loads(line)
        if event.get("id") == job_id:
            events.append(event)
            if event["event"] in ("done", "error", "cancelled"):
                return events
    pytest.fail(f"no final event for {job_id}: {events}")


def _send(process, request):
    process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
    process.stdin.flush()


def test_a_job_that_loads_a_new_library_does_not_hang(tmp_path):
    """Reading a spreadsheet loads numpy for the first time inside the job. A
    read left waiting on the stdin pipe used to freeze that load until the
    next request came, so the job never finished."""
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "sheet.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["name", "value"])
    book.active.append(["a", 1])
    book.save(source)
    process = _start(tmp_path)
    try:
        _send(process, {"id": "x1", "op": "convert", "paths": [str(source)], "target": "csv"})
        events = _events(process, "x1", timeout=45)
    finally:
        process.stdin.close()
        process.wait(10)
    assert events[-1]["event"] == "done", events


def test_convert_reports_progress_and_a_verified_output(tmp_path):
    source = tmp_path / "صورة تجربة.png"
    Image.new("RGBA", (64, 48), (240, 160, 40, 255)).save(source)
    process = _start(tmp_path)
    try:
        _send(process, {"id": "j1", "op": "convert", "paths": [str(source)], "target": "jpg"})
        events = _events(process, "j1")
    finally:
        process.stdin.close()
        process.wait(10)
    final = events[-1]
    assert final["event"] == "done", events
    output = Path(final["outputs"][0])
    assert output.suffix == ".jpg" and output.parent == tmp_path
    with Image.open(output) as image:
        assert image.size == (64, 48)
    assert any(e["event"] == "status" for e in events)


def test_tools_without_options_run_in_the_worker(tmp_path):
    source = tmp_path / "ملاحظات.txt"
    source.write_text("سطر أول   \r\n\r\n\r\n\r\nسطر ثانٍ\t\r\n", encoding="utf-8")
    process = _start(tmp_path)
    try:
        _send(process, {"id": "t1", "op": "tool", "paths": [str(source)], "tool": "txt.compress"})
        events = _events(process, "t1")
    finally:
        process.stdin.close()
        process.wait(10)
    assert events[-1]["event"] == "done", events
    cleaned = Path(events[-1]["outputs"][0]).read_text(encoding="utf-8")
    assert cleaned == "سطر أول\n\nسطر ثانٍ\n"


def test_missing_source_is_an_error_not_a_crash(tmp_path):
    process = _start(tmp_path)
    try:
        _send(process, {"id": "j2", "op": "convert", "paths": [str(tmp_path / "nope.png")], "target": "jpg"})
        events = _events(process, "j2")
        _send(process, {"op": "ping"})
        assert json.loads(_lines(process).get(timeout=30)) == {"event": "pong"}
    finally:
        process.stdin.close()
        process.wait(10)
    assert events[-1]["event"] == "error" and events[-1]["message"]


def test_worker_leaves_when_idle_and_when_the_tray_goes(tmp_path):
    process = _start(tmp_path, idle="1")
    assert process.wait(15) == 0
    process = _start(tmp_path)
    process.stdin.close()
    assert process.wait(15) == 0
