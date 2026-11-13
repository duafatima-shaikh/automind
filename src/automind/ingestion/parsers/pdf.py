from __future__ import annotations

import io
import logging

from . import Page

logger = logging.getLogger(__name__)


def parse_pdf(content: bytes, settings=None) -> list[Page]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            return []
    pages = [Page(n, p.extract_text() or "") for n, p in enumerate(reader.pages, start=1)]
    if settings is not None:
        _read_scanned_pages(content, pages, settings)
    return pages


def _read_scanned_pages(content: bytes, pages: list[Page], settings) -> None:
    """Pages with almost no text are probably pictures. Read them with text recognition."""
    if settings.ocr_backend == "none":
        return
    scanned = [i for i, p in enumerate(pages) if len(p.text.strip()) < settings.ocr_min_chars_per_page]
    if not scanned:
        return
    from ..ocr import OCRUnavailable, ocr_image

    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("%d scanned pages found but pypdfium2 is not installed", len(scanned))
        return
    document = pdfium.PdfDocument(content)
    try:
        for i in scanned[: settings.ocr_max_pages]:
            image = document[i].render(scale=2.0).to_pil()
            try:
                text = ocr_image(image, settings.ocr_backend)
            except OCRUnavailable as error:
                logger.warning("Skipping scanned pages: %s", error)
                return
            if text:
                pages[i].text = f"{pages[i].text}\n{text}".strip()
    finally:
        document.close()
