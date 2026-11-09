"""Eshab's worker process: conversions and tools, away from the tray.

The tray process stays small: Pillow, PyMuPDF, the document readers and the
FFmpeg wrappers are only ever imported here. The tray starts
``Eshab --worker`` when a job arrives and talks JSON lines over the child's
stdin/stdout; the worker leaves on its own after a quiet minute, so its
memory goes back to Windows.

Requests, one JSON object per line on stdin::

    {"id": "a1", "op": "convert", "paths": ["C:/x.heic"], "target": "jpg"}
    {"id": "a1", "op": "cancel"}

Events, one per line on stdout::

    {"id": "a1", "event": "status", "text": "..."}
    {"id": "a1", "event": "progress", "value": 0.42}
    {"id": "a1", "event": "done", "outputs": ["C:/x.jpg"]}
    {"id": "a1", "event": "error", "message": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
from pathlib import Path

log = logging.getLogger("eshab.worker")

IDLE_EXIT_S = 60.0
PROGRESS_STEP = 0.005
PROGRESS_INTERVAL_S = 0.08


class Worker:
    def __init__(self, write, idle_exit_s: float = IDLE_EXIT_S):
        self._write = write
        self._idle_exit_s = idle_exit_s
        self._lock = threading.Lock()
        self._cancels: dict[str, threading.Event] = {}
        self._last_activity = time.monotonic()
        self.closed = threading.Event()

    # -- output ----------------------------------------------------------

    def emit(self, **event) -> None:
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            self._write(line)

    # -- input -----------------------------------------------------------

    def handle(self, request: dict) -> None:
        self._last_activity = time.monotonic()
        op = request.get("op")
        job_id = str(request.get("id", ""))
        if op == "ping":
            self.emit(event="pong")
        elif op == "cancel":
            cancel = self._cancels.get(job_id)
            if cancel is not None:
                cancel.set()
        elif op == "convert":
            self._start(job_id, self._convert, request)
        elif op == "tool":
            self._start(job_id, self._tool, request)
        else:
            self.emit(id=job_id, event="error", message=f"unknown op: {op}")

    def read_loop(self, fd: int) -> None:
        buffer = b""
        read = _pipe_reader(fd)
        while True:
            try:
                chunk = read()
            except OSError:
                chunk = b""
            if not chunk:
                break  # the tray closed our stdin: it quit or crashed
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    self.handle(json.loads(line))
                except Exception:
                    log.exception("Bad request")
        self.closed.set()

    def idle(self) -> bool:
        return not self._cancels and time.monotonic() - self._last_activity > self._idle_exit_s

    # -- jobs ------------------------------------------------------------

    def _start(self, job_id: str, work, request: dict) -> None:
        cancel = threading.Event()
        self._cancels[job_id] = cancel

        def run() -> None:
            try:
                outputs = work(job_id, request, cancel)
                if cancel.is_set():
                    self.emit(id=job_id, event="cancelled")
                else:
                    self.emit(id=job_id, event="done", outputs=[str(p) for p in outputs])
            except Exception as exc:
                if cancel.is_set():
                    self.emit(id=job_id, event="cancelled")
                else:
                    log.error("Job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
                    self.emit(id=job_id, event="error", message=str(exc) or type(exc).__name__)
            finally:
                self._cancels.pop(job_id, None)
                self._last_activity = time.monotonic()

        threading.Thread(target=run, name=f"eshab-job-{job_id}", daemon=True).start()

    def _ctx(self, job_id: str, cancel: threading.Event):
        from .engines import Ctx

        state = {"value": -1.0, "at": 0.0}

        def progress(value: float) -> None:
            now = time.monotonic()
            if value < 0 or value >= 1.0 or abs(value - state["value"]) >= PROGRESS_STEP \
                    and now - state["at"] >= PROGRESS_INTERVAL_S:
                state["value"], state["at"] = value, now
                self.emit(id=job_id, event="progress", value=round(float(value), 4))

        return Ctx(progress, lambda text: self.emit(id=job_id, event="status", text=str(text)), cancel)

    def _convert(self, job_id: str, request: dict, cancel: threading.Event) -> list[Path]:
        from . import engines, i18n, naming
        from .jobs import batch_ctx

        paths = [Path(p) for p in request.get("paths", [])]
        target = str(request["target"]).lower()
        ctx = self._ctx(job_id, cancel)
        reserved: set[Path] = set()
        outputs: list[Path] = []
        descriptor = ("تحويل إلى " if i18n.is_rtl() else "convert to ") + target.upper()
        with naming.operation_scope(paths, descriptor):
            for index, path in enumerate(paths):
                if cancel.is_set():
                    break
                file_ctx = batch_ctx(ctx, len(paths), index) if len(paths) > 1 else ctx
                ctx.status(i18n.tr("action.converting_file", name=path.name))
                produced = engines.convert_single(path, target, file_ctx, reserved)
                for output in produced:
                    verify_output(Path(output), target)
                outputs.extend(produced)
        return outputs


    def _tool(self, job_id: str, request: dict, cancel: threading.Event) -> list[Path]:
        from . import i18n, naming

        key = str(request["tool"])
        run = _TOOLS.get(key)
        if run is None:
            raise RuntimeError(f"unknown tool: {key}")
        paths = [Path(p) for p in request.get("paths", [])]
        ctx = self._ctx(job_id, cancel)
        with naming.operation_scope(paths, i18n.tr("tool." + key)):
            outputs = run(paths, ctx, set())
        for output in outputs:
            verify_output(Path(output), Path(output).suffix.lstrip("."))
        return outputs


def _pipe_reader(fd: int):
    """A reader for our stdin that never leaves a read waiting on the pipe.

    On Windows a read blocked on a synchronous pipe holds the handle: a DLL
    loading meanwhile (numpy's, the first time a job imports it) asks the
    C runtime about the same handle and waits for that read, so the job
    hangs until the next request arrives. So: look first, read only what is
    there."""
    if os.name != "nt":
        return lambda: os.read(fd, 65536)
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        handle = msvcrt.get_osfhandle(fd)
    except OSError:
        return lambda: b""
    if kernel32.GetFileType(wintypes.HANDLE(handle)) != 3:     # not a pipe (a file, a console)
        return lambda: os.read(fd, 65536)
    peek = kernel32.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    peek.restype = wintypes.BOOL

    def read() -> bytes:
        while True:
            available = wintypes.DWORD(0)
            if not peek(wintypes.HANDLE(handle), None, 0, None, ctypes.byref(available), None):
                return b""                     # the tray closed its end
            if available.value:
                return os.read(fd, min(available.value, 65536))
            time.sleep(0.04)
    return read


def _tool_table():
    from . import engines, tools

    return {
        "arc.extract": lambda paths, ctx, reserved: [engines.extract_archive(paths[0], ctx, reserved)],
        "pdf.merge": lambda paths, ctx, reserved: [tools.merge_pdfs(paths, ctx, reserved)],
        "pdf.split": lambda paths, ctx, reserved: [tools.split_pdf(paths[0], ctx, reserved)],
        "vid.removeaudio": lambda paths, ctx, reserved: [tools.remove_audio(paths[0], ctx, reserved)],
        "aud.normalize": lambda paths, ctx, reserved: [tools.normalize_audio(paths[0], ctx, reserved)],
        "txt.compress": lambda paths, ctx, reserved: tools.clean_text(paths[0], ctx, reserved),
        "pdf.compress": lambda paths, ctx, reserved: [tools.compress_pdf(paths[0], ctx, reserved)],
        "doc.compress": lambda paths, ctx, reserved: [tools.compress_document(paths[0], ctx, reserved)],
    }


class _LazyTools(dict):
    def get(self, key, default=None):
        if not self:
            self.update(_tool_table())
        return super().get(key, default)


_TOOLS = _LazyTools()


def verify_output(path: Path, target: str) -> None:
    """Refuse to report success for a file that is missing, empty or unreadable."""
    from . import i18n

    if path.is_dir():
        # A document made into pictures is a folder with a picture per page.
        pages = sorted(p for p in path.iterdir() if p.is_file())
        if not pages:
            raise RuntimeError(i18n.tr("err.output_missing", name=path.name))
        for page in pages:
            verify_output(page, page.suffix.lstrip(".") or target)
        return
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(i18n.tr("err.output_missing", name=path.name))
    suffix = path.suffix.lower()
    try:
        if suffix in (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".avif", ".heic", ".ico"):
            from PIL import Image
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except Exception:
                pass
            with Image.open(path) as image:
                image.verify()
        elif suffix == ".pdf":
            import pymupdf
            with pymupdf.open(path) as document:
                if document.page_count < 1:
                    raise ValueError("no pages")
        elif suffix in (".docx", ".xlsx", ".pptx", ".epub", ".zip"):
            import zipfile
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise ValueError("corrupt member")
    except Exception as exc:
        raise RuntimeError(i18n.tr("err.output_unreadable", name=path.name)) from exc


def main() -> int:
    from . import paths

    logging.basicConfig(
        filename=str(paths.data_dir() / "eshab-worker.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    idle = float(os.environ.get("ESHAB_WORKER_IDLE_S", IDLE_EXIT_S))
    worker = Worker(lambda data: os.write(1, data), idle_exit_s=idle)
    threading.Thread(target=worker.read_loop, args=(0,), name="eshab-worker-stdin", daemon=True).start()
    while not worker.closed.wait(1.0):
        if worker.idle():
            break
    os._exit(0)
