from __future__ import annotations

import json

from . import Page


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_text(content: bytes, settings=None) -> list[Page]:
    text = decode_text(content)
    stripped = text.lstrip()
    if stripped.startswith("{") and stripped.rstrip().endswith("}"):
        try:  # pretty printing puts each key on its own line, which searches better
            text = json.dumps(json.loads(text), indent=1, ensure_ascii=False)
        except ValueError:
            pass
    return [Page(1, text)]
