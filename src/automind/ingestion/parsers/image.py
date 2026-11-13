"""Pictures. Text in the picture is read with text recognition. Optionally a vision model
adds a written description (set AUTOMIND_IMAGE_DESCRIPTIONS=true with an OpenAI key)."""
from __future__ import annotations

import io
import logging

from . import Page, image_mime_type

logger = logging.getLogger(__name__)
MAX_FRAMES = 50


def make_image_parser(extension: str):
    def parse(content: bytes, settings=None) -> list[Page]:
        from PIL import Image, ImageSequence

        from ..ocr import OCRUnavailable, ocr_image

        try:
            image = Image.open(io.BytesIO(content))
            frames = [f.copy() for _, f in zip(range(MAX_FRAMES), ImageSequence.Iterator(image))]
        except Exception as error:  # noqa: BLE001
            raise ValueError(f"The image could not be opened: {error}") from error

        backend = settings.ocr_backend if settings else "auto"
        pages: list[Page] = []
        ocr_error = None
        for number, frame in enumerate(frames, start=1):
            parts = []
            if settings is not None and settings.image_descriptions and number == 1:
                parts.append(_description(content, extension, settings))
            try:
                text = ocr_image(frame, backend)
                if text:
                    parts.append(f"Text in the image:\n{text}")
            except OCRUnavailable as error:
                ocr_error = error
            pages.append(Page(number, "\n\n".join(p for p in parts if p)))
        if ocr_error and not any(p.text for p in pages):
            raise ocr_error
        return pages

    return parse


def _description(content: bytes, extension: str, settings) -> str:
    from ..vision import describe_image

    try:
        text = describe_image(content, image_mime_type(extension), settings)
        return f"Image description: {text}" if text else ""
    except Exception as error:  # noqa: BLE001
        logger.warning("Image description failed: %s", error)
        return ""
