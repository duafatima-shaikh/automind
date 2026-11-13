"""EPUB books. Each chapter file is one page."""
from __future__ import annotations

import io
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from . import Page
from .html import parse_html


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_epub(content: bytes, settings=None) -> list[Page]:
    archive = zipfile.ZipFile(io.BytesIO(content))
    names = archive.namelist()
    ordered: list[str] = []
    try:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = next(e.get("full-path") for e in container.iter() if _local(e.tag) == "rootfile")
        opf = ET.fromstring(archive.read(opf_path))
        base = posixpath.dirname(opf_path)
        manifest = {e.get("id"): e.get("href") for e in opf.iter() if _local(e.tag) == "item"}
        for ref in (e for e in opf.iter() if _local(e.tag) == "itemref"):
            href = manifest.get(ref.get("idref"))
            if href:
                ordered.append(posixpath.normpath(posixpath.join(base, href)))
    except (KeyError, StopIteration, ET.ParseError):
        pass
    if not ordered:
        ordered = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
    pages = []
    for name in ordered:
        if name in names:
            for page in parse_html(archive.read(name)):
                if page.text.strip():
                    pages.append(Page(len(pages) + 1, page.text))
    return pages
