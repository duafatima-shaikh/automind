"""All settings in one place. Every value can be changed with an AUTOMIND_ environment variable."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTOMIND_", extra="ignore")

    data_dir: Path = Path("data")
    log_level: str = "INFO"
    max_upload_mb: int = 25

    # Reading images and scanned pages
    ocr_backend: str = "auto"  # auto | rapidocr | tesseract | none
    ocr_min_chars_per_page: int = 20  # PDF pages with less text than this are treated as scans
    ocr_max_pages: int = 100  # most scanned pages to read per file
    image_descriptions: bool = False  # ask the OpenAI compatible model to describe pictures
    vision_model: Optional[str] = None  # defaults to llm_model
    max_table_rows: int = 20000  # most spreadsheet rows to read per sheet

    # Embeddings
    embedding_backend: str = "auto"  # auto | sentence-transformers | hash
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hash_embedding_dim: int = 384
    embedding_cache: bool = True

    # Chunking (characters)
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Retrieval
    top_k: int = 5
    candidate_k: int = 20
    use_bm25: bool = True
    reranker: str = "lexical"  # lexical | cross-encoder | none
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    use_faiss: bool = True
    # If the best chunk shares less than this share of the question words, we say "not found".
    min_query_overlap: float = 0.25

    # Language model
    llm_provider: str = "extractive"  # extractive | openai | ollama
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_url: str = "http://localhost:11434"
    llm_cache_size: int = 256
    ollama_num_ctx: int = 8192  # how much text a local Ollama model may read at once

    # Study tools (summaries, notes, quizzes, exams)
    study_context_chars: int = 24000  # most material sent to the model in one request
    study_max_parts: int = 10  # most pieces a very long document is split into for a summary
    default_language: str = "en"  # en | ur | sd

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.embedding_backend not in {"auto", "sentence-transformers", "hash"}:
            raise ValueError("embedding_backend must be auto, sentence-transformers or hash")
        if self.reranker not in {"lexical", "cross-encoder", "none"}:
            raise ValueError("reranker must be lexical, cross-encoder or none")
        if self.ocr_backend not in {"auto", "rapidocr", "tesseract", "none"}:
            raise ValueError("ocr_backend must be auto, rapidocr, tesseract or none")
        if self.llm_provider not in {"extractive", "openai", "ollama"}:
            raise ValueError("llm_provider must be extractive, openai or ollama")
        if self.default_language not in {"en", "ur", "sd"}:
            raise ValueError("default_language must be en, ur or sd")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
