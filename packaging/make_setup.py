"""Make the one-file Eshab Setup from a PyInstaller build.

    python packaging/make_setup.py build/v2-dist/Eshab "build/تثبيت اسحب.exe"

The Setup is packaging/setup_stub.cs, compiled with the C# compiler that
ships with Windows, with the whole Eshab folder appended to it as a zip
(the stub opens itself as the archive: the offsets in the zip count from the
start of the file).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319")


def render_masks(folder: Path) -> dict[str, Path]:
    """The mark's page (the vessel the liquid fills) and its rim, from the
    same distance field as every other Eshab icon."""
    import numpy as np

    sys.path.insert(0, str(ROOT))
    from eshab.identity import mark

    size, supersample = 512, 2
    px, py, step = mark._grid(size, supersample)
    pose = mark.ICON
    page = mark._round_box(px, py, *pose.page)
    nx, ny, nr = pose.notch
    vessel = mark._smax(page, -mark._circle(px, py, nx, ny, nr), pose.smooth)
    out = {}
    for name, field in (("vessel", vessel), ("rim", np.abs(vessel + 0.7) - 0.7)):
        coverage = np.clip(0.5 - field / step, 0.0, 1.0)
        rgba = np.dstack([np.ones(coverage.shape + (3,)), coverage])
        path = folder / f"{name}.png"
        mark.to_image(mark._downsample(rgba, supersample)).save(path)
        out[name] = path
    out["icon"] = ROOT / "assets" / "tray.png"
    return out


def compile_stub(out: Path) -> None:
    wpf = FRAMEWORK / "WPF"
    masks = render_masks(out.parent)
    command = [str(FRAMEWORK / "csc.exe"), "/nologo", "/target:winexe", "/codepage:65001", "/optimize+",
               f"/out:{out}", f"/win32icon:{ROOT / 'assets' / 'icon.ico'}",
               f"/r:{FRAMEWORK / 'System.IO.Compression.dll'}", f"/r:{FRAMEWORK / 'System.Xaml.dll'}",
               f"/r:{wpf / 'PresentationCore.dll'}", f"/r:{wpf / 'PresentationFramework.dll'}",
               f"/r:{wpf / 'WindowsBase.dll'}", "/r:System.Windows.Forms.dll"]
    command += [f"/resource:{path},Eshab.{name}.png" for name, path in masks.items()]
    command.append(str(ROOT / "packaging" / "setup_stub.cs"))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"The Setup did not compile:\n{result.stdout}\n{result.stderr}")


def main() -> int:
    app = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve()
    if not (app / "Eshab.exe").is_file():
        raise SystemExit(f"No Eshab.exe in {app}")
    stub = target.with_name("setup_stub.exe")
    compile_stub(stub)
    shutil.copyfile(stub, target)
    stub.unlink()
    files = sorted(p for p in app.rglob("*") if p.is_file())
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, "Eshab/" + path.relative_to(app).as_posix())
    print(f"{target} ({target.stat().st_size // (1024 * 1024)} MB, {len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
