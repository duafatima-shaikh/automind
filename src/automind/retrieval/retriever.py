"""Hybrid retrieval: meaning search + keyword search, merged, reranked, then diversified."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ..config import Settings
from ..embeddings.encoder import Encoder
from ..store.bm25_store import BM25Store
from ..store.metadata_store import MetadataStore, StoredChunk
from ..store.vector_store import VectorStore
from .mmr import mmr_select
from .reranker import Reranker

RRF_K = 60  # standard constant for reciprocal rank fusion


@dataclass(frozen=True)
class RetrievalOptions:
    use_vector: bool = True
    use_bm25: bool = True
    use_reranker: bool = True
    use_mmr: bool = True


@dataclass
class RetrievedChunk:
    chunk: StoredChunk
    score: float
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]]) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return fused


class Retriever:
    def __init__(
        self,
        settings: Settings,
        encoder: Encoder,
        vectors: VectorStore,
        bm25: BM25Store,
        metadata: MetadataStore,
        reranker: Optional[Reranker],
    ) -> None:
        self.settings = settings
        self.encoder = encoder
        self.vectors = vectors
        self.bm25 = bm25
        self.metadata = metadata
        self.reranker = reranker

    def default_options(self) -> RetrievalOptions:
        return RetrievalOptions(
            use_vector=True,
            use_bm25=self.settings.use_bm25,
            use_reranker=self.reranker is not None,
            use_mmr=self.settings.use_mmr,
        )

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        document_ids: Optional[Sequence[str]] = None,
        options: Optional[RetrievalOptions] = None,
    ) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.top_k
        options = options or self.default_options()
        candidate_k = max(self.settings.candidate_k, top_k)
        allowed_docs = set(document_ids) if document_ids else None
        allowed_chunks = (
            self.metadata.chunk_ids_for_documents(allowed_docs) if allowed_docs else None
        )

        vector_hits: list[tuple[str, float]] = []
        keyword_hits: list[tuple[str, float]] = []
        if options.use_vector:
            query_vector = self.encoder.encode([query])[0]
            vector_hits = self.vectors.search(query_vector, candidate_k, allowed=allowed_chunks)
        if options.use_bm25:
            keyword_hits = self.bm25.search(query, candidate_k, allowed_docs=allowed_docs)

        vector_rank = {cid: r for r, (cid, _) in enumerate(vector_hits, start=1)}
        keyword_rank = {cid: r for r, (cid, _) in enumerate(keyword_hits, start=1)}
        fused = reciprocal_rank_fusion(
            [[cid for cid, _ in vector_hits], [cid for cid, _ in keyword_hits]]
        )
        if not fused:
            return []

        ordered = sorted(fused, key=fused.get, reverse=True)[:candidate_k]
        stored = self.metadata.get_chunks(ordered)
        ordered = [cid for cid in ordered if cid in stored]
        top_fused = max(fused[cid] for cid in ordered) or 1.0
        scores = {cid: fused[cid] / top_fused for cid in ordered}

        if options.use_reranker and self.reranker is not None:
            rerank_scores = self.reranker.score(query, [stored[cid].text for cid in ordered])
            scores = {
                cid: 0.6 * rr + 0.4 * scores[cid] for cid, rr in zip(ordered, rerank_scores)
            }
            ordered.sort(key=lambda cid: scores[cid], reverse=True)

        if options.use_mmr and len(ordered) > 1:
            pool = ordered[: max(top_k * 3, top_k)]
            found = self.vectors.get(pool)
            matrix = np.vstack(
                [found.get(cid, np.zeros(self.encoder.dim, dtype=np.float32)) for cid in pool]
            )
            peak = max(scores[cid] for cid in pool) or 1.0
            picks = mmr_select(
                matrix, [scores[cid] / peak for cid in pool], top_k, self.settings.mmr_lambda
            )
            ordered = [pool[i] for i in picks]
        else:
            ordered = ordered[:top_k]

        return [
            RetrievedChunk(stored[cid], scores[cid], vector_rank.get(cid), keyword_rank.get(cid))
            for cid in ordered
        ]
