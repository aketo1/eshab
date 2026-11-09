# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Eshab (onedir, windowed, no UPX).

Build from the repository root:

    .venv\\Scripts\\python -m PyInstaller --noconfirm --clean packaging\\eshab.spec

FFmpeg/FFprobe are bundled from tools\\ when present (audio, video, GIF).
"""

import os
import re

# Qt 6.11 uses the Windows ICU API. Developer tools such as Poppler also
# publish an incompatible icuuc.dll, so system directories must lead PATH.
_system_dirs = [os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "System32"),
                os.environ.get("SystemRoot", "C:/Windows")]
os.environ["PATH"] = os.pathsep.join(_system_dirs + os.environ.get("PATH", "").split(os.pathsep))

try:
    SPEC_DIR = os.path.abspath(SPECPATH)
except NameError:  # pragma: no cover
    SPEC_DIR = os.path.dirname(os.path.abspath(__file__))

REPO_ROOT = os.path.dirname(SPEC_DIR)
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")


def _read_app_version():
    with open(os.path.join(REPO_ROOT, "eshab", "paths.py"), encoding="utf-8") as handle:
        match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', handle.read(), re.MULTILINE)
    return match.group(1) if match else "0.0.0"


APP_VERSION = _read_app_version()
_quad = tuple(([int(p) for p in re.findall(r"\d+", APP_VERSION)][:4] + [0, 0, 0, 0])[:4])
with open(os.path.join(SPEC_DIR, "version_info.txt"), encoding="utf-8") as handle:
    _text = handle.read().replace("@@VERSION_TUPLE@@", repr(_quad)).replace("@@VERSION@@", APP_VERSION)
VERSION_FILE = os.path.join(SPEC_DIR, "_version_info_generated.txt")
with open(VERSION_FILE, "w", encoding="utf-8") as handle:
    handle.write(_text)
print(f"[eshab.spec] Eshab {APP_VERSION}")

datas = [(os.path.join(ASSETS_DIR, name), "assets")
         for name in ("icon.ico", "icon.png", "tray.ico", "tray.png", "highlight.wav")]
# The tray's glyphs for each state, light and dark (scripts/make_brand.py).
datas.append((os.path.join(ASSETS_DIR, "brand"), "assets/brand"))
# The Qt Quick windows (with their compiled shaders) and the page scripts that
# lay out Word and Excel files for printing.
datas.append((os.path.join(REPO_ROOT, "eshab", "qml"), "eshab/qml"))
for script in ("docx_pages.js", "xlsx_pages.js"):
    datas.append((os.path.join(REPO_ROOT, "eshab", script), "eshab"))
binaries = []
for tool in ("ffmpeg.exe", "ffprobe.exe"):
    path = os.path.join(TOOLS_DIR, tool)
    if os.path.isfile(path):
        binaries.append((path, "tools"))
    else:
        print(f"[eshab.spec] WARNING: {tool} not found; media conversions will need it installed")

hiddenimports = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtMultimedia",
    "PySide6.QtSvg",
    "comtypes",
    "comtypes.client",
    "eshab.install",
    "eshab.shellmenu",
    "eshab.wheel_order",
    "pymupdf",
    "pypdfium2",
]

EXCLUDES = [
    # PyMuPDF 2 pulls these in for its AI layout features; Eshab never uses them.
    "onnxruntime", "pymupdf4llm", "pymupdf_layout", "pymupdf.layout", "networkx", "tabulate",
    "torch", "torchvision", "numba", "llvmlite", "scipy", "sklearn", "matplotlib",
    "pandas", "IPython", "pytest", "tkinter", "segno",
    # Documents print through Microsoft Edge; Eshab no longer carries a browser of its own.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick3D",
    "PySide6.QtCharts", "PySide6.QtGraphs", "PySide6.QtDataVisualization",
    # (PySide6.QtOpenGL stays: Qt Quick's own bindings load it.)
    "PySide6.QtOpenGLWidgets", "PySide6.QtPositioning",
]

a = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# -- trim what Eshab never loads (unused QML, 3D, charts…) ------------------
_DROP_DLL = re.compile(
    r"^pyside6/(qt63d|qt6quick3d|qt6graphs|qt6charts|qt6datavisualization|qt6location"
    r"|qt6quickcontrols2|qt6quickdialogs2|qt6quicktemplates2|qt6shadertools|qt6pdf|qt6virtualkeyboard"
    r"|qt6scxml|qt6statemachine|qt6sensors|qt6spatialaudio|qt6quicktimeline|qt6quickparticles"
    r"|qt6quickvectorimage|qt6bluetooth|qt6nfc|qt6serialport|qt6remoteobjects|opengl32sw"
    # pulled in only by QML modules Eshab never imports (the browser, Qt Labs, maps)
    r"|qt6webengine|qt6webchannel|qtwebengineprocess|qt6labs|qt6positioning)"
    # Qt's QML debugger, and OpenCV's own video reader (Eshab reads video through FFmpeg)
    r"|^pyside6/plugins/qmltooling/|^cv2/opencv_videoio_ffmpeg"
)
_KEEP_TRANSLATION = re.compile(r"qt(base)?_(ar|en)\.qm$")
# The QML Eshab's windows import: QtQml (and its models), QtQuick with its
# Effects and Window parts, and QtMultimedia for the sound and video editors.
_KEEP_QML = re.compile(r"^pyside6/qml/(qtqml/(models/|workerscript/)?[^/]+|qtquick/(effects/|window/)?[^/]+"
                       r"|qtmultimedia/[^/]+)$")
_KEEP_BABEL = re.compile(r"/(root|en|en_us|ar|ar_sa)\.dat$")


def _keep(entry):
    dest = entry[0].replace("\\", "/").lower()
    source = entry[1].replace("\\", "/").lower()
    if "poppler" in source and re.match(r"^icu(?:uc|in|dt).*\.dll$", dest):
        return False
    if dest.startswith("pyside6/qml/"):
        return bool(_KEEP_QML.match(dest))
    if _DROP_DLL.match(dest):
        return False
    if dest.startswith("pyside6/translations/"):
        return bool(_KEEP_TRANSLATION.search(dest))
    if dest.startswith("babel/locale-data/"):
        return bool(_KEEP_BABEL.search(dest))
    return True


_before = len(a.binaries) + len(a.datas)
a.binaries = [entry for entry in a.binaries if _keep(entry)]
a.datas = [entry for entry in a.datas if _keep(entry)]
print(f"[eshab.spec] trimmed {_before - len(a.binaries) - len(a.datas)} unused files")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Eshab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=os.path.join(ASSETS_DIR, "icon.ico"),
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Eshab",
)
