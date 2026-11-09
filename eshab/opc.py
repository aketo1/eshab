"""Office files as their parts: the zip, its content types and relationships.

Enough of the Open Packaging Conventions to walk from a presentation or a
workbook to its slides, sheets, drawings, charts and pictures by
relationship, the way Office itself does.
"""
from __future__ import annotations

import base64
import posixpath
import zipfile
from pathlib import Path

from lxml import etree

REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp",
               ".tif": "image/tiff", ".tiff": "image/tiff", ".svg": "image/svg+xml", ".webp": "image/webp",
               ".emf": "image/emf", ".wmf": "image/wmf"}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=False)


class Package:
    """A zip of parts, read lazily."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.names = {info.filename.lstrip("/"): info.filename for info in self.zip.infolist()}
        self._xml: dict[str, etree._Element] = {}
        self._rels: dict[str, dict] = {}
        self._uris: dict[str, str] = {}
        self.types = {}
        if "[Content_Types].xml" in self.names:
            root = etree.fromstring(self.zip.read(self.names["[Content_Types].xml"]), _PARSER)
            for node in root:
                if node.tag == CT + "Override":
                    self.types[node.get("PartName", "").lstrip("/")] = node.get("ContentType", "")

    def close(self) -> None:
        self.zip.close()

    def has(self, name: str) -> bool:
        return name.lstrip("/") in self.names

    def blob(self, name: str) -> bytes | None:
        key = self.names.get(name.lstrip("/"))
        return self.zip.read(key) if key else None

    def xml(self, name: str):
        name = name.lstrip("/")
        if name not in self._xml:
            data = self.blob(name)
            self._xml[name] = etree.fromstring(data, _PARSER) if data else None
        return self._xml[name]

    def rels(self, name: str) -> dict:
        """{id: (type, target part name or external URL, external)} of a part."""
        name = name.lstrip("/")
        if name not in self._rels:
            folder, base = posixpath.split(name)
            data = self.blob(posixpath.join(folder, "_rels", base + ".rels"))
            out = {}
            if data:
                for node in etree.fromstring(data, _PARSER):
                    if node.tag != REL + "Relationship":
                        continue
                    target, external = node.get("Target", ""), node.get("TargetMode") == "External"
                    if not external:
                        target = posixpath.normpath(posixpath.join(folder, target)) if not target.startswith("/") else target.lstrip("/")
                    out[node.get("Id")] = (node.get("Type", ""), target, external)
            self._rels[name] = out
        return self._rels[name]

    def target(self, name: str, rid: str | None):
        if not rid:
            return None
        found = self.rels(name).get(rid)
        return found[1] if found and not found[2] else None

    def by_type(self, name: str, suffix: str) -> list[str]:
        """Targets of a part's relationships whose type ends with ``suffix``, in order."""
        return [target for _, (kind, target, external) in sorted(self.rels(name).items(), key=lambda item: _rid_order(item[0]))
                if kind.endswith(suffix) and not external]

    def data_uri(self, name: str | None) -> str | None:
        """A picture part as a data URI the page can show (EMF and WMF become PNG)."""
        if not name:
            return None
        if name in self._uris:
            return self._uris[name]
        data = self.blob(name)
        if not data:
            return None
        kind = IMAGE_TYPES.get(Path(name).suffix.lower()) or self.types.get(name.lstrip("/"), "image/png")
        if kind in ("image/emf", "image/wmf", "image/x-emf", "image/x-wmf"):
            converted = _metafile_png(data)
            if converted is None:
                self._uris[name] = None
                return None
            data, kind = converted, "image/png"
        elif kind == "image/tiff" or kind == "image/bmp":
            converted = _to_png(data)
            if converted is not None:
                data, kind = converted, "image/png"
        uri = f"data:{kind};base64," + base64.b64encode(data).decode("ascii")
        self._uris[name] = uri
        return uri


def _rid_order(rid: str):
    digits = "".join(ch for ch in rid if ch.isdigit())
    return (int(digits) if digits else 0, rid)


def _to_png(data: bytes) -> bytes | None:
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as picture:
            out = io.BytesIO()
            picture.save(out, "PNG")
            return out.getvalue()
    except Exception:
        return None


def _metafile_png(data: bytes) -> bytes | None:
    """An EMF or WMF picture drawn as PNG (Windows draws it through Pillow's WMF plugin)."""
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as picture:
            picture.load(dpi=144) if hasattr(picture, "load") else None
            out = io.BytesIO()
            picture.convert("RGBA").save(out, "PNG")
            return out.getvalue()
    except Exception:
        return None


class PartView:
    """One part, seen with its relationships: what drawings and charts need."""

    def __init__(self, package: Package, name: str):
        self.package = package
        self.name = name.lstrip("/")

    def xml(self):
        return self.package.xml(self.name)

    def related(self, rid: str | None) -> "PartView | None":
        target = self.package.target(self.name, rid)
        return PartView(self.package, target) if target and self.package.has(target) else None

    def image_uri(self, rid: str | None) -> str | None:
        return self.package.data_uri(self.package.target(self.name, rid))

    def by_type(self, suffix: str) -> list["PartView"]:
        return [PartView(self.package, target) for target in self.package.by_type(self.name, suffix) if self.package.has(target)]
