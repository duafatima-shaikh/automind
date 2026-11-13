"""Read text out of pictures (text recognition).

Backends, tried in this order when the setting is "auto":
  * rapidocr (pip install 'automind[ocr]'): pure Python install, no system program needed.
  * tesseract (needs the Tesseract program and `pip install pytesseract`).
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class OCRUnavailable(Exception):
    """No text recognition engine is installed."""


_lock = threading.Lock()
_rapid_engine = None


def _rapidocr(image) -> str:
    global _rapid_engine
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    with _lock:
        if _rapid_engine is None:
            _rapid_engine = RapidOCR()
        result, _ = _rapid_engine(np.array(image.convert("RGB")))
    if not result:
        return ""
    return "\n".join(item[1] for item in result if len(item) > 1 and item[1])


def _tesseract(image) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as error:
        raise ImportError("The Tesseract program is not installed") from error


_BACKENDS = {"rapidocr": _rapidocr, "tesseract": _tesseract}


def ocr_image(image, backend: str = "auto") -> str:
    """Return the text found in a PIL image. Raises OCRUnavailable if no engine works."""
    if backend == "none":
        raise OCRUnavailable("Text recognition is turned off (AUTOMIND_OCR_BACKEND=none).")
    names = list(_BACKENDS) if backend == "auto" else [backend]
    last_error: Optional[Exception] = None
    for name in names:
        try:
            return _BACKENDS[name](image).strip()
        except ImportError as error:
            last_error = error
            logger.debug("OCR backend %s unavailable: %s", name, error)
    raise OCRUnavailable(
        "Reading text from images needs a text recognition engine. "
        "Install one with: pip install 'automind[ocr]'"
        + (f" ({last_error})" if last_error else "")
    )


def ocr_available(backend: str = "auto") -> bool:
    from PIL import Image

    try:
        ocr_image(Image.new("RGB", (8, 8), "white"), backend)
        return True
    except OCRUnavailable:
        return False
