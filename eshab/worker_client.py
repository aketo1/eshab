"""The tray's side of the worker process (see ``eshab/worker.py``).

The worker is started when the first job arrives and is left to exit on
its own when it has been idle for a minute; the next job starts it again.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from . import i18n, paths

log = logging.getLogger("eshab")


def worker_command() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, ["--worker"]
    return sys.executable, [str(paths.app_root() / "main.py"), "--worker"]


class WorkerClient(QObject):
    status = Signal(str, str)          # job id, text
    progress = Signal(str, float)      # job id, 0..1 (negative: indeterminate)
    finished = Signal(str, list)       # job id, output paths
    failed = Signal(str, str)          # job id, message
    cancelled = Signal(str)            # job id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._buffer = b""
        self._running: set[str] = set()

    # -- public ----------------------------------------------------------

    def convert(self, files, target: str) -> str:
        return self._submit({"op": "convert", "paths": [str(Path(f)) for f in files], "target": target})

    def tool(self, files, key: str) -> str:
        return self._submit({"op": "tool", "paths": [str(Path(f)) for f in files], "tool": key})

    def cancel(self, job_id: str) -> None:
        if job_id in self._running:
            self._send({"op": "cancel", "id": job_id})

    def busy(self) -> bool:
        return bool(self._running)

    def shutdown(self) -> None:
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.closeWriteChannel()  # the worker exits when its stdin closes
            if not process.waitForFinished(1500):
                process.kill()

    # -- process ---------------------------------------------------------

    def _submit(self, request: dict) -> str:
        job_id = uuid.uuid4().hex[:10]
        request["id"] = job_id
        self._running.add(job_id)
        self._send(request)
        return job_id

    def _ensure(self) -> QProcess:
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            return process
        process = QProcess(self)
        program, arguments = worker_command()
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._exited)
        self._buffer = b""
        process.start()
        if not process.waitForStarted(5000):
            log.error("Worker failed to start: %s", process.errorString())
        self._process = process
        return process

    def _send(self, request: dict) -> None:
        process = self._ensure()
        process.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))

    def _read(self) -> None:
        process = self.sender()
        if not isinstance(process, QProcess):
            return
        self._buffer += bytes(process.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if line.strip():
                try:
                    self._dispatch(json.loads(line))
                except Exception:
                    log.exception("Bad worker event: %r", line[:200])

    def _dispatch(self, event: dict) -> None:
        job_id = str(event.get("id", ""))
        kind = event.get("event")
        if kind == "status":
            self.status.emit(job_id, str(event.get("text", "")))
        elif kind == "progress":
            self.progress.emit(job_id, float(event.get("value", 0.0)))
        elif kind == "done":
            self._running.discard(job_id)
            self.finished.emit(job_id, list(event.get("outputs", [])))
        elif kind == "error":
            self._running.discard(job_id)
            self.failed.emit(job_id, str(event.get("message", "")))
        elif kind == "cancelled":
            self._running.discard(job_id)
            self.cancelled.emit(job_id)

    def _exited(self, code: int, status) -> None:
        process = self.sender()
        if process is self._process:
            self._process = None
        orphans, self._running = self._running, set()
        if orphans:
            log.error("Worker exited (code %s) with %d job(s) running", code, len(orphans))
        for job_id in orphans:
            self.failed.emit(job_id, i18n.tr("err.worker_stopped"))
        if isinstance(process, QProcess):
            process.deleteLater()
