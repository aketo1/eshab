"""Transactional PDF editing: real text and images, not overlays.

* Replacing text removes the original glyphs (a redaction limited to text)
  and writes new, selectable text in the same place; Arabic stays real text
  that can be searched and copied.
* Replacing or moving an image removes only its pixels, never nearby text.
* Every change is a transaction with undo/redo; the input file is untouched
  until :meth:`PdfSession.save`, which writes atomically and keeps a backup
  when saving over the original.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

HISTORY_LIMIT = 15
HISTORY_BYTES = 192 * 1024 * 1024


@dataclass
class Element:
    kind: str                                   # "text" or "image"
    rect: tuple[float, float, float, float]
    text: str = ""
    size: float = 12
    color: str = "#202438"
    font: str = "Segoe UI"
    image: bytes = b""
    xref: int = 0
    bold: bool = False


def _is_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f" for ch in text)


def _font_folder() -> Path:
    return Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"


class PdfSession:
    def __init__(self, source: Path):
        self.source = Path(source).resolve()
        # Editing an in-memory copy keeps Windows from locking the original
        # during an atomic save and isolates edits from changes on disk.
        self.doc = fitz.open("pdf", self.source.read_bytes())
        if self.doc.needs_pass:
            self.doc.close()
            raise ValueError("هذا الملف محمي بكلمة مرور. افتح نسخة غير مقفلة للتحرير.")
        if not self.doc.is_pdf:
            raw = self.doc.convert_to_pdf()
            self.doc.close()
            self.doc = fitz.open("pdf", raw)
        for page in self.doc:
            if page.rotation:
                page.remove_rotation()
        self.history: list[bytes] = []
        self.future: list[bytes] = []
        self.dirty = False

    # -- basics -------------------------------------------------------------

    def close(self) -> None:
        if not getattr(self.doc, "is_closed", False):
            self.doc.close()

    def count(self) -> int:
        return self.doc.page_count

    def page_size(self, index: int) -> tuple[float, float]:
        rect = self.doc[index].rect
        return rect.width, rect.height

    def snapshot(self) -> bytes:
        return self.doc.tobytes(garbage=3, deflate=True)

    def _restore(self, data: bytes) -> None:
        self.doc.close()
        self.doc = fitz.open("pdf", data)

    def transaction(self, change) -> None:
        before = self.snapshot()
        try:
            change()
        except Exception:
            self._restore(before)
            raise
        self.history.append(before)
        while len(self.history) > HISTORY_LIMIT or (
            sum(map(len, self.history)) > HISTORY_BYTES and len(self.history) > 1
        ):
            self.history.pop(0)
        self.future.clear()
        self.dirty = True

    def can_undo(self) -> bool:
        return bool(self.history)

    def can_redo(self) -> bool:
        return bool(self.future)

    def undo(self) -> None:
        if not self.history:
            return
        self.future.append(self.snapshot())
        self._restore(self.history.pop())
        self.dirty = True

    def redo(self) -> None:
        if not self.future:
            return
        self.history.append(self.snapshot())
        self._restore(self.future.pop())
        self.dirty = True

    # -- reading --------------------------------------------------------------

    def elements(self, index: int) -> list[Element]:
        page = self.doc[index]
        items: list[Element] = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():
                            font = span.get("font", "Segoe UI")
                            items.append(Element(
                                "text", tuple(span["bbox"]),
                                unicodedata.normalize("NFKC", span["text"]),
                                span["size"], f"#{span.get('color', 0):06x}",
                                font, bold=bool(span.get("flags", 0) & 16) or "bold" in font.lower(),
                            ))
            elif block["type"] == 1:
                items.append(Element("image", tuple(block["bbox"]), image=block.get("image", b"")))
        return items

    def at(self, index: int, x: float, y: float, kind: str | None = None) -> Element | None:
        point = fitz.Point(x, y)
        matches = [e for e in self.elements(index)
                   if (kind is None or e.kind == kind) and fitz.Rect(e.rect).contains(point)]
        if not matches:
            return None
        return min(matches, key=lambda e: fitz.Rect(e.rect).get_area())

    def render(self, index: int, scale: float = 1.5):
        return self.doc[index].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

    # -- text -------------------------------------------------------------------

    def change_text(self, index: int, original: Element | None, text: str, rect,
                    size: float = 12, color: str = "#202438", bold: bool | None = None) -> None:
        target = fitz.Rect(rect)
        if target.is_empty or target.width < 2 or target.height < 2:
            raise ValueError("منطقة النص صغيرة جدًا.")
        size = max(4.0, min(250.0, float(size)))
        if bold is None:
            bold = bool(original is not None and original.bold)

        def apply() -> None:
            page = self.doc[index]
            if original is not None:
                old = fitz.Rect(original.rect)
                old.x0 += 0.1
                old.x1 -= 0.1
                old.y0 += 0.1
                old.y1 -= 0.1
                # Only the glyphs go: no fill, so a coloured panel, a picture or
                # a line under the words stays exactly as it was.
                page.add_redact_annot(old, fill=False, cross_out=False)
                page.apply_redactions(images=0, graphics=0, text=0)
            if not text.strip():
                return
            folder = _font_folder()
            regular = "tahoma.ttf" if (folder / "tahoma.ttf").exists() else "arial.ttf"
            heavy = {"tahoma.ttf": "tahomabd.ttf", "arial.ttf": "arialbd.ttf"}[regular]
            heavy = heavy if (folder / heavy).exists() else regular
            css = (
                f"@font-face {{font-family:Eshab;src:url({regular})}} "
                f"@font-face {{font-family:Eshab;src:url({heavy});font-weight:bold}} "
                "* {font-family:Eshab,sans-serif;margin:0;padding:0} "
                f"body {{font-size:{size}pt;color:{color};line-height:1.15;"
                f"font-weight:{'bold' if bold else 'normal'}}}"
            )
            direction = "rtl" if _is_arabic(text) else "ltr"
            markup = f'<div dir="{direction}">{html.escape(text).replace(chr(10), "<br>")}</div>'
            archive = fitz.Archive(str(folder))
            # Longer words than before get room on their line first, toward
            # where it continues (left in Arabic, right otherwise), at their
            # own size; only then are they made smaller.
            wider = fitz.Rect(target)
            if direction == "rtl":
                wider.x0 = min(wider.x0, page.rect.x0 + 18)
            else:
                wider.x1 = max(wider.x1, page.rect.x1 - 18)
            spare = -1
            for box, smallest in ((target, 1), (wider, 1), (wider, 0.5)):
                spare, _scale = page.insert_htmlbox(box, markup, css=css, archive=archive, scale_low=smallest)
                if spare >= 0:
                    break
            if spare < 0:
                raise ValueError("النص لا يتسع في المنطقة. كبّر المربع أو صغّر الخط.")
            self._normalize_font_maps(page)

        self.transaction(apply)

    def _normalize_font_maps(self, page) -> None:
        """Copy/search Arabic as ordinary Unicode while keeping shaped glyphs.

        The HTML story can map Arabic glyphs to presentation forms; only the
        ToUnicode destinations are normalized, never the embedded glyphs.
        """

        def normalized(value: str) -> str:
            try:
                text = bytes.fromhex(value).decode("utf-16-be")
                return unicodedata.normalize("NFKC", text).encode("utf-16-be").hex()
            except (ValueError, UnicodeError):
                return value

        def range_block(match) -> str:
            unchanged, changed = [], []
            for line in match.group(1).strip().splitlines():
                m = re.fullmatch(r"\s*<([a-fA-F0-9]+)>\s*<([a-fA-F0-9]+)>\s*<([a-fA-F0-9]+)>\s*", line)
                if not m:
                    unchanged.append(line)
                    continue
                start, end, dest = (int(v, 16) for v in m.groups())
                width = len(m[3])
                mappings = [(f"{cid:0{len(m[1])}x}", f"{dest + cid - start:0{width}x}")
                            for cid in range(start, end + 1)]
                if any(normalized(v) != v.lower() for _, v in mappings):
                    changed.extend((cid, normalized(v)) for cid, v in mappings)
                else:
                    unchanged.append(line)
            blocks = []
            if unchanged:
                blocks.append(f"{len(unchanged)} beginbfrange\n" + "\n".join(unchanged) + "\nendbfrange")
            for i in range(0, len(changed), 100):
                part = changed[i:i + 100]
                blocks.append(f"{len(part)} beginbfchar\n"
                              + "\n".join(f"<{cid}> <{dest}>" for cid, dest in part) + "\nendbfchar")
            return "\n".join(blocks)

        def chars(match) -> str:
            body = re.sub(r"<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>",
                          lambda m: f"<{m[1]}> <{normalized(m[2])}>", match.group(1))
            return "beginbfchar" + body + "endbfchar"

        done = set()
        for font in page.get_fonts():
            kind, ref = self.doc.xref_get_key(font[0], "ToUnicode")
            if kind != "xref":
                continue
            xref = int(ref.split()[0])
            if xref in done:
                continue
            done.add(xref)
            raw = self.doc.xref_stream(xref).decode("latin1")
            adjusted = re.sub(r"\d+\s+beginbfrange\s*(.*?)\s*endbfrange", range_block, raw, flags=re.S)
            adjusted = re.sub(r"beginbfchar(.*?)endbfchar", chars, adjusted, flags=re.S)
            if adjusted != raw:
                self.doc.update_stream(xref, adjusted.encode("latin1"))

    # -- images -----------------------------------------------------------------

    def change_image(self, index: int, original: Element | None, data: bytes, rect) -> None:
        # Validate before touching the page, and remove pixels, not text.
        pix = fitz.Pixmap(data)
        if pix.width * pix.height > 100_000_000:
            raise ValueError("الصورة كبيرة جدًا.")

        def apply() -> None:
            page = self.doc[index]
            if original is not None:
                page.add_redact_annot(fitz.Rect(original.rect), fill=(1, 1, 1), cross_out=False)
                page.apply_redactions(images=2, graphics=0, text=1)
            page.insert_image(fitz.Rect(rect), stream=data, keep_proportion=False, overlay=True)

        self.transaction(apply)

    def image_bytes(self, index: int, element: Element) -> bytes:
        """PNG bytes of *element* as it appears on the page (for moving it)."""
        if element.image:
            try:
                fitz.Pixmap(element.image)
                return element.image
            except Exception:
                pass
        clip = fitz.Rect(element.rect)
        return self.doc[index].get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).tobytes("png")

    def delete_element(self, index: int, element: Element) -> None:
        def apply() -> None:
            page = self.doc[index]
            rect = fitz.Rect(element.rect)
            page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
            if element.kind == "text":
                page.apply_redactions(images=0, graphics=0, text=0)
            else:
                page.apply_redactions(images=2, graphics=0, text=1)

        self.transaction(apply)

    def redact(self, index: int, rect) -> None:
        def apply() -> None:
            page = self.doc[index]
            page.add_redact_annot(fitz.Rect(rect), fill=(0, 0, 0), cross_out=False)
            page.apply_redactions(images=2, graphics=1, text=0)

        self.transaction(apply)

    # -- pages --------------------------------------------------------------------

    def rotate_page(self, index: int, angle: int = 90) -> None:
        def apply() -> None:
            page = self.doc[index]
            page.set_rotation((page.rotation + angle) % 360)
            page.remove_rotation()

        self.transaction(apply)

    def reorder(self, indices: list[int]) -> None:
        if not indices or any(i < 0 or i >= self.count() for i in indices):
            raise ValueError("ترتيب صفحات غير صالح.")
        self.transaction(lambda: self.doc.select(indices))

    def duplicate_page(self, index: int) -> None:
        order = list(range(self.count()))
        order.insert(index + 1, index)
        self.reorder(order)

    def delete_page(self, index: int) -> None:
        if self.count() <= 1:
            raise ValueError("لا يمكن حذف الصفحة الوحيدة.")
        self.reorder([i for i in range(self.count()) if i != index])

    def move_page(self, index: int, offset: int) -> int:
        target = max(0, min(self.count() - 1, index + offset))
        if target == index:
            return index
        order = list(range(self.count()))
        order.insert(target, order.pop(index))
        self.reorder(order)
        return target

    # -- saving -------------------------------------------------------------------

    def backup_path(self, target: Path, label: str = "before Eshab") -> Path:
        backup = target.with_name(f"{target.stem} - {label}.pdf")
        counter = 2
        while backup.exists():
            backup = target.with_name(f"{target.stem} - {label} {counter}.pdf")
            counter += 1
        return backup

    def save(self, target: Path, overwrite: bool = False, backup_label: str = "before Eshab") -> Path | None:
        target = Path(target).resolve()
        if target == self.source and not overwrite:
            raise ValueError("استخدم حفظ في نفس الملف أو اختر اسمًا جديدًا.")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if target == self.source and target.exists():
            backup = self.backup_path(target, backup_label)
            shutil.copy2(target, backup)
        handle, temp = tempfile.mkstemp(prefix=".eshab-", suffix=".pdf", dir=target.parent)
        os.close(handle)
        try:
            self.doc.save(temp, garbage=4, deflate=True)
            with fitz.open(temp) as verify:
                if verify.page_count != self.count():
                    raise ValueError("تعذّر التحقق من الملف المحفوظ.")
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        self.dirty = False
        return backup
