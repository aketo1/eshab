"""The «الملف ينسحب» mark: one shape, one palette, every asset present."""

import re
from pathlib import Path

import numpy as np
import pytest

from eshab.identity import mark

ROOT = Path(__file__).resolve().parent.parent


def _inside(x, y, pose=mark.ICON):
    return float(mark.silhouette(np.array([[x]]), np.array([[y]]), pose)[0, 0]) < 0


def test_rest_pose_is_a_page_with_a_drop_in_its_notch():
    assert _inside(*mark.ICON.drop)                 # the drop
    assert _inside(60.0, 70.0)                      # the page body
    assert not _inside(36.0, 31.0)                  # the gap between drop and notch
    assert not _inside(5.0, 95.0)                   # outside everything


def test_neck_joins_the_drop_to_the_page_while_pulling():
    pulled = mark.replace(mark.ICON, drop=(16.0, 12.0), drop_radius=10.0, neck=(6.0, 4.0))
    snapped = mark.replace(pulled, neck=(0.0, 0.0))
    rim = mark.rim_point(pulled)
    midway = ((rim[0] + 16.0) / 2.0, (rim[1] + 12.0) / 2.0)
    assert _inside(*midway, pose=pulled)
    assert not _inside(*midway, pose=snapped)


@pytest.mark.parametrize("size", [16, 24, 64])
def test_renders_have_the_requested_size_and_some_ink(size):
    glass = mark.render_glass(size, mark.HONEY, supersample=2)
    flat = mark.render_flat(size, (1.0, 1.0, 1.0))
    assert glass.shape == (size, size, 4) and flat.shape == (size, size, 4)
    assert 0.15 < glass[..., 3].mean() < 0.7
    assert 0.15 < flat[..., 3].mean() < 0.7


def test_qml_theme_uses_the_same_material_colours_as_the_icons():
    theme = (ROOT / "eshab" / "qml" / "Eshab" / "Theme.qml").read_text("utf-8")
    for material in mark.MATERIALS.values():
        block = re.search(r'"%s":\s*\{([^}]*)\}' % material.key, theme)
        assert block, material.key
        for field, rgb in (("light", material.light), ("deep", material.deep)):
            value = re.search(r'"%s":\s*"(#[0-9A-Fa-f]{6})"' % field, block.group(1)).group(1)
            assert tuple(round(c * 255) for c in rgb) == tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def test_every_tray_glyph_exists():
    brand = ROOT / "assets" / "brand"
    states = ["idle", "done", "error"] + [f"work{i}" for i in range(8)]
    missing = [f"tray-{tone}-{state}-{size}.png"
               for tone in ("dark", "light") for state in states for size in (16, 20, 24, 32, 40)
               if not (brand / f"tray-{tone}-{state}-{size}.png").is_file()]
    assert not missing


def test_shader_is_compiled_next_to_its_source():
    shaders = ROOT / "eshab" / "qml" / "Eshab" / "shaders"
    source, compiled = shaders / "mark.frag", shaders / "mark.frag.qsb"
    assert compiled.is_file() and compiled.stat().st_mtime >= source.stat().st_mtime - 1
