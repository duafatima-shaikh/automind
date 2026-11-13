"""Server sent events helper shared by the streaming endpoints."""
from __future__ import annotations

import json


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
