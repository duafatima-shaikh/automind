"""File parsers. Each parser turns file bytes into a list of pages of text.

A "page" means: a page of a PDF, a slide of a presentation, a sheet of a spreadsheet,
a chapter of a book, or the frame of an image. Citations show this number.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Optional

from ...config import Settings


class UnsupportedFileType(Exception):
    pass


class EmptyDocumentError(Exception):
    pass


@dataclass
class Page:
    number: int
    text: str


TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".tex", ".srt", ".vtt", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".sql",
    ".sh", ".bat", ".css", ".kt", ".swift", ".r", ".ipynb",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
LEGACY_OFFICE = {".doc": "docx", ".ppt": "pptx", ".xls": "xlsx"}
ODF_EXTENSIONS = {".odt", ".odp", ".ods"}
HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}

SUPPORTED_DESCRIPTION = (
    "PDF, Word (docx, doc), PowerPoint (pptx, ppt), Excel (xlsx, xls), CSV, OpenDocument, "
    "RTF, EPUB, HTML, text and code files, and images (png, jpg, gif, bmp, tiff, webp)"
)

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp"}


def image_mime_type(extension: str) -> str:
    return _MIME.get(extension, "application/octet-stream")


def _kind_from_content(content: bytes) -> Optional[str]:
    """Guess the type from the first bytes, for files with a missing or wrong extension."""
    head = content[:16]
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if head.startswith(b"BM"):
        return ".bmp"
    if head.startswith(b"{\\rtf"):
        return ".rtf"
    if head.startswith(b"PK"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(content)).namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return ".docx"
        if "ppt/presentation.xml" in names:
            return ".pptx"
        if "xl/workbook.xml" in names:
            return ".xlsx"
        if "mimetype" in names:
            mimetype = zipfile.ZipFile(io.BytesIO(content)).read("mimetype")
            if mimetype.startswith(b"application/epub"):
                return ".epub"
            return {b"application/vnd.oasis.opendocument.text": ".odt",
                    b"application/vnd.oasis.opendocument.presentation": ".odp",
                    b"application/vnd.oasis.opendocument.spreadsheet": ".ods"}.get(mimetype)
    return None


def looks_like_text(content: bytes) -> bool:
    sample = content[:8192]
    if b"\x00" in sample:
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = sample.decode("latin-1")
        except UnicodeDecodeError:
            return False
    if not text:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    return printable / len(text) > 0.95


def parse_document(filename: str, content: bytes, settings: Optional[Settings] = None) -> list[Page]:
    settings = settings or Settings()
    extension = PurePath(filename).suffix.lower()
    known = (TEXT_EXTENSIONS | IMAGE_EXTENSIONS | ODF_EXTENSIONS | HTML_EXTENSIONS
             | set(LEGACY_OFFICE) | {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".csv", ".tsv",
                                     ".rtf", ".epub"})
    if extension not in known:
        extension = _kind_from_content(content) or (".txt" if looks_like_text(content) else "")
    if not extension:
        raise UnsupportedFileType(
            f"This file type is not supported. Supported: {SUPPORTED_DESCRIPTION}"
        )

    if extension == ".pdf":
        from .pdf import parse_pdf as parser
    elif extension == ".docx":
        from .docx import parse_docx as parser
    elif extension == ".pptx":
        from .pptx import parse_pptx as parser
    elif extension in (".xlsx", ".xlsm"):
        from .xlsx import parse_xlsx as parser
    elif extension in (".csv", ".tsv"):
        from .csv_file import parse_csv as parser
    elif extension in LEGACY_OFFICE:
        from .legacy import make_legacy_parser
        parser = make_legacy_parser(extension)
    elif extension in ODF_EXTENSIONS:
        from .odf import parse_odf as parser
    elif extension == ".rtf":
        from .rtf import parse_rtf as parser
    elif extension == ".epub":
        from .epub import parse_epub as parser
    elif extension in HTML_EXTENSIONS:
        from .html import parse_html as parser
    elif extension in IMAGE_EXTENSIONS:
        from .image import make_image_parser
        parser = make_image_parser(extension)
    else:
        from .text import parse_text as parser

    pages = [p for p in parser(content, settings) if p.text.strip()]
    if not pages:
        raise EmptyDocumentError(
            "No readable text was found in this file."
            + (" If it is a picture of text, install text recognition: pip install 'automind[ocr]'"
               if extension in IMAGE_EXTENSIONS or extension == ".pdf" else "")
        )
    return pages
