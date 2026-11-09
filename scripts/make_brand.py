"""Render Eshab's icons from the «الملف ينسحب» mark.

Writes the app icon (assets/icon.ico, assets/icon.png, assets/brand/eshab-*.png)
and every tray glyph (assets/brand/tray-<taskbar>-<state>-<size>.png, plus
assets/tray.ico/png). Run from the repository root:

    .venv\\Scripts\\python scripts\\make_brand.py
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageFilter  # noqa: E402

from eshab.identity import mark  # noqa: E402

ASSETS = ROOT / "assets"
BRAND = ASSETS / "brand"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
TRAY_SIZES = (16, 20, 24, 32, 40)
WORK_FRAMES = 8
INKS = {"dark": (1.0, 1.0, 1.0), "light": (0.11, 0.11, 0.12)}  # by taskbar colour
ERROR_RED = (0.90, 0.28, 0.30)


def with_shadow(image: Image.Image, size: int) -> Image.Image:
    alpha = image.split()[3]
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.32)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.0, size / 48.0)))
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, max(1, round(size / 64.0))))
    out.alpha_composite(image)
    return out


def app_icon(size: int) -> Image.Image:
    pose = mark.ICON if size >= 40 else mark.GLYPH
    if size < 32:
        pose = replace(pose, lines=False)
    image = mark.to_image(mark.render_glass(size, mark.HONEY, pose, supersample=4 if size < 128 else 2))
    return with_shadow(image, size) if size >= 48 else image


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    icons = {size: app_icon(size) for size in ICON_SIZES}
    icons[256].save(ASSETS / "icon.png")
    icons[256].save(BRAND / "eshab-256.png")
    with_shadow(mark.to_image(mark.render_glass(1024, mark.HONEY, mark.ICON)), 1024).save(BRAND / "eshab-1024.png")
    icons[256].save(ASSETS / "icon.ico", format="ICO", sizes=[(s, s) for s in ICON_SIZES],
                    append_images=[icons[s] for s in ICON_SIZES if s != 256])

    for taskbar, ink in INKS.items():
        for size in TRAY_SIZES:
            frames = {
                "idle": mark.render_tray(size, ink),
                "done": mark.render_tray(size, ink, check=True),
                "error": mark.render_tray(size, ink, badge=ERROR_RED),
            }
            for index in range(WORK_FRAMES):
                phase = index / WORK_FRAMES
                level = 0.15 + 0.7 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))
                frames[f"work{index}"] = mark.render_tray(size, ink, level=level, wave=phase * 2 * math.pi)
            for state, rgba in frames.items():
                mark.to_image(rgba).save(BRAND / f"tray-{taskbar}-{state}-{size}.png")

    tray = [Image.open(BRAND / f"tray-dark-idle-{size}.png") for size in TRAY_SIZES]
    tray[-1].save(ASSETS / "tray.png")
    tray[-1].save(ASSETS / "tray.ico", format="ICO", sizes=[(s, s) for s in TRAY_SIZES], append_images=tray[:-1])
    print(f"Wrote {len(ICON_SIZES)} icon sizes and {len(INKS) * len(TRAY_SIZES) * (3 + WORK_FRAMES)} tray glyphs")


if __name__ == "__main__":
    main()
