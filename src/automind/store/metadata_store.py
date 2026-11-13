"""SQLite storage for documents, chunk text, query history and feedback."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from ..ingestion.chunker import Chunk


@dataclass
class DocumentRecord:
    id: str
    filename: str
    sha256: str
    n_pages: int
    n_chunks: int
    size_bytes: int
    created_at: str


@dataclass
class StoredChunk:
    id: str
    doc_id: str
    filename: str
    page: int
    index: int
    text: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MetadataStore:
    def __init__(self, path: Path) -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
                n_pages INTEGER NOT NULL, n_chunks INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                filename TEXT NOT NULL, page INTEGER NOT NULL,
                idx INTEGER NOT NULL, text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id);
            CREATE TABLE IF NOT EXISTS queries (
                id TEXT PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL,
                found INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id TEXT NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
                helpful INTEGER NOT NULL, comment TEXT, created_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    # ---- documents ----
    def add_document(
        self, doc_id: str, filename: str, sha256: str, n_pages: int, n_chunks: int, size_bytes: int
    ) -> DocumentRecord:
        created = _now()
        with self._lock:
            self._db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, filename, sha256, n_pages, n_chunks, size_bytes, created),
            )
            self._db.commit()
        return DocumentRecord(doc_id, filename, sha256, n_pages, n_chunks, size_bytes, created)

    @staticmethod
    def _doc(row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(**{k: row[k] for k in row.keys()})

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        with self._lock:
            row = self._db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._doc(row) if row else None

    def find_document_by_hash(self, sha256: str) -> Optional[DocumentRecord]:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
        return self._doc(row) if row else None

    def list_documents(self) -> list[DocumentRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [self._doc(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self._db.commit()
        return cursor.rowcount > 0

    # ---- chunks ----
    def add_chunks(self, filename: str, chunks: Iterable[Chunk]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                [(c.id, c.doc_id, filename, c.page, c.index, c.text) for c in chunks],
            )
            self._db.commit()

    @staticmethod
    def _chunk(row: sqlite3.Row) -> StoredChunk:
        return StoredChunk(row["id"], row["doc_id"], row["filename"], row["page"],
                           row["idx"], row["text"])

    def get_chunks(self, chunk_ids: Sequence[str]) -> dict[str, StoredChunk]:
        found: dict[str, StoredChunk] = {}
        with self._lock:
            for start in range(0, len(chunk_ids), 500):
                batch = list(chunk_ids[start:start + 500])
                marks = ",".join("?" * len(batch))
                for row in self._db.execute(
                    f"SELECT * FROM chunks WHERE id IN ({marks})", batch
                ):
                    found[row["id"]] = self._chunk(row)
        return found

    def chunk_ids_for_documents(self, doc_ids: Iterable[str]) -> set[str]:
        ids: set[str] = set()
        with self._lock:
            for doc_id in doc_ids:
                for row in self._db.execute("SELECT id FROM chunks WHERE doc_id = ?", (doc_id,)):
                    ids.add(row["id"])
        return ids

    def get_document_chunks(self, doc_id: str) -> list[StoredChunk]:
        """All chunks of one document in reading order."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY idx", (doc_id,)
            ).fetchall()
        return [self._chunk(row) for row in rows]

    def iter_chunks(self) -> Iterator[StoredChunk]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM chunks").fetchall()
        for row in rows:
            yield self._chunk(row)

    def count_chunks(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # ---- queries and feedback ----
    def log_query(self, query_id: str, question: str, answer: str, found: bool) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO queries VALUES (?, ?, ?, ?, ?)",
                (query_id, question, answer, int(found), _now()),
            )
            self._db.commit()

    def query_exists(self, query_id: str) -> bool:
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM queries WHERE id = ?", (query_id,)
            ).fetchone() is not None

    def add_feedback(self, query_id: str, helpful: bool, comment: Optional[str]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO feedback (query_id, helpful, comment, created_at) VALUES (?,?,?,?)",
                (query_id, int(helpful), comment, _now()),
            )
            self._db.commit()

    def feedback_stats(self) -> dict:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS total, COALESCE(SUM(helpful), 0) AS helpful FROM feedback"
            ).fetchone()
            queries = self._db.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
        return {"total": row["total"], "helpful": row["helpful"],
                "not_helpful": row["total"] - row["helpful"], "queries_logged": queries}

    def close(self) -> None:
        with self._lock:
            self._db.close()
