"""Marks drawn over a photo: arrows, pen strokes, boxes, ellipses, highlights and text.

Each mark is a dict in the photo's own pixels, the same dicts the editor's
canvas draws as they are made, so what is saved is what was seen. Only Qt
GUI is needed (a QImage and a QPainter), never widgets.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF, QTextOption

from . import i18n, tools


def draw(painter: QPainter, op: dict, scale: float = 1.0, offset: QPointF | None = None) -> None:
    offset = offset or QPointF(0.0, 0.0)

    def point(x: float, y: float) -> QPointF:
        return QPointF(offset.x() + x * scale, offset.y() + y * scale)

    color = QColor(op.get("color", "#F87800"))
    width = max(1.0, float(op.get("width", 3)) * scale)
    kind = op.get("type")
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    if kind == "arrow":
        start, end = point(op["x1"], op["y1"]), point(op["x2"], op["y2"])
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head = max(10.0 * scale, width * 4.2)
        # the shaft stops where the head begins, so a thick line keeps a sharp tip
        neck = QPointF(end.x() - head * 0.8 * math.cos(angle), end.y() - head * 0.8 * math.sin(angle))
        painter.setPen(pen)
        painter.drawLine(start, neck)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        left = QPointF(end.x() - head * math.cos(angle - 0.42), end.y() - head * math.sin(angle - 0.42))
        right = QPointF(end.x() - head * math.cos(angle + 0.42), end.y() - head * math.sin(angle + 0.42))
        painter.drawPolygon(QPolygonF([end, left, right]))
    elif kind == "pen":
        points = [point(x, y) for x, y in op.get("points", [])]
        if len(points) == 1:
            points.append(points[0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))
    elif kind in ("rect", "ellipse", "highlight"):
        rect = QRectF(point(op["x1"], op["y1"]), point(op["x2"], op["y2"])).normalized()
        if kind == "highlight":
            fill = QColor(op.get("color", "#F8E400"))
            fill.setAlpha(96)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRect(rect)
        else:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "rect":
                painter.drawRect(rect)
            else:
                painter.drawEllipse(rect)
    elif kind == "text":
        font = QFont("Segoe UI")
        font.setPixelSize(max(6, int(float(op.get("size", 32)) * scale)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        text = str(op.get("text", ""))
        box = QRectF(point(op["x1"], op["y1"]), point(op.get("x2", op["x1"] + 4000), op.get("y2", op["y1"] + 4000)))
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        if any("֐" <= ch <= "ࣿ" for ch in text):
            option.setTextDirection(Qt.LayoutDirection.RightToLeft)
            option.setAlignment(Qt.AlignmentFlag.AlignRight)
        painter.drawText(box, text, option)


def render(path: Path, ops: list[dict], reserved: set[Path] | None = None) -> Path:
    """The photo with its marks, saved beside it as PNG at full size."""
    from PIL import ImageOps

    full = tools.load_image(path)
    if full.getexif().get(274, 1) != 1:
        full = ImageOps.exif_transpose(full)
    image = full.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
    painter = QPainter(qimage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    for op in ops:
        draw(painter, op)
    painter.end()
    out = tools._unique(path.parent, f"{path.stem} Annotated", ".png", reserved if reserved is not None else set())
    if not qimage.save(str(out), "PNG"):
        raise tools.EngineError(i18n.tr("err.annotate_save"))
    return out
