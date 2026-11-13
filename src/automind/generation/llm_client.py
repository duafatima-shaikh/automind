"""Language model clients. All of them share one small interface, so providers can be swapped
with a single setting."""
from __future__ import annotations

import hashlib
import json
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Iterator, Optional, Sequence

import httpx

from ..config import Settings
from ..utils.text import split_sentences, term_coverage
from .prompts import NOT_FOUND_MESSAGE


class LLMError(Exception):
    pass


def describe_http_error(error: Exception) -> str:
    """A short, readable reason, including what the service said (for example a wrong key)."""
    response = getattr(error, "response", None)
    if response is not None:
        try:
            detail = response.text.strip().replace("\n", " ")[:200]
        except Exception:  # noqa: BLE001  (streaming responses may not be readable)
            detail = ""
        return f"{response.status_code} {detail}".strip()
    return str(error) or error.__class__.__name__


class LLMClient(ABC):
    name: str = "llm"

    is_real_model: bool = True  # False for the built in extractive engine

    @abstractmethod
    def generate(self, system: str, user: str, *, question: str = "",
                 sources: Sequence = (), temperature: float = 0.0) -> str: ...

    def stream(self, system: str, user: str, *, question: str = "",
               sources: Sequence = (), temperature: float = 0.0) -> Iterator[str]:
        text = self.generate(system, user, question=question, sources=sources,
                             temperature=temperature)
        for word in text.split(" "):
            yield word + " "


class ExtractiveClient(LLMClient):
    """No model at all. It quotes the sentences that best match the question, with citations.
    Works offline and never makes anything up, so it is a safe default for demos and tests."""

    name = "extractive"
    is_real_model = False
    MIN_SENTENCE_COVERAGE = 0.34
    MAX_SENTENCES = 3

    def generate(self, system: str, user: str, *, question: str = "",
                 sources: Sequence = (), temperature: float = 0.0) -> str:
        scored: list[tuple[float, int, int, str]] = []
        for source in sources:
            for position, sentence in enumerate(split_sentences(source.text)):
                coverage = term_coverage(question, sentence)
                if coverage >= self.MIN_SENTENCE_COVERAGE:
                    scored.append((coverage, -source.number, -position, sentence))
        if not scored:
            return NOT_FOUND_MESSAGE
        scored.sort(reverse=True)
        chosen, seen = [], set()
        for coverage, negative_number, _, sentence in scored:
            if sentence in seen:
                continue
            seen.add(sentence)
            chosen.append(f"{sentence.rstrip()} [{-negative_number}]")
            if len(chosen) == self.MAX_SENTENCES:
                break
        return " ".join(chosen)


class OpenAICompatibleClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise LLMError("AUTOMIND_OPENAI_API_KEY is not set")
        self.model = settings.llm_model
        self.name = f"openai:{self.model}"
        self._client = httpx.Client(
            base_url=settings.openai_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )

    def _payload(self, system: str, user: str, stream: bool, temperature: float = 0.0) -> dict:
        return {
            "model": self.model, "temperature": temperature, "stream": stream,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

    def generate(self, system: str, user: str, *, question: str = "",
                 sources: Sequence = (), temperature: float = 0.0) -> str:
        try:
            response = self._client.post(
                "/chat/completions", json=self._payload(system, user, False, temperature))
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            raise LLMError(f"Language model request failed: {describe_http_error(error)}") from error

    def stream(self, system: str, user: str, *, question: str = "",
               sources: Sequence = (), temperature: float = 0.0) -> Iterator[str]:
        try:
            with self._client.stream("POST", "/chat/completions",
                                     json=self._payload(system, user, True, temperature)) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices") or [{}]
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            raise LLMError(f"Language model request failed: {describe_http_error(error)}") from error


class OllamaClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self.model = settings.llm_model
        self.name = f"ollama:{self.model}"
        self._num_ctx = settings.ollama_num_ctx
        self._client = httpx.Client(base_url=settings.ollama_url.rstrip("/"),
                                    timeout=settings.llm_timeout_seconds)

    def _payload(self, system: str, user: str, stream: bool, temperature: float = 0.0) -> dict:
        return {
            "model": self.model, "stream": stream,
            "options": {"temperature": temperature, "num_ctx": self._num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

    def generate(self, system: str, user: str, *, question: str = "",
                 sources: Sequence = (), temperature: float = 0.0) -> str:
        try:
            response = self._client.post(
                "/api/chat", json=self._payload(system, user, False, temperature))
            response.raise_for_status()
            return response.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise LLMError(f"Ollama request failed: {describe_http_error(error)}") from error

    def stream(self, system: str, user: str, *, question: str = "",
               sources: Sequence = (), temperature: float = 0.0) -> Iterator[str]:
        try:
            with self._client.stream("POST", "/api/chat",
                                     json=self._payload(system, user, True, temperature)) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    piece = json.loads(line).get("message", {}).get("content")
                    if piece:
                        yield piece
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise LLMError(f"Ollama request failed: {describe_http_error(error)}") from error


class ResponseCache:
    """Remembers recent answers so the same question on the same sources is free."""

    def __init__(self, max_size: int = 256) -> None:
        self.max_size = max_size
        self._items: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(model: str, system: str, user: str) -> str:
        return hashlib.sha256(f"{model}\n{system}\n{user}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        return None

    def put(self, key: str, value: str) -> None:
        if self.max_size <= 0:
            return
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "openai":
        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "ollama":
        return OllamaClient(settings)
    return ExtractiveClient()
