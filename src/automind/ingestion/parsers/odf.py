"""OpenDocument files (odt, odp, ods) from LibreOffice and similar programs."""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from . import Page

NS = {
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
}


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _paragraphs(element) -> list[str]:
    found = []
    for node in element.iter():
        if node.tag in (_q("text", "p"), _q("text", "h")):
            text = "".join(node.itertext()).strip()
            if text:
                found.append(text)
    return found


def parse_odf(content: bytes, settings=None) -> list[Page]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    slides = list(root.iter(_q("draw", "page")))
    if slides:
        return [Page(i, f"Slide {i}\n\n" + "\n\n".join(_paragraphs(s))) for i, s in enumerate(slides, 1)]
    sheets = list(root.iter(_q("table", "table")))
    if sheets and not list(root.iter(_q("text", "h"))):
        pages = []
        for i, sheet in enumerate(sheets, 1):
            name = sheet.get(_q("table", "name"), f"Sheet{i}")
            rows = []
            for r, row in enumerate(sheet.iter(_q("table", "table-row")), 1):
                cells = [" ".join(_paragraphs(c)) for c in row.iter(_q("table", "table-cell"))]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(f"Sheet {name}, row {r}: " + " | ".join(cells))
            pages.append(Page(i, "\n\n".join(rows)))
        return pages
    return [Page(1, "\n\n".join(_paragraphs(root)))]
