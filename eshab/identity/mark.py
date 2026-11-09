"""The «الملف ينسحب» mark as a signed distance field.

A page whose top-left corner (the dog-ear side in Arabic) is pulled out into
a liquid drop. The same field drives the static icons rendered here with
numpy and the animated shader in ``eshab/qml/Eshab/shaders/mark.frag``, so
the app icon, the tray glyph and the in-app logo are one shape.

Coordinates are in a 100 x 100 box, y pointing down.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class Pose:
    """One frame of the mark.

    At rest the page's top-left corner is a drop sitting in a round notch:
    the moment just after the corner was pulled loose. While it animates a
    tapered neck joins the notch rim to the drop again.
    """

    page: tuple[float, float, float, float, float] = (55.0, 56.0, 26.0, 32.0, 9.0)  # cx, cy, hx, hy, radius
    notch: tuple[float, float, float] = (29.0, 24.0, 20.0)  # centre and radius of the bite
    drop: tuple[float, float] = (27.5, 22.5)                # drop centre
    drop_radius: float = 12.0
    neck: tuple[float, float] = (0.0, 0.0)                  # neck radius at the rim, at the drop (0 = none)
    smooth: float = 3.0                                     # liquid fillet size
    lines: bool = True                                      # the two text lines inside the page


ICON = Pose()
#: Small glyphs need a wider gap around the drop to survive 16 px.
GLYPH = replace(ICON, notch=(29.0, 24.0, 21.5), drop_radius=11.5, smooth=2.0)


@dataclass(frozen=True)
class Material:
    key: str
    light: tuple[float, float, float]
    deep: tuple[float, float, float]
    alpha: float
    rim: float


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


HONEY = Material("honey", _rgb("#FFD985"), _rgb("#DB7817"), 0.97, 0.55)
CLEAR = Material("clear", _rgb("#FFFFFF"), _rgb("#D5DCE8"), 0.34, 1.0)
INK = Material("ink", _rgb("#B3BCFF"), _rgb("#3138C8"), 0.97, 0.5)
MATERIALS = {m.key: m for m in (HONEY, CLEAR, INK)}


# -- distance functions ------------------------------------------------------

def _round_box(px, py, cx, cy, hx, hy, r):
    qx = np.abs(px - cx) - (hx - r)
    qy = np.abs(py - cy) - (hy - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    return outside + np.minimum(np.maximum(qx, qy), 0.0) - r


def _circle(px, py, cx, cy, r):
    return np.hypot(px - cx, py - cy) - r


def _uneven_capsule(px, py, ax, ay, bx, by, ra, rb):
    """Tapered capsule from a (radius ra) to b (radius rb)."""
    dx, dy = bx - ax, by - ay
    h = float(np.hypot(dx, dy))
    if h < 1e-6:
        return np.hypot(px - ax, py - ay) - max(ra, rb)
    # Local frame: a at the origin, b on +y.
    ux, uy = dx / h, dy / h
    lx = np.abs((px - ax) * uy - (py - ay) * ux)
    ly = (px - ax) * ux + (py - ay) * uy
    b = (ra - rb) / h
    a = float(np.sqrt(max(0.0, 1.0 - b * b)))
    k = lx * -b + ly * a
    return np.where(
        k < 0.0,
        np.hypot(lx, ly) - ra,
        np.where(k > a * h, np.hypot(lx, ly - h) - rb, lx * a + ly * b - ra),
    )


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def _smax(a, b, k):
    return -_smin(-a, -b, k)


def rim_point(pose: Pose) -> tuple[float, float]:
    """Where the notch meets the page, on the line towards the page centre."""
    nx, ny, nr = pose.notch
    cx, cy = pose.page[0], pose.page[1]
    length = float(np.hypot(cx - nx, cy - ny)) or 1.0
    return nx + (cx - nx) / length * nr, ny + (cy - ny) / length * nr


def silhouette(px, py, pose: Pose = ICON):
    cx, cy, hx, hy, r = pose.page
    page = _round_box(px, py, cx, cy, hx, hy, r)
    nx, ny, nr = pose.notch
    bitten = _smax(page, -_circle(px, py, nx, ny, nr), pose.smooth)
    shape = _smin(bitten, _circle(px, py, *pose.drop, pose.drop_radius), pose.smooth)
    ra, rb = pose.neck
    if ra > 0.0 or rb > 0.0:
        neck = _uneven_capsule(px, py, *rim_point(pose), *pose.drop, ra, rb)
        shape = _smin(shape, neck, pose.smooth * 2.0)
    return shape


def text_lines(px, py, pose: Pose = ICON):
    """Two right-aligned lines of 'text' (Arabic reads from the right)."""
    cx, cy, hx, hy, _ = pose.page
    right = cx + hx - 10.0
    first = _uneven_capsule(px, py, right - 24.0, cy - 6.0, right, cy - 6.0, 2.2, 2.2)
    second = _uneven_capsule(px, py, right - 15.0, cy + 4.0, right, cy + 4.0, 2.2, 2.2)
    return np.minimum(first, second)


# -- rendering ---------------------------------------------------------------

def _grid(size: int, supersample: int):
    n = size * supersample
    step = 100.0 / n
    axis = (np.arange(n) + 0.5) * step
    px, py = np.meshgrid(axis, axis)
    return px, py, step


def _downsample(rgba: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return rgba
    n = rgba.shape[0] // factor
    # Average premultiplied colour so edges do not darken.
    premul = rgba.copy()
    premul[..., :3] *= premul[..., 3:4]
    premul = premul.reshape(n, factor, n, factor, 4).mean(axis=(1, 3))
    alpha = premul[..., 3:4]
    premul[..., :3] = np.where(alpha > 1e-6, premul[..., :3] / np.maximum(alpha, 1e-6), 0.0)
    return premul


def render_glass(size: int, material: Material = HONEY, pose: Pose = ICON, supersample: int = 2) -> np.ndarray:
    """Liquid-glass mark as float RGBA (straight alpha), size x size."""
    px, py, step = _grid(size, supersample)
    d = silhouette(px, py, pose)
    coverage = np.clip(0.5 - d / step, 0.0, 1.0)

    # A rounded "pillow" height field gives the glass its volume.
    bevel = 9.0
    s = np.clip(-d / bevel, 0.0, 1.0)
    height = np.sqrt(1.0 - (1.0 - s) ** 2)
    gy, gx = np.gradient(height, step)
    nx, ny, nz = -gx * 3.2, -gy * 3.2, np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm

    light = np.array([-0.45, -0.62, 0.64])
    light /= np.linalg.norm(light)
    half = light + np.array([0.0, 0.0, 1.0])
    half /= np.linalg.norm(half)
    diffuse = np.clip(nx * light[0] + ny * light[1] + nz * light[2], 0.0, 1.0)
    spec = np.clip(nx * half[0] + ny * half[1] + nz * half[2], 0.0, 1.0) ** 70
    fresnel = (1.0 - nz) ** 1.6

    # Light to deep along the diagonal, deeper where the glass is thick.
    t = np.clip(((px - 20.0) + (py - 10.0)) / 150.0 + 0.25 * (1.0 - s), 0.0, 1.0)
    light_c = np.array(material.light)
    deep_c = np.array(material.deep)
    body = light_c * (1.0 - t[..., None]) + deep_c * t[..., None]
    body *= (0.78 + 0.32 * diffuse)[..., None]

    # Inner rim: a thin bright edge facing the light, a darker one away from it.
    edge = np.clip(1.0 - (-d) / 1.6, 0.0, 1.0) * (d < 0)
    facing = np.clip(-(nx * 0.6 + ny * 0.8), 0.0, 1.0)
    white = np.ones(3)
    color = body
    color = color + (white - color) * (material.rim * fresnel * (0.4 + 0.6 * facing))[..., None]
    color = color + (white - color) * (0.85 * spec)[..., None]
    color = color + (white - color) * (0.55 * edge * facing)[..., None]
    color = color * (1.0 - 0.18 * (edge * (1.0 - facing)))[..., None]

    alpha = coverage * (material.alpha + (1.0 - material.alpha) * np.clip(fresnel * 1.4 + spec, 0.0, 1.0))

    if pose.lines:
        lines = text_lines(px, py, pose)
        etch = np.clip(0.5 - lines / step, 0.0, 1.0) * coverage
        color = color + (white - color) * (0.62 * etch)[..., None]
        alpha = np.maximum(alpha, etch * 0.9)

    rgba = np.dstack([np.clip(color, 0.0, 1.0), np.clip(alpha, 0.0, 1.0)])
    return _downsample(rgba, supersample)


def render_flat(size: int, ink: tuple[float, float, float], pose: Pose = GLYPH,
                cut_lines: bool | None = None, supersample: int = 4) -> np.ndarray:
    """Single-colour glyph (tray, small sizes). Lines are cut out of the page."""
    px, py, step = _grid(size, supersample)
    d = silhouette(px, py, pose)
    if cut_lines is None:
        cut_lines = size >= 20
    if cut_lines:
        d = np.maximum(d, -text_lines(px, py, pose))
    coverage = np.clip(0.5 - d / step, 0.0, 1.0)
    rgba = np.dstack([np.broadcast_to(np.array(ink), coverage.shape + (3,)), coverage])
    return _downsample(rgba.astype(float), supersample)


def _check(px, py, pose: Pose, reveal: float = 1.0):
    cx, cy = pose.page[0], pose.page[1]
    a, b, c = (cx - 11.0, cy + 2.0), (cx - 3.0, cy + 10.0), (cx + 12.0, cy - 8.0)
    first = _uneven_capsule(px, py, *a, *b, 3.6, 3.6)
    second = _uneven_capsule(px, py, *b, *c, 3.6, 3.6)
    return np.minimum(first, second)


def render_tray(size: int, ink: tuple[float, float, float], level: float | None = None,
                wave: float = 0.0, check: bool = False, badge: tuple[float, float, float] | None = None,
                supersample: int = 4) -> np.ndarray:
    """Tray glyph. ``level`` (0..1) draws the working state: an outlined page
    filling from the bottom, the drop solid. ``check`` cuts a tick out of the
    page; ``badge`` adds a small coloured dot (errors)."""
    pose = GLYPH
    px, py, step = _grid(size, supersample)
    pixel = 100.0 / size
    d = silhouette(px, py, pose)
    if level is None:
        if check and size >= 20:
            d = np.maximum(d, -_check(px, py, pose))
        elif size >= 20:
            d = np.maximum(d, -text_lines(px, py, pose))
        shape = d
    else:
        stroke = 1.3 * pixel
        shell = np.abs(d + stroke / 2.0) - stroke / 2.0
        cx, cy, hx, hy, _ = pose.page
        top, bottom = cy - hy, cy + hy
        surface = bottom - (bottom - top) * level + 0.9 * pixel * np.sin(px * 0.3 + wave)
        liquid = np.maximum(d, surface - py)
        drop = _circle(px, py, *pose.drop, pose.drop_radius)
        shape = np.minimum(np.minimum(shell, liquid), drop)
    coverage = np.clip(0.5 - shape / step, 0.0, 1.0)
    color = np.broadcast_to(np.array(ink, dtype=float), coverage.shape + (3,)).copy()
    alpha = coverage
    if badge is not None:
        dot = _circle(px, py, 82.0, 82.0, 16.0)
        ring = np.clip(0.5 - (dot - 2.5 * pixel) / step, 0.0, 1.0)
        fill = np.clip(0.5 - dot / step, 0.0, 1.0)
        alpha = alpha * (1.0 - ring)          # a clear gap separates the dot from the page
        color = color * (1.0 - fill[..., None]) + np.array(badge) * fill[..., None]
        alpha = np.maximum(alpha, fill)
    return _downsample(np.dstack([color, alpha]), supersample)


def to_image(rgba: np.ndarray):
    from PIL import Image

    return Image.fromarray((np.clip(rgba, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGBA")
