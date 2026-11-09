"""Draw Eshab's icons with the liquid glass kit.

Writes assets/icon.png, assets/icon.ico, assets/tray.png and assets/tray.ico.
Run from the repository root:  python scripts/make_icon.py
"""

import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from eshab import glass  # noqa: E402


def to_pil(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def tile(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 512.0
    rect = QRectF(28 * s, 28 * s, 456 * s, 456 * s)
    shape = QPainterPath()
    shape.addRoundedRect(rect, 112 * s, 112 * s)
    base = QLinearGradient(rect.topLeft(), rect.bottomRight())
    base.setColorAt(0.0, QColor("#4A4A50"))
    base.setColorAt(0.55, QColor("#1E1E22"))
    base.setColorAt(1.0, QColor("#0B0B0D"))
    p.fillPath(shape, base)
    p.save()
    p.setClipPath(shape)
    light = QRadialGradient(QPointF(rect.left() + rect.width() * 0.3, rect.top() + rect.height() * 0.15),
                            rect.width() * 0.7)
    light.setColorAt(0.0, QColor(255, 255, 255, 60))
    light.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(rect, light)
    p.restore()
    center = QPointF(256 * s, 262 * s)
    # Three drops on the ring: the wheel itself.
    for angle, radius in ((-90, 46), (30, 40), (150, 40)):
        point = QPointF(center.x() + math.cos(math.radians(angle)) * 150 * s,
                        center.y() + math.sin(math.radians(angle)) * 150 * s)
        glass.drop_shadow(p, point, radius * s, QColor(0, 0, 0, 110), lift=8 * s)
        glass.paint_glass(p, glass.circle(point, radius * s), True, None, magnify=1.0, lift=0.8)
    # The orb with a liquid neck to the top drop.
    top = QPointF(center.x(), center.y() - 150 * s)
    neck = glass.liquid_bridge(center, 96 * s, top, 44 * s, 0.34)
    if neck is not None:
        glass.paint_glass(p, neck, True, None, specular=0.0, lift=0.8)
    glass.drop_shadow(p, center, 96 * s, QColor(0, 0, 0, 120), lift=12 * s)
    orb = glass.circle(center, 96 * s)
    glass.paint_glass(p, orb, True, None, lift=1.0)
    # Rim of the tile.
    glass._rim(p, shape, rect, True, 0.9)
    p.end()
    return image


def tray(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 64.0
    center = QPointF(32 * s, 34 * s)
    disc = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    disc.setColorAt(0.0, QColor("#4A4A50"))
    disc.setColorAt(1.0, QColor("#111114"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(disc)
    p.drawEllipse(QPointF(32 * s, 32 * s), 30 * s, 30 * s)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(center, 12 * s, 12 * s)
    for angle in (-90, 30, 150):
        point = QPointF(center.x() + math.cos(math.radians(angle)) * 20 * s,
                        center.y() + math.sin(math.radians(angle)) * 20 * s)
        p.drawEllipse(point, 5.2 * s, 5.2 * s)
    p.end()
    return image


assets = ROOT / "assets"
big = to_pil(tile(512))
big.save(assets / "icon.png")
big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
small = to_pil(tray(256))
small.resize((64, 64), Image.LANCZOS).save(assets / "tray.png")
small.save(assets / "tray.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64)])
print("icons written to", assets)
