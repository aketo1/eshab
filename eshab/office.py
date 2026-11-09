"""Office documents to PDF with the most faithful engine this PC has.

1. Microsoft Office (Word, Excel, PowerPoint) through COM, when installed:
   the document's own renderer, so the PDF is what the author saw.
2. LibreOffice, bundled with Eshab (tools/LibreOffice) or installed.
3. Eshab's own: the document laid out as HTML (Word files read in full by
   :mod:`eshab.docx_layout`) and printed by Microsoft Edge, which Windows
   ships with. Edge never touches a printer for this.

Office runs in a helper process (``Eshab --office-pdf``) with a time limit:
a dialog nobody can see must never hang a conversion. If the limit passes,
the helper and the automation instance it started are ended.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import shutil
import sys
import tempfile
import time
import winreg
from pathlib import Path

from . import paths, settings

log = logging.getLogger("eshab")

CREATE_NO_WINDOW = 0x08000000
OFFICE_APPS = {
    ".docx": "word", ".doc": "word", ".rtf": "word", ".odt": "word",
    ".xlsx": "excel", ".xls": "excel", ".csv": "excel", ".ods": "excel",
    ".pptx": "powerpoint", ".ppt": "powerpoint", ".odp": "powerpoint",
}
PROGIDS = {"word": "Word.Application", "excel": "Excel.Application", "powerpoint": "PowerPoint.Application"}
PROCESSES = {"word": "WINWORD.EXE", "excel": "EXCEL.EXE", "powerpoint": "POWERPNT.EXE"}
OFFICE_TIMEOUT_S = 180
LIBREOFFICE_TIMEOUT_S = 240
EDGE_TIMEOUT_S = 120
#: Sources Eshab can lay out itself as HTML for Edge to print.
HTML_SOURCES = {".docx", ".xlsx", ".pptx", ".csv", ".md", ".txt", ".rtf", ".odt"}


class ConversionUnavailable(RuntimeError):
    """No engine on this PC can convert the document faithfully."""


# -- what this PC has -----------------------------------------------------------------

def office_allowed() -> bool:
    """Office opening a document talks to the default printer, which wakes a
    sleeping network printer. Off until it is shown not to (or the user asks)."""
    return bool(settings.get("useOfficeForPdf", False))


def office_available(app: str) -> bool:
    progid = PROGIDS.get(app)
    if not progid:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID"):
            return True
    except OSError:
        return False


def libreoffice() -> Path | None:
    candidates = [paths.tools_dir() / "LibreOffice" / "program" / "soffice.exe"]
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    return next((c for c in candidates if c.is_file()), None)


def edge() -> Path | None:
    for root in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if root:
            candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def can_convert(suffix: str) -> bool:
    """Whether some engine here turns this kind of file into a faithful PDF."""
    suffix = suffix.lower()
    app = OFFICE_APPS.get(suffix)
    return bool((app and office_allowed() and office_available(app)) or (app and libreoffice())
                or (suffix in HTML_SOURCES and edge()))


# -- conversion ------------------------------------------------------------------------

def to_pdf(source: Path, target: Path, status=lambda text: None) -> str:
    """Write ``target``; returns the engine that did it. Raises
    :class:`ConversionUnavailable` when nothing here can do it well."""
    # Absolute paths: Edge and LibreOffice resolve relative ones elsewhere.
    source, target = Path(source).resolve(), Path(target).resolve()
    suffix = source.suffix.lower()
    app = OFFICE_APPS.get(suffix)
    tried = []
    if app and office_allowed() and office_available(app):
        tried.append("office")
        if _office(app, source, target):
            return "office"
    soffice = libreoffice() if app else None
    if soffice is not None:
        tried.append("libreoffice")
        if _libreoffice(soffice, source, target):
            return "libreoffice"
    browser = edge()
    if browser is not None and suffix in HTML_SOURCES:
        tried.append("edge")
        if _edge(browser, source, target):
            return "edge"
    raise ConversionUnavailable(f"no faithful engine for {suffix} (tried: {', '.join(tried) or 'none'})")


def _ok(target: Path) -> bool:
    return target.is_file() and target.stat().st_size > 0


def _helper_command(app: str, source: Path, target: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--office-pdf", app, str(source), str(target)]
    return [sys.executable, str(paths.app_root() / "main.py"), "--office-pdf", app, str(source), str(target)]


def _office(app: str, source: Path, target: Path) -> bool:
    command = _helper_command(app, source, target)
    try:
        result = subprocess.run(command, timeout=OFFICE_TIMEOUT_S, creationflags=CREATE_NO_WINDOW,
                                capture_output=True)
    except subprocess.TimeoutExpired:
        log.error("%s did not finish %s in time; ending its automation instance", app, source.name)
        _end_automation(app)
        return False
    if result.returncode != 0:
        log.warning("%s could not convert %s: %s", app, source.name, result.stderr.decode(errors="replace")[-400:])
    return result.returncode == 0 and _ok(target)


def _end_automation(app: str) -> None:
    """End Office instances started for automation (never the user's own)."""
    name = PROCESSES[app]
    script = (f"Get-CimInstance Win32_Process -Filter \"Name='{name}'\" | "
              "Where-Object { $_.CommandLine -match '/Automation|-Embedding' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   timeout=30, creationflags=CREATE_NO_WINDOW, capture_output=True)


def _libreoffice(soffice: Path, source: Path, target: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="eshab-lo-") as work:
        profile = Path(work) / "profile"
        command = [str(soffice), f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
                   "--nolockcheck", "--convert-to", "pdf", "--outdir", work, str(source)]
        try:
            subprocess.run(command, timeout=LIBREOFFICE_TIMEOUT_S, creationflags=CREATE_NO_WINDOW,
                           capture_output=True)
        except subprocess.TimeoutExpired:
            log.error("LibreOffice did not finish %s in time", source.name)
            return False
        produced = Path(work) / (source.stem + ".pdf")
        if not _ok(produced):
            return False
        os.replace(produced, target)
    return True


def _edge(browser: Path, source: Path, target: Path) -> bool:
    from . import html_layout

    html = html_layout.document_html(source)
    deadline = time.monotonic() + EDGE_TIMEOUT_S
    with tempfile.TemporaryDirectory(prefix="eshab-edge-", ignore_cleanup_errors=True) as work:
        page = Path(work) / "document.html"
        page.write_text(html, encoding="utf-8")
        profile = Path(work) / "profile"
        command = [str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                   f"--user-data-dir={profile}", "--no-pdf-header-footer",
                   f"--print-to-pdf={target}", page.as_uri()]
        # No pipes: Edge's printing process outlives the program started here and
        # would keep captured pipes open, so waiting for its output never ends.
        try:
            subprocess.run(command, timeout=EDGE_TIMEOUT_S, creationflags=CREATE_NO_WINDOW,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            log.error("Edge did not print %s in time", source.name)
            return False
        # Newer Edge hands the printing to a process of its own and returns at
        # once: the PDF arrives a moment later, and the profile stays in use
        # until that process ends.
        if not _wait_for_print(target, deadline):
            log.error("Edge did not print %s in time", source.name)
            return False
        _wait_until_free(profile, min(deadline, time.monotonic() + 15))
    # A page laid out larger (finer than Edge's pixel grid) is shrunk back.
    scale = re.search('<meta name="eshab-print-scale" content="([0-9]+)"', html)
    if _ok(target) and scale and int(scale.group(1)) > 1:
        shrink_pdf(target, 1.0 / int(scale.group(1)))
    return _ok(target)


def _wait_for_print(target: Path, deadline: float) -> bool:
    """The printed PDF, once Edge has finished writing it (its size has settled)."""
    last = -1
    while time.monotonic() < deadline:
        size = target.stat().st_size if target.is_file() else 0
        if size > 0 and size == last:
            return True
        last = size
        time.sleep(0.2)
    return _ok(target)


def _wait_until_free(folder: Path, deadline: float) -> None:
    """Remove Edge's profile as soon as Edge lets go of it."""
    while time.monotonic() < deadline:
        try:
            shutil.rmtree(folder)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.2)


def shrink_pdf(path: Path, factor: float) -> None:
    """Scale every page of a PDF (content, size and links) by ``factor``.

    The page content is only wrapped in a scaling transform, never
    rewritten, so text stays text and the tagged structure stays intact.
    Gradients and patterns ignore that transform, so their own matrices
    are scaled to match.
    """
    import pymupdf

    path = Path(path)
    shrunk = path.with_name(path.stem + ".shrinking.pdf")
    scale = pymupdf.Matrix(factor, factor)
    with pymupdf.open(path) as doc:
        scaled: set = set()
        for page in doc:
            _scale_patterns(doc, page, factor, scaled)
            links = page.get_links()
            for link in links:
                page.delete_link(link)
            streams = page.get_contents()
            before, after = doc.get_new_xref(), doc.get_new_xref()
            for xref, data in ((before, f"q {factor:.6f} 0 0 {factor:.6f} 0 0 cm\n".encode("ascii")),
                               (after, b"\nQ\n")):
                doc.update_object(xref, "<<>>")
                doc.update_stream(xref, data)
            doc.xref_set_key(page.xref, "Contents",
                             "[" + " ".join(f"{xref} 0 R" for xref in (before, *streams, after)) + "]")
            box = page.mediabox
            page.set_mediabox(pymupdf.Rect(0, 0, box.width * factor, box.height * factor))
            for link in links:
                link["from"] = link["from"] * scale
                if link.get("to") is not None:
                    link["to"] = link["to"] * scale
                page.insert_link(link)
        doc.save(shrunk, garbage=3, deflate=True)
    os.replace(shrunk, path)


def _scale_patterns(doc, page, factor: float, scaled: set) -> None:
    """A page's patterns are measured from the page's first coordinates,
    which the scaling transform doesn't reach."""
    kind, value = doc.xref_get_key(page.xref, "Resources/Pattern")
    if kind == "xref":
        kind, value = "dict", doc.xref_object(int(value.split()[0]))
    if kind != "dict":
        return
    for found in re.finditer("/[^ /]+ ?([0-9]+) 0 R", value):
        xref = int(found.group(1))
        if xref in scaled:
            continue
        scaled.add(xref)
        kind, matrix = doc.xref_get_key(xref, "Matrix")
        numbers = [float(n) for n in matrix.strip("[] ").split()] if kind == "array" else [1, 0, 0, 1, 0, 0]
        if len(numbers) == 6:
            doc.xref_set_key(xref, "Matrix", "[" + " ".join(f"{n * factor:.6f}" for n in numbers) + "]")


# -- the helper process ----------------------------------------------------------------

def helper_main(argv: list[str]) -> int:
    """``Eshab --office-pdf <word|excel|powerpoint> <source> <target>``."""
    index = argv.index("--office-pdf")
    app, source, target = argv[index + 1], str(Path(argv[index + 2]).resolve()), str(Path(argv[index + 3]).resolve())
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    instance = comtypes.client.CreateObject(PROGIDS[app], dynamic=True)
    try:
        try:
            instance.DisplayAlerts = 0 if app != "excel" else False
            instance.AutomationSecurity = 3          # never run the document's macros
        except Exception:
            pass
        if app == "word":
            instance.Visible = False
            document = instance.Documents.Open(source, False, True, False)
            document.ExportAsFixedFormat(target, 17)            # wdExportFormatPDF
            document.Close(0)
        elif app == "excel":
            instance.Visible = False
            book = instance.Workbooks.Open(source, 0, True)
            book.ExportAsFixedFormat(0, target)                 # xlTypePDF
            book.Close(False)
        else:
            presentation = instance.Presentations.Open(source, True, False, False)   # read-only, no window
            presentation.SaveAs(target, 32)                     # ppSaveAsPDF
            presentation.Close()
    finally:
        try:
            instance.Quit()
        except Exception:
            pass
    return 0 if Path(target).is_file() else 1
