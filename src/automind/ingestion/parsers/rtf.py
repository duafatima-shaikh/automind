from __future__ import annotations

from . import Page
from .text import decode_text


def parse_rtf(content: bytes, settings=None) -> list[Page]:
    from striprtf.striprtf import rtf_to_text

    return [Page(1, rtf_to_text(decode_text(content), errors="ignore"))]
