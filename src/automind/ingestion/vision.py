"""Optional: ask a vision capable model (OpenAI compatible) to describe a picture.
Useful for photos and charts that contain little or no text."""
from __future__ import annotations

import base64

import httpx

from ..config import Settings

PROMPT = (
    "Describe this image for a search index. Mention every visible label, number, title and "
    "any chart values, then describe what the picture shows in two or three sentences."
)


def describe_image(content: bytes, mime_type: str, settings: Settings) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("AUTOMIND_OPENAI_API_KEY is needed for image descriptions")
    data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode()}"
    payload = {
        "model": settings.vision_model or settings.llm_model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }
    response = httpx.post(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()
