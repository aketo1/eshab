"""Eshab's entry point.

``Eshab --worker`` runs the conversion worker (started by the tray process,
see eshab/worker.py); ``Eshab --editor <tool> <files…>`` opens an editor
(eshab/editor_app.py). Everything else starts, or talks to, the tray app.
``Eshab --self-check <file.json>`` loads every part and writes what loaded,
showing nothing, so a build can be checked.
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _log_crash(message: str) -> None:
    try:
        crash = Path(os.environ.get("APPDATA", "")) / "Eshab" / "crash.log"
        crash.parent.mkdir(parents=True, exist_ok=True)
        with crash.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def _tell(message: str) -> None:
    """A short message box (never for the worker, which has no window)."""
    try:
        import ctypes

        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            ctypes.windll.user32.MessageBoxW(None, message, "Eshab", 0x10)
    except Exception:
        pass


def _run(part: str, start, quiet: bool) -> None:
    """Run one part of Eshab; a crash is written to crash.log instead of
    showing Python's own error box."""
    try:
        code = start()
    except SystemExit:
        raise
    except BaseException as exc:
        _log_crash(f"Eshab {part} stopped: {exc}\n\n{traceback.format_exc()}")
        if not quiet:
            _tell(f"Eshab could not open this ({exc}).\nThe details are in %APPDATA%\\Eshab\\crash.log.")
        raise SystemExit(1)
    raise SystemExit(code)


def _self_check(target: Path) -> int:
    """Import what the tray, the worker and the editors need; nothing is shown."""
    results = {}
    for name in ("PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtSvg", "PySide6.QtNetwork",
                 "eshab.app", "eshab.worker", "eshab.editor_app", "eshab.office", "eshab.documents",
                 "eshab.docx_layout", "eshab.xlsx_layout", "eshab.pptx_layout", "eshab.pdf_docx", "eshab.tools",
                 "eshab.annotate", "eshab.pdf_model", "eshab.image_pdf", "cv2", "numpy", "pymupdf", "pillow_heif",
                 "openpyxl", "docx", "pptx"):
        try:
            __import__(name)
            results[name] = "ok"
        except BaseException as exc:      # noqa: BLE001 - every failure is the answer here
            results[name] = f"{type(exc).__name__}: {exc}"
    try:
        from eshab import paths

        qml = Path(getattr(sys, "_MEIPASS", paths.app_root())) / "eshab" / "qml"
        results["qml files"] = "ok" if (qml / "windows" / "Editor.qml").is_file() else f"missing in {qml}"
    except BaseException as exc:          # noqa: BLE001
        results["qml files"] = f"{type(exc).__name__}: {exc}"
    target.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0 if all(value == "ok" for value in results.values()) else 1


if "--self-check" in sys.argv:
    index = sys.argv.index("--self-check")
    out = Path(sys.argv[index + 1]) if len(sys.argv) > index + 1 else Path("eshab-self-check.json")
    raise SystemExit(_self_check(out))

if "--worker" in sys.argv:
    def _worker() -> int:
        from eshab.worker import main as worker_main

        return worker_main()

    _run("worker", _worker, quiet=True)

if "--office-pdf" in sys.argv:
    def _office_helper() -> int:
        from eshab.office import helper_main

        return helper_main(sys.argv)

    _run("Office helper", _office_helper, quiet=True)

if "--editor" in sys.argv:
    def _editor() -> int:
        from eshab.editor_app import main as editor_main

        return editor_main(sys.argv)

    _run("editor", _editor, quiet=bool(os.environ.get("ESHAB_EDITOR_SNAPSHOT")))

if "--version" in sys.argv:
    try:
        from eshab.paths import APP_VERSION

        print(f"Eshab {APP_VERSION}")
    except Exception:
        print("Eshab (version unknown)")
    raise SystemExit(0)

if "--setup-finish" in sys.argv or "--uninstall" in sys.argv:
    def _install() -> int:
        import logging

        from eshab import install, paths

        logging.basicConfig(filename=str(paths.data_dir() / "eshab-install.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
        if "--uninstall" in sys.argv:
            return install.uninstall()
        return install.finish(sys.argv[1:])

    _run("setup", _install, quiet="--setup-finish" in sys.argv)

try:
    from eshab.app import main
except Exception as exc:
    message = f"Eshab failed to start: {exc}\n\n{traceback.format_exc()}"
    _log_crash(message)
    _tell(message)
    raise SystemExit(1)

if __name__ == "__main__":
    sys.exit(main())
