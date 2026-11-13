"""Ingestion: parse a file, chunk it, embed the chunks, and save everything."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass

from ..config import Settings
from ..embeddings.encoder import Encoder
from ..store.bm25_store import BM25Store
from ..store.metadata_store import DocumentRecord, MetadataStore
from ..store.vector_store import VectorStore
from .chunker import chunk_pages
from .parsers import parse_document

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    document: DocumentRecord
    duplicate: bool


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        metadata: MetadataStore,
        encoder: Encoder,
        vectors: VectorStore,
        bm25: BM25Store,
        write_lock: threading.RLock,
    ) -> None:
        self.settings = settings
        self.metadata = metadata
        self.encoder = encoder
        self.vectors = vectors
        self.bm25 = bm25
        self.write_lock = write_lock

    def ingest(self, filename: str, content: bytes) -> IngestResult:
        digest = hashlib.sha256(content).hexdigest()
        existing = self.metadata.find_document_by_hash(digest)
        if existing:
            return IngestResult(existing, duplicate=True)

        started = time.perf_counter()
        pages = parse_document(filename, content, self.settings)
        doc_id = uuid.uuid4().hex[:12]
        chunks = chunk_pages(doc_id, pages, self.settings.chunk_size, self.settings.chunk_overlap)
        vectors = self.encoder.encode([c.text for c in chunks])

        with self.write_lock:
            record = self.metadata.add_document(
                doc_id=doc_id,
                filename=filename,
                sha256=digest,
                n_pages=len(pages),
                n_chunks=len(chunks),
                size_bytes=len(content),
            )
            self.metadata.add_chunks(filename, chunks)
            self.vectors.add([c.id for c in chunks], vectors)
            self.vectors.save()
            for chunk in chunks:
                self.bm25.add(chunk.id, doc_id, chunk.text)
        logger.info(
            "Ingested %s: %d pages, %d chunks in %.2fs",
            filename, len(pages), len(chunks), time.perf_counter() - started,
        )
        return IngestResult(record, duplicate=False)

    def delete(self, doc_id: str) -> bool:
        with self.write_lock:
            chunk_ids = self.metadata.chunk_ids_for_documents({doc_id})
            deleted = self.metadata.delete_document(doc_id)
            if deleted:
                self.vectors.delete(list(chunk_ids))
                self.vectors.save()
                self.bm25.remove_document(doc_id)
            return deleted
