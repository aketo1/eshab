"""The visual studio: native file engines, a transparent Chromium surface.

The bridge accepts only files selected in this window. All edits and exports
stay local; the view cannot navigate to the network.
"""
from __future__ import annotations

import base64
import ctypes
import io
import json
import math
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    _render_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for _flag in ("--disable-gpu", "--disable-gpu-compositing"):
        if _flag not in _render_flags.split():
            _render_flags += " " + _flag
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _render_flags.strip()

from PySide6.QtCore import QObject, QPointF, QRectF, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from . import actions, catalog, i18n, naming, paths, progress, theme, tools
from .pdf_model import PdfSession
from .liquid_ui import WindowControl

_OPEN = []


def clear_glass_window(widget):
    """Preserve the clear alpha surface without nested backdrop rendering."""
    return theme.glass_window(widget)


def _asset_root():
    import sys
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "eshab" / "ui"


class _LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in {"file", "qrc", "data", "blob", "about"}:
            info.block(True)


class _Page(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main_frame):
        return url.scheme() in {"file", "qrc", "data", "about"} and (
            not main_frame or Path(url.toLocalFile()).resolve() == (_asset_root() / "studio.html").resolve()
        )

    def javaScriptConsoleMessage(self, level, message, line, source):
        import logging
        logging.getLogger("eshab.studio").debug("UI %s:%s %s", source, line, message)


def export_image(source: Path, options: dict, operations: list, output: Path, ctx):
    """Replay normalized preview operations at the original resolution."""
    from PIL import Image, ImageDraw, ImageOps
    from .editors.base import pil_to_qimage
    from .editors.ui.canvas import _draw_op

    image = ImageOps.exif_transpose(tools.load_image(source)).convert("RGBA")
    image = tools._apply_edits(image, options)
    for index, operation in enumerate(operations):
        kind = operation["type"]
        width, height = image.size
        if kind == "crop":
            x, y, w, h = operation["box"]
            box = (round(x * width), round(y * height), round((x + w) * width), round((y + h) * height))
            image = image.crop(box)
        elif kind == "rotate":
            image = image.transpose(Image.Transpose.ROTATE_270)
        elif kind == "flip":
            image = ImageOps.mirror(image)
        elif kind == "background":
            background = Image.new("RGBA", image.size, operation["color"])
            background.alpha_composite(image)
            image = background
        elif kind == "redact":
            x, y, w, h = operation["box"]
            box = (round(x * width), round(y * height), round((x + w) * width), round((y + h) * height))
            if operation.get("effect") == "pixelate":
                region = image.crop(box)
                region = region.resize(
                    (max(1, region.width // 18), max(1, region.height // 18)),
                    Image.Resampling.BILINEAR,
                ).resize(region.size, Image.Resampling.NEAREST)
                image.paste(region, box)
            else:
                ImageDraw.Draw(image).rectangle(box, fill=operation.get("color", "#25252a"))
        else:
            op = dict(operation)
            for key in ("x", "x1", "x2"):
                if key in op:
                    op[key] *= width
            for key in ("y", "y1", "y2"):
                if key in op:
                    op[key] *= height
            if "points" in op:
                op["points"] = [(x * width, y * height) for x, y in op["points"]]
            op["width"] = max(1, float(op.get("width", 0.004)) * width)
            op["size"] = max(8, float(op.get("size", 0.035)) * width)
            if kind == "text":
                qimage = pil_to_qimage(image)
                painter = QPainter(qimage)
                from PySide6.QtCore import QRectF
                from PySide6.QtGui import QFont, QFontMetricsF

                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                font = QFont("Segoe UI")
                font.setPixelSize(round(op["size"]))
                painter.setFont(font)
                painter.setPen(QColor(op.get("color", "#222222")))
                metrics = QFontMetricsF(font)
                lines = str(op.get("text", "")).splitlines() or [""]
                max_line_w = max((metrics.horizontalAdvance(line) for line in lines), default=20.0)
                text_width = max(20.0, max_line_w + 8.0)
                flags = (
                    Qt.AlignmentFlag.AlignRight
                    if any("\u0600" <= c <= "\u06ff" for c in op["text"])
                    else Qt.AlignmentFlag.AlignLeft
                )
                painter.drawText(
                    QRectF(op["x"], op["y"], text_width, max(op["size"] * 2 * len(lines), height - op["y"])),
                    flags | Qt.AlignmentFlag.AlignTop,
                    op["text"],
                )
                painter.end()
            else:
                qimage = pil_to_qimage(image)
                painter = QPainter(qimage)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                from PySide6.QtCore import QPointF

                _draw_op(painter, op, 1, QPointF())
                painter.end()
            from PySide6.QtCore import QBuffer, QIODevice

            qbuffer = QBuffer()
            qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
            qimage.save(qbuffer, "PNG")
            image = Image.open(io.BytesIO(bytes(qbuffer.data()))).convert("RGBA")
        ctx.progress((index + 1) / max(1, len(operations) + 1))
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        flattened = Image.new("RGB", image.size, "white")
        flattened.paste(image, mask=image.getchannel("A"))
        flattened.save(output, quality=94, optimize=True)
    else:
        image.save(output)
    ctx.progress(1)
    return output


class StudioBridge(QObject):
    response = Signal(str, str)
    event = Signal(str, str)

    def __init__(self, host, mode="home", source=None, tool="select"):
        super().__init__(host)
        self.host = host
        self.mode = mode
        self.source = Path(source).resolve() if source else None
        self.initial_tool = tool
        self.files = [self.source] if self.source else []
        self.allowed = set(self.files)
        self.session = PdfSession(self.source) if mode == "pdf" else None
        self.page_index = 0
        self.elements = []
        self.windows = []
        self.pdf_labels = []
        self._pdf_label_history = []
        self._pdf_label_future = []
        self._audio_data = None
        self._audio_loading = False
        self._audio_end = 0.
        self._audio_start = 0.
        self._preview_active = False
        self._preview_pending = []
        progress.events().changed.connect(self._task_changed)
        if mode == "audio":
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.audio_output.setVolume(.85)
            self.player.setAudioOutput(self.audio_output)
            self.player.setSource(QUrl.fromLocalFile(str(self.source)))
            self._audio_clock = QTimer(self)
            self._audio_clock.setInterval(40)
            self._audio_clock.timeout.connect(self._audio_tick)
            self.player.errorOccurred.connect(self._audio_error)

    def emit_event(self, name, data):
        self.event.emit(name, json.dumps(data, ensure_ascii=False))

    @Slot(object, object)
    def _task_changed(self, owner, task):
        if owner is self.host:
            self.emit_event("task", task)

    @Slot(str, str)
    def request(self, identifier, payload):
        try:
            args = json.loads(payload)
            method = args.pop("method")
            if method == "adjustmentPreview" and self.mode == "image":
                self._preview_pending.append((identifier, args))
                self._start_preview()
                return
            result = self.dispatch(method, args)
            self.response.emit(identifier, json.dumps({"ok": True, "value": result}, ensure_ascii=False))
        except Exception as exc:
            import logging
            logging.getLogger("eshab").exception("Studio operation failed")
            self.response.emit(identifier, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))

    def _start_preview(self):
        if self._preview_active or not self._preview_pending:
            return
        from .jobs import Job
        self._preview_active = True
        pending, self._preview_pending = self._preview_pending, []
        identifier, args = pending[-1]
        # Resolve superseded requests without assigning a different preview to
        # their signature. Only the newest queued adjustment consumes CPU.
        for skipped, _ in pending[:-1]:
            self.response.emit(skipped, json.dumps({"ok": True, "value": None}))
        image = self._preview_image
        options = args.get("options", {})
        def render_preview(ctx):
            result = tools._apply_edits(image, options)
            buffer = io.BytesIO()
            result.save(buffer, "PNG")
            return ["data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()]
        job = Job(render_preview, QApplication.instance())
        job.setProperty("request_id", identifier)
        job.finished.connect(self._preview_ready)
        job.failed.connect(self._preview_failed)
        job.finished.connect(job.deleteLater)
        job.failed.connect(job.deleteLater)
        job.start()

    @Slot(list)
    def _preview_ready(self, result):
        self._last_preview = result[0]
        self.response.emit(self.sender().property("request_id"), json.dumps({"ok": True, "value": result[0]}))
        self._preview_active = False
        self._start_preview()

    @Slot(str)
    def _preview_failed(self, message):
        self.response.emit(self.sender().property("request_id"), json.dumps({"ok": False, "error": str(message)}))
        self._preview_active = False
        self._start_preview()

    def _check(self, path):
        value = Path(path).resolve()
        if value not in self.allowed:
            raise ValueError("Choose this file before opening it.")
        return value

    def add_files(self, names):
        self.files = list(dict.fromkeys(self.files + [Path(name).resolve() for name in names if Path(name).is_file()]))
        self.allowed.update(self.files)
        self.emit_event("files", self.file_items())

    def drop_files(self, names):
        incoming = [Path(name).resolve() for name in names if Path(name).is_file()]
        self.add_files(incoming)
        if self.mode != "home" and incoming:
            family = catalog.family_of(incoming[0])
            if family in {"image", "pdf", "audio"}:
                self._track(open_studio(family, incoming[0], controller=self.host.controller))
            elif self.host.controller:
                self.host.controller.open_home()
                self.host.controller._home.bridge.add_files(incoming)

    def file_items(self):
        return [
            {
                "path": str(p),
                "name": p.name,
                "ext": p.suffix[1:].upper(),
                "family": catalog.family_of(p) or "other",
                "size": p.stat().st_size,
            }
            for p in self.files
            if p.is_file()
        ]

    def _track(self, window):
        if window:
            self.windows.append(window)
            if self.host.controller:
                self.host.controller._track(window)

    def dispatch(self, method, args):
        if method == "init":
            data = {
                "mode": self.mode,
                "tool": self.initial_tool,
                "language": i18n.current_language(),
                "dark": theme.is_dark(),
                "design": theme.design_tokens(),
                "version": paths.APP_VERSION,
                "brand": "data:image/png;base64," + base64.b64encode((paths.assets_dir() / "icon.png").read_bytes()).decode(),
                "files": self.file_items(),
                "tasks": progress.tasks_for(self.host),
            }
            if self.mode == "image":
                from PIL import ImageOps
                image = ImageOps.exif_transpose(tools.load_image(self.source))
                data["width"], data["height"] = image.size
                image.thumbnail((1800, 1800))
                self._preview_image = image.convert("RGBA")
                buffer = io.BytesIO()
                image.convert("RGBA").save(buffer, "PNG")
                data["image"] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
                self._last_preview = data["image"]
            if self.session:
                data["pdf"] = self.pdf_page()
            if self.mode == "audio":
                data["audio"] = self._audio_data
                if not self._audio_loading and self._audio_data is None:
                    self._audio_loading = True
                    QTimer.singleShot(0, self._load_audio)
            return data
        if method == "adjustmentPreview" and self.mode == "image":
            image = tools._apply_edits(self._preview_image, args.get("options", {}))
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        if method == "pick":
            filters = {
                "image": "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.heic *.heif *.gif)",
                "audio": "Audio (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.opus *.aiff *.wma)",
                "pdf": "PDF (*.pdf)",
                "video": "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)",
            }
            names, _ = QFileDialog.getOpenFileNames(self.host, i18n.tr("home.choose"), "", filters.get(args.get("family"), "All files (*)"))
            self.add_files(names)
            return {"files": self.file_items(), "picked": [str(Path(name).resolve()) for name in names]}
        if method == "clear" and self.mode == "home":
            self.files.clear()
            self.allowed.clear()
            self.emit_event("files", [])
            return []
        if method == "options":
            selection = [self._check(p) for p in args["files"]]
            return {
                "formats": [
                    {"id": c.target_ext, "count": len(catalog.conversion_paths(c.target_ext, selection))}
                    for c in catalog.conversions_for(selection)
                ],
                "tools": [{"id": t.id, "label": i18n.tr("tool." + t.id)} for t in catalog.tools_for(selection)],
            }
        if method == "edit":
            source = self._check(args["path"])
            family = catalog.family_of(source)
            if family not in {"image", "pdf", "audio"}:
                raise ValueError(i18n.tr("home.no_tools"))
            self._track(open_studio(family, source, controller=self.host.controller))
            return True
        if method == "shelf":
            from .file_actions import show_shelf
            show_shelf([self._check(path) for path in args.get("files", [])])
            return True
        if method == "taskAction":
            return progress.task_action(self.host, str(args["id"]), str(args["action"]))
        if method == "audioReload" and self.mode == "audio":
            if not self._audio_loading:
                self._audio_loading = True
                QTimer.singleShot(0, self._load_audio)
            return True
        if method in {"audioPlay", "audioStop", "audioSeek", "saveAudio"} and self.mode == "audio":
            if method == "audioStop":
                self.player.pause()
                self._audio_clock.stop()
                self._audio_tick()
                return True
            if not self._audio_data:
                raise ValueError("انتظر تجهيز الصوت" if i18n.is_rtl() else "Wait for the audio to load")
            duration = self._audio_data["duration"]
            start, end = float(args.get("start", 0)), float(args.get("end", duration))
            if not all(math.isfinite(value) for value in (start, end)) or start < 0 or end > duration + .001 or end - start < .05:
                raise ValueError(i18n.tr("msg.range_too_short"))
            self._audio_start, self._audio_end = start, min(end, duration)
            if method in {"audioPlay", "audioSeek"}:
                position = float(args.get("position", start))
                if not math.isfinite(position):
                    raise ValueError("Invalid playback position")
                position = max(start, min(end, position))
                self.player.setPosition(round(position * 1000))
                if method == "audioPlay":
                    self.player.play()
                    self._audio_clock.start()
                return True
            self.player.pause()
            self._audio_clock.stop()
            window = progress.run_job(i18n.tr("action.trimming", name=self.source.name),
                                      lambda ctx: [tools.trim_audio(self.source, start, end, ctx, set())], parent=self.host)
            window.job.finished.connect(self._saved_audio)
            window.job.failed.connect(self._save_audio_error)
            self._track(window)
            return True
        if method == "convert":
            selection = [self._check(p) for p in args["files"]]
            subset = catalog.conversion_paths(args["target"], selection)
            if not subset:
                raise ValueError(i18n.tr("home.no_conversion"))
            self._track(actions.run_conversions(subset, args["target"], self.host))
            return True
        if method == "tool":
            selection = [self._check(p) for p in args["files"]]
            valid = {t.id for t in catalog.tools_for(selection)}
            if args["key"] not in valid:
                raise ValueError(i18n.tr("home.no_tools"))
            self._track(actions.run_tool(catalog.tool_paths(args["key"], selection), args["key"], self.host))
            return True
        if method == "saveImage":
            if self.mode != "image":
                raise ValueError("No image is open")
            extension = args.get("format", "png")
            if extension not in {"png", "jpg", "webp"}:
                raise ValueError("Invalid output format")
            options, operations = args.get("options", {}), args.get("operations", [])
            labels = []
            image_labels = {
                "crop": ("قص", "crop"),
                "rotate": ("تدوير", "rotate"),
                "flip": ("قلب", "flip"),
                "text": ("نص", "text"),
                "redact": ("حجب", "redact"),
                "background": ("خلفية", "background"),
            }
            for operation in operations:
                pair = image_labels.get(operation["type"], ("رسم", "drawing"))
                label = pair[0 if i18n.is_rtl() else 1]
                if label not in labels:
                    labels.append(label)
            if any(value not in (0, "none", None) for value in options.values()):
                labels.append("ألوان" if i18n.is_rtl() else "color")
            descriptor = " + ".join(labels) or ("حفظ نسخة" if i18n.is_rtl() else "copy")
            output = naming.edited_path(self.source, descriptor, "." + extension)
            window = progress.run_job(
                i18n.tr("action.editing", name=self.source.name),
                lambda ctx: [export_image(self.source, options, operations, output, ctx)],
                parent=self.host,
            )
            window.job.finished.connect(
                lambda outputs: self.emit_event("saved", {"path": str(outputs[0])}) if outputs else None
            )
            window.job.failed.connect(lambda message: self.emit_event("error", {"message": str(message)}))
            self._track(window)
            return str(output)
        if method == "reveal":
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(args["path"]).parent)))
            return True
        if method == "settings":
            if self.host.controller:
                self.host.controller.open_settings()
            else:
                from .settings_window import open_settings
                self._track(open_settings(self.host))
            return True
        if method == "window":
            action = args.get("action")
            if action == "close":
                self.host._web_close_authorized = True
                self.host.close()
            elif action == "minimize":
                self.host.showMinimized()
            elif action == "maximize":
                self.host.showNormal() if self.host.isMaximized() else self.host.showMaximized()
            elif action == "drag":
                self.host.windowHandle().startSystemMove()
            return True
        if method.startswith("pdf") and self.session:
            return self.pdf_command(method, args)
        raise ValueError("Unknown studio action")

    def _load_audio(self):
        from .jobs import Job
        from .editors.audio import audio_peaks

        source = self.source
        def analyze(ctx):
            duration = tools.probe_duration_seconds(source) or 0.
            if duration <= 0:
                raise ValueError("تعذرت قراءة مدة الصوت" if i18n.is_rtl() else "Could not read audio duration")
            peaks = audio_peaks(source, duration=duration)
            if not peaks:
                raise ValueError("تعذر تجهيز موجة الصوت" if i18n.is_rtl() else "Could not decode the audio waveform")
            return [{"duration": duration, "peaks": peaks}]
        self._analysis_job = Job(analyze, QApplication.instance())
        self._analysis_job.finished.connect(self._audio_ready)
        self._analysis_job.failed.connect(self._audio_load_error)
        self._analysis_job.finished.connect(self._analysis_job.deleteLater)
        self._analysis_job.failed.connect(self._analysis_job.deleteLater)
        self._analysis_job.start()

    @Slot(list)
    def _audio_ready(self, result):
        self._audio_loading = False
        self._audio_data = result[0]
        self._audio_end = self._audio_data["duration"]
        self.emit_event("audioReady", self._audio_data)

    @Slot(str)
    def _audio_load_error(self, message):
        self._audio_loading = False
        self.emit_event("audioError", {"message": message})

    @Slot(list)
    def _saved_audio(self, outputs):
        if outputs:
            self.allowed.update(Path(path).resolve() for path in outputs)
            self.emit_event("saved", {"path": str(outputs[0])})

    @Slot(str)
    def _save_audio_error(self, message):
        self.emit_event("error", {"message": str(message)})

    def _audio_error(self, error, message):
        self._audio_clock.stop()
        self.emit_event("audioError", {"message": str(message)})

    def _audio_tick(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.position() / 1000 >= self._audio_end:
            self.player.pause()
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.emit_event("audioPosition", {"position": self.player.position() / 1000, "playing": playing})
        if not playing:
            self._audio_clock.stop()

    def pdf_page(self):
        pix = self.session.render(self.page_index, 1.4)
        width, height = self.session.page_size(self.page_index)
        self.elements = self.session.elements(self.page_index)
        return {
            "image": "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode(),
            "width": width,
            "height": height,
            "page": self.page_index,
            "count": self.session.count(),
            "dirty": self.session.dirty,
            "undo": self.session.can_undo(),
            "redo": self.session.can_redo(),
            "elements": [
                {"id": i, "kind": e.kind, "rect": list(e.rect), "text": e.text, "size": e.size, "color": e.color}
                for i, e in enumerate(self.elements)
            ],
        }

    def pdf_command(self, method, args):
        previous_labels = list(self.pdf_labels)
        before_snapshot = self.session.history[-1] if self.session.history else None
        if method == "pdfPage":
            self.page_index = max(0, min(self.session.count() - 1, int(args["page"])))
        elif method == "pdfText":
            element = self.elements[int(args["id"])] if args.get("id") is not None else None
            rect = tuple(args["rect"])
            size = max(4, min(200, float(args.get("size", element.size if element else 16))))
            text = str(args.get("text", ""))
            if not text.strip():
                if element:
                    self.session.delete_element(self.page_index, element)
            else:
                for attempt in range(5):
                    try:
                        self.session.change_text(
                            self.page_index,
                            element,
                            text,
                            rect,
                            size,
                            args.get("color", element.color if element else "#222222"),
                        )
                        break
                    except ValueError:
                        if attempt == 4:
                            raise
                        x0, y0, x1, y1 = rect
                        page_w, page_h = self.session.page_size(self.page_index)
                        rect = (
                            x0,
                            y0,
                            min(page_w - 4, max(x1 + 60, x0 + len(text) * size * 0.55)),
                            min(page_h - 4, y1 + size * 1.5),
                        )
        elif method == "pdfDelete":
            self.session.delete_element(self.page_index, self.elements[int(args["id"])])
        elif method == "pdfMove":
            element = self.elements[int(args["id"])]
            if element.kind == "image":
                image = self.session.image_bytes(self.page_index, element)
                self.session.change_image(self.page_index, element, image, tuple(args["rect"]))
        elif method == "pdfRedact":
            self.session.redact(self.page_index, tuple(args["rect"]))
        elif method == "pdfUndo":
            if self.session.can_undo() and self._pdf_label_history:
                self._pdf_label_future.append(list(self.pdf_labels))
                self.pdf_labels = self._pdf_label_history.pop()
            self.session.undo()
        elif method == "pdfRedo":
            if self.session.can_redo() and self._pdf_label_future:
                self._pdf_label_history.append(list(self.pdf_labels))
                self.pdf_labels = self._pdf_label_future.pop()
            self.session.redo()
        elif method == "pdfRotate":
            self.session.rotate_page(self.page_index)
        elif method == "pdfDuplicate":
            self.session.duplicate_page(self.page_index)
        elif method == "pdfDeletePage":
            self.session.delete_page(self.page_index)
            self.page_index = min(self.page_index, self.session.count() - 1)
        elif method == "pdfImage":
            name, _ = QFileDialog.getOpenFileName(
                self.host, i18n.tr("pdfedit.add_image"), "", i18n.tr("pdfedit.images_filter")
            )
            if name:
                from PIL import Image
                with Image.open(name) as image:
                    w, h = image.size
                page_w, _ = self.session.page_size(self.page_index)
                target_w = min(200, page_w * 0.5)
                element = self.elements[int(args["id"])] if args.get("id") is not None else None
                rect = element.rect if element else (40, 80, 40 + target_w, 80 + target_w * h / w)
                self.session.change_image(self.page_index, element, Path(name).read_bytes(), rect)
        elif method == "pdfSave":
            descriptor = " + ".join(self.pdf_labels) or ("حفظ نسخة" if i18n.is_rtl() else "copy")
            output = naming.edited_path(self.source, descriptor, ".pdf")
            self.session.save(output)
            self.allowed.add(output)
            self.emit_event("saved", {"path": str(output)})
            return str(output)
        else:
            raise ValueError("Unknown PDF operation")
        label_pairs = {
            "pdfText": ("نص", "text"),
            "pdfDelete": ("حذف عنصر", "delete element"),
            "pdfMove": ("تحريك صورة", "move image"),
            "pdfRedact": ("حجب", "redact"),
            "pdfRotate": ("تدوير صفحة", "rotate page"),
            "pdfDuplicate": ("تكرار صفحة", "duplicate page"),
            "pdfDeletePage": ("حذف صفحة", "delete page"),
            "pdfImage": ("صورة", "image"),
        }
        if method in label_pairs and self.session.history and self.session.history[-1] is not before_snapshot:
            self._pdf_label_history.append(previous_labels)
            self._pdf_label_history = self._pdf_label_history[-len(self.session.history):]
            self._pdf_label_future.clear()
            label = label_pairs[method][0 if i18n.is_rtl() else 1]
            if label not in self.pdf_labels:
                self.pdf_labels.append(label)
        return self.pdf_page()


class _View(QWebEngineView):
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.window().bridge.drop_files([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class StudioWindow(QWidget):
    def __init__(self, mode="home", source=None, controller=None, tool="select"):
        super().__init__()
        self.controller = controller
        self._web_close_authorized = False
        self.setWindowTitle((Path(source).name + " · " if source else "") + i18n.tr("app.name") + " · " + paths.APP_VERSION)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, mode != "home")
        self.setMinimumSize(880, 620)
        self.resize(1180, 820)
        self._acrylic = False
        self._backdrop_dark = False
        self.bridge = StudioBridge(self, mode, source, tool)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = _View(self)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.profile = QWebEngineProfile(self.view)
        self.page = _Page(self.profile, self.view)
        self.page.setBackgroundColor(QColor(0, 0, 0, 0))
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self._interceptor = _LocalOnly(self.page)
        self.page.profile().setUrlRequestInterceptor(self._interceptor)
        self.view.setPage(self.page)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("studio", self.bridge)
        self.page.setWebChannel(self.channel)
        layout.addWidget(self.view)
        self.window_buttons = QWidget(self)
        buttons_layout = QHBoxLayout(self.window_buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(5)
        self.window_buttons.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        buttons_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        for kind in ("minimize", "maximize", "close"):
            button = WindowControl(kind, self.window_buttons)
            buttons_layout.addWidget(button)
            if kind == "close":
                button.clicked.connect(lambda: self.page.runJavaScript("guarded(closeWindow)()"))
            elif kind == "minimize":
                button.clicked.connect(self.showMinimized)
            else:
                button.clicked.connect(lambda: self.showNormal() if self.isMaximized() else self.showMaximized())
        self.window_buttons.setFixedSize(124, 32)
        self.window_buttons.raise_()
        theme.add_theme_listener(self._theme_changed)
        self.view.load(QUrl.fromLocalFile(str(_asset_root() / "studio.html")))

    def _theme_changed(self, dark):
        if self._backdrop_dark != bool(dark):
            self._acrylic = clear_glass_window(self)
            self._backdrop_dark = bool(dark)
        self.bridge.emit_event("theme", {"dark": bool(dark), "design": theme.design_tokens(dark)})
        for button in self.window_buttons.findChildren(WindowControl):
            button.update()
        self.update()

    def present(self):
        area = self.screen().availableGeometry()
        self.resize(min(1180, area.width() - 40), min(820, area.height() - 60))
        self.move(area.center() - self.rect().center())
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._acrylic = clear_glass_window(self)
        self._backdrop_dark = theme.is_dark()
        self.window_buttons.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "window_buttons"):
            self.window_buttons.move(20 if i18n.is_rtl() else self.width() - 144, 31)
            self.window_buttons.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), theme.window_tint(theme.is_dark()))
        painter.end()

    def closeEvent(self, event):
        if self.bridge.mode in {"image", "audio"} and not self._web_close_authorized:
            event.ignore()
            self.page.runJavaScript("guarded(closeWindow)()")
            return
        if self.bridge.mode == "audio":
            self.bridge.player.stop()
            self.bridge._audio_clock.stop()
        if self.bridge.session and self.bridge.session.dirty:
            choice = QMessageBox.question(
                self,
                i18n.tr("app.name"),
                i18n.tr("pdfedit.unsaved"),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.StandardButton.Save:
                try:
                    self.bridge.pdf_command("pdfSave", {})
                except Exception as exc:
                    QMessageBox.warning(self, i18n.tr("app.name"), str(exc))
                    event.ignore()
                    return
        if self.bridge.session:
            self.bridge.session.close()
        if self in _OPEN:
            _OPEN.remove(self)
        if self.bridge.mode != "home":
            theme.remove_theme_listener(self._theme_changed)
        super().closeEvent(event)


def open_studio(mode="home", source=None, controller=None, tool="select"):
    window = StudioWindow(mode, source, controller, tool)
    _OPEN.append(window)
    window.present()
    return window
