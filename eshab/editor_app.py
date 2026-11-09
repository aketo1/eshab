"""Eshab's editors: every tool that asks for a choice, in one Qt Quick window.

``Eshab --editor <tool> <files…>`` opens the editor in a process of its own,
so the tray never loads Pillow, PyMuPDF or a media stack. Each tool is
described here once: the preview it needs (the photo with an overlay to crop,
hide or mark it; a waveform; a video; pages or files to order; details to
read; a PDF to edit), the options it takes, and the function that does the
work (eshab/tools.py and friends, the same functions the tests cover). The
window (qml/windows/Editor.qml) is built from that description. When the work
is done the result goes to the island at the top of the screen, which shows
it like any other finished job, and the editor closes.
"""
from __future__ import annotations

import array
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QImage

from . import i18n

log = logging.getLogger("eshab.editor")

QML_DIR = Path(__file__).resolve().parent / "qml"
PREVIEW_EDGE = 1800
THUMB_EDGE = 320
LIVE_EDGE = 1200
COLORS = ["#F87800", "#E5484D", "#F5D90A", "#30A46C", "#0090FF", "#8E4EC6", "#FFFFFF", "#1C1C1E"]


# -- what a tool's options look like ------------------------------------------------------

def _t(key: str) -> str:
    return i18n.tr(key)


def choice(key, values, default, label=None, when=None, labels=None):
    return {"type": "choice", "key": key, "label": _t(label or f"ed.{key}"), "default": default, "when": when,
            "options": [{"value": v, "label": _t((labels or {}).get(v, f"ed.{key}.{v}"))} for v in values]}


def slider(key, low, high, default, step=1, label=None, unit="", when=None, centered=False):
    return {"type": "slider", "key": key, "label": _t(label or f"ed.{key}"), "min": low, "max": high,
            "step": step, "default": default, "unit": unit, "when": when, "centered": centered}


def toggle(key, default=False, label=None, when=None):
    return {"type": "toggle", "key": key, "label": _t(label or f"ed.{key}"), "default": default, "when": when}


def color(key, default, label=None, when=None):
    return {"type": "color", "key": key, "label": _t(label or "ed.color"), "default": default, "when": when, "colors": COLORS}


def text(key, default="", label=None, when=None):
    return {"type": "text", "key": key, "label": _t(label or f"ed.{key}"), "default": default, "when": when}


def number(key, low, high, default, label=None, unit="", when=None, step=1):
    return {"type": "number", "key": key, "label": _t(label or f"ed.{key}"), "min": low, "max": high,
            "default": default, "unit": _t(unit) if unit.startswith("ed.") else unit, "when": when, "step": step}


def picture(key, label=None, when=None):
    return {"type": "picture", "key": key, "label": _t(label or "ed.picture"), "default": "", "when": when}


def button(key, label):
    return {"type": "button", "key": key, "label": _t(label), "default": None, "when": None}


@dataclass
class Tool:
    preview: str                      # image | crop | boxes | annotate | order | waveform | video | info | pdf | none
    fields: list = field(default_factory=list)
    run: object = None                # (job) -> [outputs]
    live: object = None               # (editor, options) -> PIL image, for a live preview
    mode: str = ""                    # how the preview works: trim, bleep, crop, boxes, snapshots…
    hint: str = ""
    many: bool = False                # works on several files at once
    action: str = "ed.save"


@dataclass
class Job:
    files: list
    options: dict
    state: dict
    ctx: object
    reserved: set
    editor: object


def _batch(job: Job, one) -> list:
    """One file after another, each with its share of the progress."""
    from .jobs import batch_ctx

    outputs = []
    for index, path in enumerate(job.files):
        if job.ctx.cancelled():
            break
        ctx = batch_ctx(job.ctx, len(job.files), index) if len(job.files) > 1 else job.ctx
        produced = one(path, ctx)
        outputs.extend(produced if isinstance(produced, list) else [produced])
    return outputs


# -- the work of each tool -------------------------------------------------------------------

def _img_compress(job: Job):
    from . import tools

    size = job.options.get("size", "original")
    edge = None if size == "original" else int(size)
    target = int(job.options.get("target_kb", 500)) * 1024 if job.options.get("target_enabled") else None
    return _batch(job, lambda p, ctx: tools.compress_image(p, job.options.get("strength", "balanced"), edge, target, ctx, job.reserved))


def _media_compress(kind):
    def run(job: Job):
        from . import tools

        work = tools.compress_video if kind == "video" else tools.compress_audio
        return _batch(job, lambda p, ctx: work(p, job.options.get("strength", "balanced"), ctx, job.reserved))
    return run


def _written(job: Job, fields: dict) -> dict:
    """The details to write. One file shows its own details in the form, so an
    emptied field removes that detail; for several files an empty field keeps
    each file's own."""
    fields = {key: str(value).strip() for key, value in fields.items() if value is not None}
    if len(job.files) == 1:
        return fields
    return {key: value for key, value in fields.items() if value}


def _img_metadata(job: Job):
    from . import tools

    o = job.options
    fields = _written(job, {270: o.get("description", ""), 315: o.get("artist", ""), 33432: o.get("copyright", "")})

    def one(path, ctx):
        location = tools.read_location(path) if o.get("keep_location", True) else None
        return tools.write_metadata_image(path, fields, bool(o.get("strip_all")), ctx, job.reserved, location)
    return _batch(job, one)


MEDIA_KEYS = ("title", "artist", "album", "date", "genre", "track", "comment")
PDF_KEYS = ("title", "author", "subject", "keywords")


def _media_metadata(job: Job):
    from . import tools

    tags = _written(job, {key: job.options.get(key, "") for key in MEDIA_KEYS})
    return _batch(job, lambda p, ctx: tools.write_media_metadata(p, tags, bool(job.options.get("strip_all")), ctx, job.reserved))


def _pdf_metadata(job: Job):
    from . import tools

    fields = _written(job, {key: job.options.get(key, "") for key in PDF_KEYS})
    return _batch(job, lambda p, ctx: tools.write_pdf_metadata(p, fields, bool(job.options.get("strip_all")), ctx, job.reserved))


EDIT_KEYS = ("preset", "exposure", "contrast", "saturation", "temperature", "vibrance", "sharpness", "vignette", "grain")


def _img_edit(job: Job):
    from . import tools

    options = {key: job.options.get(key) for key in EDIT_KEYS if job.options.get(key) is not None}
    return _batch(job, lambda p, ctx: tools.edit_image(p, options, ctx, job.reserved))


def _live_edit(editor, options):
    from . import tools

    picture = editor.working_image(LIVE_EDGE)
    return tools._apply_edits(picture, {key: options.get(key) for key in EDIT_KEYS if options.get(key) is not None})


def _background_options(o):
    kind = o.get("fill", "color")
    if kind == "gradient":
        fill = {"type": "gradient", "from": o.get("from", "#F2A33A"), "to": o.get("to", "#5560F0"), "angle": int(o.get("angle", 135))}
    elif kind == "image" and o.get("picture"):
        fill = {"type": "image", "path": o.get("picture")}
    else:
        fill = {"type": "color", "color": o.get("color", "#FFFFFF")}
    return {"fill": fill, "aspect": o.get("aspect", "original"), "margin": int(o.get("margin", 64)),
            "radius": int(o.get("radius", 24)), "fit": "contain"}


def _img_background(job: Job):
    from . import tools

    return _batch(job, lambda p, ctx: tools.add_background(p, _background_options(job.options), ctx, job.reserved))


def _live_background(editor, options):
    """The background tool on a small copy: what it would make, quickly."""
    import tempfile

    from . import tools
    from .engines import Ctx

    with tempfile.TemporaryDirectory(prefix="eshab-bg-") as work:
        small = Path(work) / "preview.png"
        editor.working_image(LIVE_EDGE // 2).save(small)
        settings = _background_options(options)
        scale = LIVE_EDGE / 2 / max(editor.width, editor.height, 1)
        settings["margin"] = max(0, int(settings["margin"] * scale))
        settings["radius"] = max(0, int(settings["radius"] * scale))
        out = tools.add_background(small, settings, Ctx(), set())
        from PIL import Image

        with Image.open(out) as made:
            return made.copy()


def _img_crop(job: Job):
    from . import tools

    box = job.state.get("box") or {}
    x, y = int(round(box.get("x", 0))), int(round(box.get("y", 0)))
    w, h = int(round(box.get("w", 0))), int(round(box.get("h", 0)))
    if w < 1 or h < 1:
        raise ValueError(_t("ed.hint.crop"))
    return [tools.crop_image(job.files[0], (x, y, x + w, y + h), job.ctx, job.reserved)]


def _img_redact(job: Job):
    from . import tools

    mode = job.options.get("mode", "blur")
    tint = job.options.get("color", "#000000")
    boxes = [(int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"]), mode, tint) for b in job.state.get("boxes", []) if b.get("w", 0) >= 1 and b.get("h", 0) >= 1]
    if not boxes:
        raise ValueError(_t("ed.hint.boxes"))
    return [tools.redact_photo(job.files[0], boxes, job.ctx, job.reserved)]


def _img_annotate(job: Job):
    from . import annotate

    marks = job.state.get("marks", [])
    if not marks:
        raise ValueError(_t("ed.hint.annotate"))
    job.ctx.progress(0.3)
    out = annotate.render(job.files[0], marks, job.reserved)
    job.ctx.progress(1.0)
    return [out]


def _ordered(job: Job):
    order = job.state.get("order")
    if isinstance(order, list) and sorted(order) == list(range(len(job.files))):
        return [job.files[i] for i in order]
    return list(job.files)


def _img_pdf(job: Job):
    from .image_pdf import PdfOptions, create_image_pdf

    o = job.options
    # The window shows the pages in the order they will have (sorting by name
    # rearranges them there), so the order sent with the job is the one to keep.
    files = _ordered(job)
    options = PdfOptions(order="manual", rows=int(o.get("rows", 1)), columns=int(o.get("columns", 1)),
                         with_filenames=bool(o.get("with_filenames")))
    return [create_image_pdf(files, job.ctx, job.reserved, options)]


COLLAGE_KEYS = ("layout", "spacing", "padding", "corner_radius", "background", "resolution", "fit")


def _collage_options(o):
    out = {key: o.get(key) for key in COLLAGE_KEYS if o.get(key) is not None}
    if out.get("resolution") not in (None, "source"):
        out["resolution"] = int(out["resolution"])
    for key in ("spacing", "padding", "corner_radius"):
        if key in out:
            out[key] = int(out[key])
    return out


def _img_collage(job: Job):
    from . import tools

    return [tools.make_collage(_ordered(job), _collage_options(job.options), job.ctx, job.reserved)]


def _live_collage(editor, options):
    """The collage from small copies of the photos (made once), in the chosen order."""
    from . import tools
    from .engines import Ctx
    from PIL import Image

    work = editor.work_dir()
    smalls = []
    order = editor.order or list(range(len(editor.files)))
    for index in order:
        small = work / f"collage-{index}.png"
        if not small.exists():
            picture = tools.load_image(editor.files[index])
            picture.thumbnail((500, 500))
            picture.save(small)
        smalls.append(small)
    settings = _collage_options(options)
    settings["resolution"] = 600 if settings.get("layout") in ("horizontal", "vertical") else 900
    out = tools.make_collage(smalls, settings, Ctx(), set())
    try:
        with Image.open(out) as made:
            return made.copy()
    finally:
        out.unlink(missing_ok=True)


def _aud_trim(job: Job):
    from . import tools

    start, end = float(job.state.get("start", 0)), float(job.state.get("end", 0))
    if end - start < 0.05:
        raise ValueError(_t("ed.hint.trim"))
    work = tools.trim_audio if job.editor.tool_key.startswith("aud") else tools.trim_video
    return [work(job.files[0], start, end, job.ctx, job.reserved)]


def _aud_bleep(job: Job):
    from . import tools

    ranges = [(float(a), float(b)) for a, b in job.state.get("ranges", []) if float(b) - float(a) > 0.02]
    if not ranges:
        raise ValueError(_t("ed.hint.bleep"))
    return [tools.bleep_audio(job.files[0], ranges, job.ctx, job.reserved)]


def _aud_channels(job: Job):
    from . import tools

    return _batch(job, lambda p, ctx: tools.convert_channels(p, job.options.get("channels", "mono"), ctx, job.reserved))


def _aud_visualizer(job: Job):
    from . import tools

    background = Path(job.options["picture"]) if job.options.get("picture") else None
    return [tools.make_visualizer(job.files[0], job.options.get("orientation", "landscape"), background, job.ctx, job.reserved)]


def _vid_crop(job: Job):
    from . import tools

    box = job.state.get("box") or {}
    x, y, w, h = (int(round(box.get(k, 0))) for k in ("x", "y", "w", "h"))
    if w < 2 or h < 2:
        raise ValueError(_t("ed.hint.crop"))
    return [tools.crop_video(job.files[0], (x - x % 2, y - y % 2, w - w % 2, h - h % 2), job.ctx, job.reserved)]


def _vid_speed(job: Job):
    from . import tools

    return [tools.change_speed(job.files[0], float(job.options.get("speed", 1.5)), job.ctx, job.reserved)]


def _vid_snapshots(job: Job):
    from . import tools

    times = sorted({round(float(t), 3) for t in job.state.get("times", [])})
    every = float(job.options.get("every", 0) or 0)
    if not times and every > 0 and job.editor.duration > 0:
        step, moment = max(0.5, every), 0.0
        while moment < job.editor.duration - 0.05 and len(times) < 500:
            times.append(round(moment, 3))
            moment += step
    if not times:
        raise ValueError(_t("ed.hint.snapshots"))
    return list(tools.take_snapshots(job.files[0], times, job.ctx, job.reserved))


def _vid_split(job: Job):
    from . import tools

    return [tools.split_video(job.files[0], int(job.options.get("parts", 2)), job.ctx, job.reserved)]


def _vid_redact(job: Job):
    from . import tools

    boxes = [{"x": int(b["x"]), "y": int(b["y"]), "w": int(b["w"]), "h": int(b["h"]),
              "start": float(b.get("start", 0)), "end": float(b.get("end", job.editor.duration or 0))}
             for b in job.state.get("boxes", []) if b.get("w", 0) >= 2 and b.get("h", 0) >= 2]
    if not boxes:
        raise ValueError(_t("ed.hint.video_boxes"))
    mode = job.options.get("mode", "blur")
    return [tools.redact_video(job.files[0], boxes, mode, job.options.get("color", "#000000"), job.ctx, job.reserved)]


def _vid_join(job: Job):
    from . import tools

    return [tools.join_videos(_ordered(job), job.ctx, job.reserved)]


def _pdf_save(job: Job):
    from . import tools

    target = tools._unique(job.files[0].parent, f"{job.files[0].stem} Edited", ".pdf", job.reserved)
    job.ctx.progress(0.4)
    with job.editor._pdf_lock:
        if job.editor.session is None:
            raise ValueError("no PDF")
        job.editor.session.save(target)
    job.ctx.progress(1.0)
    return [target]


def _metadata_fields(kind: str) -> list:
    if kind == "image":
        return [text("description"), text("artist"), text("copyright"), toggle("keep_location", True), toggle("strip_all")]
    if kind == "pdf":
        return [text("title"), text("author"), text("subject"), text("keywords"), toggle("strip_all")]
    return [text("title"), text("artist"), text("album"), text("date"), text("genre"), text("track"), text("comment"),
            toggle("strip_all")]


def _tools() -> dict:
    strength = choice("strength", ["balanced", "strong"], "balanced")
    hide = [choice("mode", ["blur", "pixelate", "solid"], "blur"), color("color", "#1C1C1E", when={"mode": "solid"})]
    return {
        "img.compress": Tool("image", [strength, choice("size", ["original", "2560", "1920", "1280"], "original"),
                                       toggle("target_enabled"), number("target_kb", 20, 102400, 500, unit="ed.kb", when={"target_enabled": True}, step=50)],
                             _img_compress, many=True),
        "img.metadata": Tool("image", _metadata_fields("image"), _img_metadata, mode="metadata", many=True),
        "gif.metadata": Tool("image", _metadata_fields("image"), _img_metadata, mode="metadata", many=True),
        "img.edit": Tool("image", [choice("preset", ["none", "vivid", "warm", "cool", "mono", "noir", "sepia"], "none"),
                                   slider("exposure", -100, 100, 0, centered=True), slider("contrast", -100, 100, 0, centered=True),
                                   slider("saturation", -100, 100, 0, centered=True), slider("temperature", -100, 100, 0, centered=True),
                                   slider("vibrance", -100, 100, 0, centered=True), slider("sharpness", 0, 100, 0),
                                   slider("vignette", 0, 100, 0), slider("grain", 0, 100, 0)],
                         _img_edit, _live_edit, many=True),
        "img.annotate": Tool("annotate", [choice("mark", ["arrow", "pen", "rect", "ellipse", "highlight", "text"], "arrow"),
                                          color("color", "#F87800"), slider("width", 1, 40, 6, when={"mark": ["arrow", "pen", "rect", "ellipse"]}),
                                          text("text", "", when={"mark": "text"}), slider("text_size", 8, 400, 48, when={"mark": "text"})],
                             _img_annotate, hint="ed.hint.annotate"),
        "img.background": Tool("image", [choice("fill", ["color", "gradient", "image"], "color"),
                                         color("color", "#FFFFFF", when={"fill": "color"}),
                                         color("from", "#F2A33A", label="ed.from", when={"fill": "gradient"}),
                                         color("to", "#5560F0", label="ed.to", when={"fill": "gradient"}),
                                         slider("angle", 0, 360, 135, unit="°", when={"fill": "gradient"}),
                                         picture("picture", when={"fill": "image"}),
                                         choice("aspect", ["original", "1:1", "4:3", "3:2", "16:9", "9:16"], "original",
                                                labels={v: "ed.aspect.original" if v == "original" else v for v in ["original", "1:1", "4:3", "3:2", "16:9", "9:16"]}),
                                         slider("margin", 0, 512, 64, unit="px"), slider("radius", 0, 256, 24, unit="px")],
                               _img_background, _live_background, many=True),
        "img.crop": Tool("crop", [choice("aspect", ["free", "original", "1:1", "4:3", "3:2", "16:9", "9:16"], "free",
                                         labels={"free": "ed.aspect.free", "original": "ed.aspect.original", "1:1": "1:1", "4:3": "4:3",
                                                 "3:2": "3:2", "16:9": "16:9", "9:16": "9:16"})],
                         _img_crop, hint="ed.hint.crop"),
        "img.redact": Tool("boxes", hide + [button("faces", "ed.faces")], _img_redact, hint="ed.hint.boxes"),
        "img.pdf": Tool("order", [choice("order", ["manual", "name", "received"], "manual"), number("rows", 1, 6, 1),
                                  number("columns", 1, 6, 1), toggle("with_filenames")], _img_pdf, hint="ed.hint.order", many=True),
        "img.collage": Tool("image", [choice("layout", ["grid", "horizontal", "vertical", "featured"], "grid"),
                                      slider("spacing", 0, 96, 12, unit="px"), slider("padding", 0, 160, 24, unit="px"),
                                      slider("corner_radius", 0, 64, 12, unit="px", label="ed.radius"),
                                      choice("background", ["white", "black", "transparent"], "white"),
                                      choice("resolution", ["source", "2000", "1500", "1080"], "source",
                                             labels={"source": "ed.resolution.source", "2000": "2000", "1500": "1500", "1080": "1080"}),
                                      choice("fit", ["fill", "contain"], "fill")],
                            _img_collage, _live_collage, mode="collage", many=True),
        "qr.read": Tool("info", [], None, mode="qr", many=True, action="ed.copy_all"),
        "pdf.qr": Tool("info", [], None, mode="qr", many=True, action="ed.copy_all"),
        "aud.compress": Tool("waveform", [strength], _media_compress("audio"), mode="plain", many=True),
        "vid.compress": Tool("video", [strength], _media_compress("video"), mode="plain", many=True),
        "aud.metadata": Tool("waveform", _metadata_fields("media"), _media_metadata, mode="metadata", many=True),
        "vid.metadata": Tool("video", _metadata_fields("media"), _media_metadata, mode="metadata", many=True),
        "pdf.metadata": Tool("info", _metadata_fields("pdf"), _pdf_metadata, mode="metadata", many=True),
        "aud.trim": Tool("waveform", [], _aud_trim, mode="trim", hint="ed.hint.trim"),
        "aud.bleep": Tool("waveform", [], _aud_bleep, mode="bleep", hint="ed.hint.bleep"),
        "aud.channels": Tool("waveform", [choice("channels", ["mono", "stereo"], "mono")], _aud_channels, mode="plain", many=True),
        "aud.visualizer": Tool("waveform", [choice("orientation", ["landscape", "portrait", "square"], "landscape"),
                                            picture("picture")], _aud_visualizer, mode="plain"),
        "vid.trim": Tool("video", [], _aud_trim, mode="trim", hint="ed.hint.trim"),
        "vid.crop": Tool("video", [choice("aspect", ["free", "original", "1:1", "4:3", "16:9", "9:16"], "free",
                                          labels={"free": "ed.aspect.free", "original": "ed.aspect.original", "1:1": "1:1",
                                                  "4:3": "4:3", "16:9": "16:9", "9:16": "9:16"})],
                         _vid_crop, mode="crop", hint="ed.hint.crop"),
        "vid.speed": Tool("video", [choice("speed", ["0.25", "0.5", "0.75", "1.25", "1.5", "2", "3", "4"], "1.5",
                                           labels={v: v + "×" for v in ["0.25", "0.5", "0.75", "1.25", "1.5", "2", "3", "4"]})],
                          _vid_speed, mode="plain"),
        "vid.snapshots": Tool("video", [number("every", 0, 600, 0, label="ed.every", unit="ed.seconds")], _vid_snapshots,
                              mode="snapshots", hint="ed.hint.snapshots"),
        "vid.split": Tool("video", [number("parts", 2, 50, 2)], _vid_split, mode="plain"),
        "vid.redact": Tool("video", hide, _vid_redact, mode="boxes", hint="ed.hint.video_boxes"),
        "vid.join": Tool("order", [], _vid_join, mode="files", hint="ed.hint.order", many=True),
        "pdf.edit": Tool("pdf", [], _pdf_save, hint="ed.hint.pdf"),
    }


TOOLS: dict = {}


def tool(key: str) -> Tool | None:
    if not TOOLS:
        TOOLS.update(_tools())
    return TOOLS.get(key)


# -- pictures for the page ---------------------------------------------------------------------

def to_qimage(picture) -> QImage:
    """A Pillow image as a QImage the page can show."""
    rgba = picture.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


def _checker(light: str, dark: str) -> QImage:
    """The 16 px tile shown behind transparent pictures."""
    from PySide6.QtGui import QColor, QPainter

    tile = QImage(16, 16, QImage.Format.Format_RGB32)
    tile.fill(QColor(light))
    painter = QPainter(tile)
    painter.fillRect(0, 0, 8, 8, QColor(dark))
    painter.fillRect(8, 8, 8, 8, QColor(dark))
    painter.end()
    return tile


try:
    from PySide6.QtQuick import QQuickImageProvider

    class Pictures(QQuickImageProvider):
        """Pictures the window asks for by name: image://editor/<name>/<revision>.

        ``pdf/<page>/<scale>/<revision>`` is a PDF page, drawn when it is asked
        for by ``renderer`` (on Qt's loading thread for an asynchronous Image).
        """

        def __init__(self):
            super().__init__(QQuickImageProvider.ImageType.Image)
            self._lock = threading.Lock()
            self._images: dict[str, QImage] = {}
            self.renderer = None
            self._images["checker-light"] = _checker("#FFFFFF", "#E4E4E8")
            self._images["checker-dark"] = _checker("#3A3A40", "#2C2C31")

        def put(self, name: str, image: QImage) -> None:
            with self._lock:
                self._images[name] = image

        def requestImage(self, identifier, size, requested):  # noqa: N802 - Qt's name
            parts = identifier.split("/")
            image = None
            if parts[0] == "pdf" and len(parts) >= 3 and self.renderer is not None:
                try:
                    image = self.renderer(int(parts[1]), float(parts[2]))
                except Exception:
                    log.exception("could not draw %s", identifier)
            else:
                with self._lock:
                    image = self._images.get(parts[0])
            if image is None or image.isNull():
                image = QImage(1, 1, QImage.Format.Format_RGBA8888)
                image.fill(Qt.GlobalColor.transparent)
            if size is not None:
                try:
                    size.setWidth(image.width())
                    size.setHeight(image.height())
                except (AttributeError, TypeError):
                    pass
            if requested is not None and requested.width() > 0 and requested.height() > 0:
                return image.scaled(requested, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return image
except ImportError:          # pragma: no cover - Qt Quick ships with PySide6
    Pictures = None


def audio_peaks(path: Path, buckets: int = 1600) -> tuple[list[float], float]:
    """A waveform's outline (0..1 per bucket) and the length in seconds, through FFmpeg."""
    from .media import ffmpeg_path, probe

    duration = 0.0
    try:
        duration = float(probe(path).duration or 0.0)
    except Exception:
        pass
    exe = ffmpeg_path()
    if not exe:
        return [], duration
    rate = 2000
    try:
        result = subprocess.run([str(exe), "-v", "quiet", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate),
                                 "-f", "s16le", "-"], capture_output=True, timeout=180,
                                creationflags=0x08000000 if os.name == "nt" else 0)
    except Exception:
        return [], duration
    samples = array.array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    if not samples:
        return [], duration
    if not duration:
        duration = len(samples) / rate
    step = max(1, len(samples) // buckets)
    peaks = []
    for start in range(0, len(samples), step):
        chunk = samples[start:start + step]
        peaks.append(max(abs(min(chunk)), abs(max(chunk))) / 32768.0 if chunk else 0.0)
    top = max(peaks) or 1.0
    return [round(p / top, 4) for p in peaks], duration


# -- the editor --------------------------------------------------------------------------------

class Relay(QObject):
    """Signals from work threads back to the window's thread."""
    progressed = Signal(float)
    told = Signal(str)
    finished = Signal(list)
    failed = Signal(str)
    previewed = Signal(int)
    loaded = Signal()


class Editor(QObject):
    changed = Signal()
    previewChanged = Signal()
    jobChanged = Signal()
    pdfChanged = Signal()

    def __init__(self, key: str, files: list[Path], pictures=None):
        super().__init__()
        self.tool_key = key
        self.spec_tool = tool(key)
        if self.spec_tool is None:
            raise ValueError(f"no editor for {key}")
        self.files = [Path(f) for f in files if Path(f).exists()]
        if not self.spec_tool.many:
            self.files = self.files[:1]
        if not self.files:
            raise ValueError("no file")
        self.pictures = pictures
        if pictures is not None:
            pictures.renderer = self._render_page
        self._pdf_lock = threading.RLock()
        self._work_dir: Path | None = None
        self.initial: dict = {}
        self.relay = Relay()
        self.relay.progressed.connect(self._progressed)
        self.relay.told.connect(self._told)
        self.relay.finished.connect(self._finished)
        self.relay.failed.connect(self._failed)
        self.relay.previewed.connect(self._previewed)
        self.relay.loaded.connect(self.changed)
        self.relay.loaded.connect(self.jobChanged)
        self.relay.loaded.connect(self.pdfChanged)
        self.width = self.height = 0
        self.order: list[int] = []
        self.duration = 0.0
        self.video_size = (0, 0)
        self.peaks: list[float] = []
        self.rows: list[dict] = []
        self.items: list[dict] = []
        self.session = None
        self._picture = None
        self._working = None
        self._source_rev = self._preview_rev = 0
        self._preview_generation = 0
        self._busy = False
        self._progress = -1.0
        self._status = ""
        self._error = ""
        self._outputs: list[str] = []
        self._cancel = threading.Event()
        self._loading = True
        self._broken = False
        self._pdf_rev = 0
        threading.Thread(target=self._load, name="eshab-editor-load", daemon=True).start()

    # -- loading what the preview shows ----------------------------------------------------

    def _load(self) -> None:
        try:
            kind = self.spec_tool.preview
            if kind in ("image", "crop", "boxes", "annotate") and self.tool_key != "img.collage":
                self._load_picture()
            if self.tool_key == "img.collage" or kind == "order":
                self._load_items()
            if kind == "waveform":
                self.peaks, self.duration = audio_peaks(self.files[0])
            if kind == "video":
                self._load_video()
            if kind == "info" or self.spec_tool.mode == "metadata":
                self._load_rows()
            if self.spec_tool.mode == "metadata" and len(self.files) == 1:
                self._load_initial()
            if kind == "pdf":
                from .pdf_model import PdfSession

                self.session = PdfSession(self.files[0])
                self._pdf_rev += 1
            if self.spec_tool.live is not None:
                self._render_live({key: f.get("default") for key, f in self._defaults().items()})
        except Exception as exc:
            log.exception("could not open %s", self.files[0])
            self._error = str(exc) or type(exc).__name__
            self._broken = True
        self._loading = False
        self.relay.loaded.emit()

    def _defaults(self) -> dict:
        return {f["key"]: f for f in self.spec_tool.fields if f.get("key")}

    def _load_initial(self) -> None:
        """The details the file already has, so the form starts from them."""
        path = self.files[0]
        found: dict = {}
        try:
            if self.tool_key in ("img.metadata", "gif.metadata"):
                from PIL import Image

                with Image.open(path) as picture:
                    exif = picture.getexif()
                for tag, key in ((270, "description"), (315, "artist"), (33432, "copyright")):
                    value = exif.get(tag)
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", "replace")
                    if value:
                        found[key] = str(value).replace("\x00", "").strip()
            elif self.tool_key in ("aud.metadata", "vid.metadata"):
                from . import tools

                found = {key: value for key, value in tools.read_media_tags(path).items() if key in MEDIA_KEYS and value}
            elif self.tool_key == "pdf.metadata":
                import pymupdf

                with pymupdf.open(str(path)) as document:
                    meta = document.metadata or {}
                found = {key: str(meta.get(key) or "") for key in PDF_KEYS if meta.get(key)}
        except Exception:
            log.exception("could not read the details of %s", path)
        self.initial = found

    def work_dir(self) -> Path:
        """A folder for this window's scratch files, removed when it closes."""
        if self._work_dir is None:
            import tempfile

            self._work_dir = Path(tempfile.mkdtemp(prefix="eshab-editor-"))
        return self._work_dir

    def cleanup(self) -> None:
        if self._work_dir is not None:
            import shutil

            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None
        with self._pdf_lock:
            if self.session is not None:
                self.session.close()

    def _load_picture(self) -> None:
        from PIL import ImageOps

        from . import tools

        picture = tools.load_image(self.files[0])
        if picture.getexif().get(274, 1) != 1:
            picture = ImageOps.exif_transpose(picture)
        self.width, self.height = picture.size
        shown = picture.copy()
        shown.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE))
        self._picture = shown
        if self.pictures is not None:
            self.pictures.put("source", to_qimage(shown))
            self.pictures.put("preview", to_qimage(shown))
        self._source_rev += 1
        self._preview_rev += 1

    def working_image(self, edge: int):
        """A small copy of the photo for live previews."""
        if self._working is None or max(self._working.size) != min(edge, max(self._picture.size)):
            copy = self._picture.copy()
            copy.thumbnail((edge, edge))
            self._working = copy
        return self._working.copy()

    def _load_items(self) -> None:
        from . import tools

        items = []
        for index, path in enumerate(self.files):
            name = f"item{index}"
            try:
                if self.tool_key == "vid.join":
                    picture = self._frame(path, 1.0) or self._frame(path, 0.0)
                else:
                    picture = tools.load_image(path)
                    picture.thumbnail((THUMB_EDGE, THUMB_EDGE))
                if picture is not None and self.pictures is not None:
                    self.pictures.put(name, to_qimage(picture))
            except Exception:
                log.exception("no thumbnail for %s", path)
            items.append({"name": path.name, "url": f"image://editor/{name}/1", "index": index,
                          "received": index, "size": path.stat().st_size})
        self.items = items
        self.order = list(range(len(self.files)))

    @staticmethod
    def _frame(path: Path, seconds: float):
        import io

        from PIL import Image

        from .media import ffmpeg_path

        exe = ffmpeg_path()
        if not exe:
            return None
        result = subprocess.run([str(exe), "-v", "quiet", "-ss", f"{seconds:.2f}", "-i", str(path), "-frames:v", "1",
                                 "-vf", f"scale={THUMB_EDGE}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                                capture_output=True, timeout=60, creationflags=0x08000000 if os.name == "nt" else 0)
        if not result.stdout:
            return None
        return Image.open(io.BytesIO(result.stdout)).convert("RGB")

    def _load_video(self) -> None:
        from .media import probe

        info = probe(self.files[0])
        self.duration = float(info.duration or 0.0)
        video = info.video()
        if video is not None:
            width, height = video.display_size()
            self.video_size = (int(width or 0), int(height or 0))

    def _load_rows(self) -> None:
        from . import tools

        rows = []
        if self.spec_tool.mode == "qr":
            from .engines import Ctx

            for name, kind, value in tools.read_qr_codes(self.files, Ctx()):
                rows.append({"label": name + (f" · {kind}" if kind else ""), "value": value})
        else:
            for label, value in tools.read_metadata(self.files[0]):
                rows.append({"label": label, "value": value})
        self.rows = rows

    # -- what the window reads ---------------------------------------------------------------

    @Property(str, constant=True)
    def toolKey(self) -> str:
        return self.tool_key

    @Property(str, constant=True)
    def title(self) -> str:
        return i18n.tr("tool." + self.tool_key)

    @Property(str, constant=True)
    def subtitle(self) -> str:
        return self.files[0].name if len(self.files) == 1 else i18n.tr("ed.files", n=len(self.files))

    @Property(str, constant=True)
    def spec(self) -> str:
        t = self.spec_tool
        return json.dumps({"preview": t.preview, "mode": t.mode, "fields": t.fields, "hint": _t(t.hint) if t.hint else "",
                           "action": _t(t.action), "live": t.live is not None, "rtl": i18n.is_rtl(),
                           "words": {key: _t(key) for key in ("ed.cancel", "ed.save", "ed.working", "ed.close", "ed.undo",
                                                               "ed.redo", "ed.clear", "ed.delete", "ed.copy", "ed.copied",
                                                               "ed.play", "ed.pause", "ed.choose", "ed.none", "ed.start",
                                                               "ed.end", "ed.add_snapshot", "ed.rotate", "ed.duplicate",
                                                               "ed.move_up", "ed.move_down", "ed.edit_text", "ed.redact_area",
                                                               "ed.replace_image", "ed.failed", "ed.loading", "ed.nothing_found",
                                                               "ed.results", "ed.info", "ed.reset", "ed.page", "ed.compare",
                                                               "ed.before", "ed.after")}},
                          ensure_ascii=False)

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def sourceUrl(self) -> str:
        return f"image://editor/source/{self._source_rev}" if self._source_rev else ""

    @Property(str, notify=previewChanged)
    def previewUrl(self) -> str:
        return f"image://editor/preview/{self._preview_rev}" if self._preview_rev else ""

    @Property(int, notify=changed)
    def imageWidth(self) -> int:
        return self.width

    @Property(int, notify=changed)
    def imageHeight(self) -> int:
        return self.height

    @Property(str, constant=True)
    def mediaUrl(self) -> str:
        return QUrl.fromLocalFile(str(self.files[0])).toString()

    @Property(float, notify=changed)
    def mediaDuration(self) -> float:
        return self.duration

    @Property(str, constant=True)
    def beepUrl(self) -> str:
        """A second of the bleep's tone, so the window can play it over the marked parts."""
        if self.tool_key != "aud.bleep":
            return ""
        path = self.work_dir() / "bleep.wav"
        if not path.exists():
            import math
            import struct
            import wave

            rate = 44100
            samples = (int(9000 * math.sin(2 * math.pi * 1000 * i / rate)) for i in range(rate))
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(b"".join(struct.pack("<h", value) for value in samples))
        return QUrl.fromLocalFile(str(path)).toString()

    @Property(bool, notify=changed)
    def broken(self) -> bool:
        return self._broken

    @Property(int, notify=changed)
    def videoWidth(self) -> int:
        return self.video_size[0]

    @Property(int, notify=changed)
    def videoHeight(self) -> int:
        return self.video_size[1]

    @Property("QVariantList", notify=changed)
    def peaksList(self) -> list:
        return self.peaks

    @Property("QVariantList", notify=changed)
    def infoRows(self) -> list:
        return self.rows

    @Property("QVariantList", notify=changed)
    def itemList(self) -> list:
        return self.items

    @Property("QVariantMap", notify=changed)
    def initialOptions(self) -> dict:
        return self.initial

    @Property(int, constant=True)
    def fileCount(self) -> int:
        return len(self.files)

    @Property(bool, notify=jobChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(float, notify=jobChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=jobChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=jobChanged)
    def error(self) -> str:
        return self._error

    # -- live previews ---------------------------------------------------------------------------

    @Slot(str)
    def preview(self, options_json: str) -> None:
        """A tool's look on a small copy, while its options change."""
        if self.spec_tool.live is None or self._loading and self._picture is None and self.tool_key != "img.collage":
            return
        try:
            options = json.loads(options_json or "{}")
        except ValueError:
            return
        threading.Thread(target=self._render_live, args=(options,), daemon=True).start()

    def _render_live(self, options: dict) -> None:
        self._preview_generation += 1
        mine = self._preview_generation
        try:
            picture = self.spec_tool.live(self, options)
        except Exception:
            log.exception("live preview of %s", self.tool_key)
            return
        if mine != self._preview_generation:
            return                          # a newer change is on its way
        if self.pictures is not None:
            self.pictures.put("preview", to_qimage(picture))
        self.relay.previewed.emit(mine)

    def _previewed(self, _generation: int) -> None:
        self._preview_rev += 1
        self.previewChanged.emit()

    @Slot(str)
    def setOrder(self, order_json: str) -> None:
        try:
            order = [int(i) for i in json.loads(order_json)]
        except (ValueError, TypeError):
            return
        if sorted(order) == list(range(len(self.files))):
            self.order = order

    # -- the work ---------------------------------------------------------------------------------

    @Slot(str, str)
    def run(self, options_json: str, state_json: str) -> None:
        if self._busy:
            return
        if self.spec_tool.mode == "qr":
            self.copyText("\n".join(row["value"] for row in self.rows))
            return
        try:
            options = json.loads(options_json or "{}")
            state = json.loads(state_json or "{}")
        except ValueError:
            options, state = {}, {}
        if "order" in state:
            self.setOrder(json.dumps(state["order"]))
        self._busy, self._error, self._progress, self._status = True, "", -1.0, _t("ed.working")
        self._cancel.clear()
        self.jobChanged.emit()
        threading.Thread(target=self._work, args=(options, state), name="eshab-editor-job", daemon=True).start()

    def _work(self, options: dict, state: dict) -> None:
        from .engines import Ctx
        from .worker import verify_output

        ctx = Ctx(lambda value: self.relay.progressed.emit(float(value)), lambda words: self.relay.told.emit(str(words)), self._cancel)
        job = Job(self.files, options, state, ctx, set(), self)
        try:
            from . import naming

            with naming.operation_scope(self.files, i18n.tr("tool." + self.tool_key)):
                outputs = [Path(p) for p in self.spec_tool.run(job)]
            if self._cancel.is_set():
                self.relay.failed.emit("")
                return
            for output in outputs:
                if output.is_file():
                    verify_output(output, output.suffix.lstrip("."))
            self.relay.finished.emit([str(p) for p in outputs])
        except Exception as exc:
            if self._cancel.is_set():
                self.relay.failed.emit("")
                return
            log.error("%s failed: %s\n%s", self.tool_key, exc, traceback.format_exc())
            self.relay.failed.emit(str(exc) or type(exc).__name__)

    def _progressed(self, value: float) -> None:
        self._progress = value
        self.jobChanged.emit()

    def _told(self, words: str) -> None:
        self._status = words
        self.jobChanged.emit()

    def _finished(self, outputs: list) -> None:
        self._busy, self._outputs, self._progress = False, outputs, 1.0
        self.jobChanged.emit()
        announce(self.title, outputs)
        QTimer.singleShot(120, self.closeWindow)

    def _failed(self, message: str) -> None:
        self._busy = False
        self._error = message
        self._progress = -1.0
        self.jobChanged.emit()

    @Slot()
    def cancel(self) -> None:
        if self._busy:
            self._cancel.set()
        else:
            self.closeWindow()

    closeRequested = Signal()

    @Slot()
    def closeWindow(self) -> None:
        self.closeRequested.emit()

    # -- small services for the window -----------------------------------------------------------

    @Slot(str)
    def copyText(self, words: str) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(words)

    @Slot(result=str)
    def pickPicture(self) -> str:
        from PySide6.QtWidgets import QFileDialog

        chosen, _ = QFileDialog.getOpenFileName(None, _t("ed.picture"), str(self.files[0].parent),
                                                "Images (*.png *.jpg *.jpeg *.webp *.heic *.bmp *.tif *.tiff)")
        return chosen or ""

    @Slot(result=str)
    def findFaces(self) -> str:
        from . import tools

        try:
            faces = tools.detect_faces(self.files[0])
        except Exception:
            log.exception("face detection")
            faces = []
        return json.dumps([{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in faces])

    # -- the PDF editor ------------------------------------------------------------------------------
    # The document is touched from the window's thread (edits), Qt's picture
    # thread (pages being drawn) and the save; one lock keeps them in turn.

    def _pdf_change(self, change) -> str:
        with self._pdf_lock:
            if self.session is None:
                return "?"
            try:
                change()
            except Exception as exc:
                log.exception("PDF edit")
                return str(exc) or type(exc).__name__
            self._pdf_rev += 1
        self.pdfChanged.emit()
        return ""

    def _render_page(self, index: int, scale: float):
        with self._pdf_lock:
            if self.session is None or not 0 <= index < self.session.count():
                return None
            width, height = self.session.page_size(index)
            scale = max(0.05, min(scale, 6.0, 5000.0 / max(width, height, 1.0)))
            pixmap = self.session.render(index, scale)
            return QImage(pixmap.samples, pixmap.width, pixmap.height, pixmap.stride,
                          QImage.Format.Format_RGB888).copy()

    @Property(int, notify=pdfChanged)
    def pdfRevision(self) -> int:
        return self._pdf_rev

    @Property(int, notify=pdfChanged)
    def pdfCount(self) -> int:
        with self._pdf_lock:
            return self.session.count() if self.session is not None else 0

    @Property(bool, notify=pdfChanged)
    def canUndo(self) -> bool:
        return self.session is not None and self.session.can_undo()

    @Property(bool, notify=pdfChanged)
    def canRedo(self) -> bool:
        return self.session is not None and self.session.can_redo()

    @Slot(int, float, result=str)
    def pdfPage(self, index: int, scale: float) -> str:
        """The URL of a page drawn at ``scale`` pixels per point (drawn when the picture is loaded)."""
        if self.session is None or index < 0:
            return ""
        return f"image://editor/pdf/{index}/{round(max(0.05, min(scale, 6.0)), 3)}/{self._pdf_rev}"

    @Slot(int, result=str)
    def pdfPageSize(self, index: int) -> str:
        with self._pdf_lock:
            if self.session is None or not 0 <= index < self.session.count():
                return "[612, 792]"
            return json.dumps(list(self.session.page_size(index)))

    @Slot(int, result=str)
    def pdfElements(self, index: int) -> str:
        with self._pdf_lock:
            if self.session is None or not 0 <= index < self.session.count():
                return "[]"
            found = self.session.elements(index)
        return json.dumps([{"kind": e.kind, "rect": [round(v, 2) for v in e.rect], "text": e.text,
                            "size": round(e.size, 2), "color": e.color} for e in found], ensure_ascii=False)

    def _element(self, index: int, at: int):
        found = self.session.elements(index)
        return found[at] if 0 <= at < len(found) else None

    @Slot(int, int, str, result=str)
    def pdfEditText(self, index: int, at: int, words: str) -> str:
        def change():
            element = self._element(index, at)
            if element is None:
                raise ValueError(_t("ed.failed"))
            self.session.change_text(index, element, words, element.rect, element.size, element.color)
        return self._pdf_change(change)

    @Slot(int, float, float, float, float, str, float, result=str)
    def pdfAddText(self, index: int, x0: float, y0: float, x1: float, y1: float, words: str, size: float) -> str:
        if not words.strip():
            return ""
        rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        return self._pdf_change(lambda: self.session.change_text(index, None, words, rect, size, "#1C1C1E"))

    @Slot(int, int, result=str)
    def pdfDeleteElement(self, index: int, at: int) -> str:
        def change():
            element = self._element(index, at)
            if element is None:
                raise ValueError(_t("ed.failed"))
            self.session.delete_element(index, element)
        return self._pdf_change(change)

    @Slot(int, int, result=str)
    def pdfReplaceImage(self, index: int, at: int) -> str:
        chosen = self.pickPicture()
        if not chosen:
            return ""
        data = Path(chosen).read_bytes()

        def change():
            element = self._element(index, at)
            if element is None:
                raise ValueError(_t("ed.failed"))
            self.session.change_image(index, element, data, element.rect)
        return self._pdf_change(change)

    @Slot(int, float, float, float, float, result=str)
    def pdfRedact(self, index: int, x0: float, y0: float, x1: float, y1: float) -> str:
        return self._pdf_change(lambda: self.session.redact(index, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))))

    @Slot(int, result=str)
    def pdfRotate(self, index: int) -> str:
        return self._pdf_change(lambda: self.session.rotate_page(index, 90))

    @Slot(int, result=str)
    def pdfDeletePage(self, index: int) -> str:
        return self._pdf_change(lambda: self.session.delete_page(index))

    @Slot(int, result=str)
    def pdfDuplicate(self, index: int) -> str:
        return self._pdf_change(lambda: self.session.duplicate_page(index))

    @Slot(int, int, result=int)
    def pdfMove(self, index: int, offset: int) -> int:
        moved = [index]

        def change():
            moved[0] = self.session.move_page(index, offset)
        self._pdf_change(change)
        return moved[0]

    @Slot()
    def pdfUndo(self) -> None:
        self._pdf_change(lambda: self.session.undo())

    @Slot()
    def pdfRedo(self) -> None:
        self._pdf_change(lambda: self.session.redo())


def announce(title: str, outputs: list) -> None:
    """The finished job, shown by the island at the top of the screen (the tray process)."""
    if not outputs:
        return
    from .requests import forward_request

    first = Path(outputs[0])
    detail = first.name if len(outputs) == 1 else i18n.tr("progress.saved_many", n=len(outputs))
    try:
        import uuid

        forward_request({"id": uuid.uuid4().hex, "action": "notify", "title": title, "detail": detail,
                         "output": str(first), "count": len(outputs)}, 800)
    except Exception:
        log.exception("could not tell the tray")


def main(argv: list[str]) -> int:
    from . import paths

    logging.basicConfig(filename=str(paths.data_dir() / "eshab-editor.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    index = argv.index("--editor")
    key, files = argv[index + 1], [Path(f) for f in argv[index + 2:]]
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtWidgets import QApplication

    import PySide6.QtQuick  # noqa: F401 - Qt Quick must be loaded before windows are made

    app = QApplication(argv[:1])
    QLocale.setDefault(QLocale("en_US"))
    app.setApplicationName("Eshab")
    app.setWindowIcon(QIcon(str(paths.assets_dir() / "icon.ico")))
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    pictures = Pictures()
    try:
        editor = Editor(key, files, pictures)
    except Exception as exc:
        log.exception("no editor for %s", key)
        return 1
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    engine.addImageProvider("editor", pictures)
    from .app_bridge import Bridge

    bridge = Bridge()
    engine.rootContext().setContextProperty("eshab", bridge)
    engine.rootContext().setContextProperty("editor", editor)
    theme = engine.singletonInstance("Eshab", "Theme")
    if theme is not None:
        bridge.apply_theme(theme)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "windows" / "Editor.qml")))
    window = component.create()
    if window is None:
        for error in component.errors():
            log.error("Editor.qml: %s", error.toString())
        return 1
    editor.closeRequested.connect(window.close)
    snapshot = os.environ.get("ESHAB_EDITOR_SNAPSHOT")
    if snapshot:
        # A check of a build: draw the window off-screen, keep a picture of it, quit.
        window.setFlags(window.flags() | Qt.WindowType.Tool)
        window.setPosition(-4000, 3000)

        def take() -> None:
            if editor.loading:
                QTimer.singleShot(200, take)
                return
            QTimer.singleShot(1500, lambda: (window.grabWindow().save(snapshot), app.quit()))
        QTimer.singleShot(300, take)
    window.show()
    if not snapshot:
        window.requestActivate()
    code = app.exec()
    editor.cleanup()
    del window, component
    return code
