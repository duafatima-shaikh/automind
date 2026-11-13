"""Request and response shapes. These also produce the OpenAPI documentation at /docs."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["en", "ur", "sd"]


class DocumentOut(BaseModel):
    id: str
    filename: str
    n_pages: int
    n_chunks: int
    size_bytes: int
    created_at: str
    duplicate: bool = False


class HistoryTurn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=6000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    document_ids: Optional[list[str]] = Field(
        default=None, description="Only search inside these documents"
    )
    language: Language = Field(default="en", description="Language of the answer")
    history: list[HistoryTurn] = Field(
        default_factory=list, max_length=6,
        description="Earlier questions and answers, so follow up questions make sense",
    )

    def history_pairs(self) -> list[tuple[str, str]]:
        return [(turn.question, turn.answer) for turn in self.history]


class SourceOut(BaseModel):
    number: int
    chunk_id: str
    doc_id: str
    filename: str
    page: int
    text: str
    score: float
    cited: bool


class CitationCheck(BaseModel):
    valid: list[int]
    removed: list[int]
    grounding_score: float = Field(description="Share of sentences backed by their cited source")


class QueryResponse(BaseModel):
    query_id: str
    answer: str
    found: bool
    sources: list[SourceOut]
    citation_check: CitationCheck
    model: str
    prompt_version: str
    cached: bool
    timings_ms: dict[str, float]


class FeedbackRequest(BaseModel):
    query_id: str
    helpful: bool
    comment: Optional[str] = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    status: str = "saved"


class HealthResponse(BaseModel):
    status: str
    version: str
    documents: int
    chunks: int
    embedding_model: str
    llm: str


class StudyBody(BaseModel):
    task: Literal["summary", "explain", "notes", "quiz", "flashcards", "assignment",
                  "mid_exam", "final_exam"]
    document_ids: Optional[list[str]] = Field(
        default=None, description="Use these documents (default: all)")
    topic: Optional[str] = Field(default=None, max_length=300,
                                 description="Find and use only this part of the material")
    pages: Optional[str] = Field(default=None, max_length=100,
                                 description='Page numbers, for example "3-5, 8"')
    instructions: Optional[str] = Field(default=None, max_length=600,
                                        description="Extra wishes in the student's own words")
    language: Language = "en"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    length: Literal["short", "medium", "detailed"] = "medium"
    count: Optional[int] = Field(default=None, ge=1, le=50,
                                 description="Number of questions or flashcards")
    total_marks: Optional[int] = Field(default=None, ge=5, le=200)


class StudySource(BaseModel):
    filename: str
    pages: list[int]


class StudyResponse(BaseModel):
    task: str
    language: str
    markdown: str
    model: str
    sampled: bool = Field(description="True if a very long document was only partly used")
    offline: bool = Field(description="True if the basic engine (no AI model) wrote this")
    sources: list[StudySource]


class LLMSettingsIn(BaseModel):
    provider: Literal["extractive", "openai", "ollama"]
    model: Optional[str] = Field(default=None, max_length=120)
    api_key: Optional[str] = Field(default=None, max_length=400)
    base_url: Optional[str] = Field(default=None, max_length=300)
    ollama_url: Optional[str] = Field(default=None, max_length=300)
    test: bool = Field(default=True, description="Send a test message before saving")


class LLMStatus(BaseModel):
    provider: str
    model: str
    name: str
    real: bool
    base_url: str
    ollama_url: str
    has_key: bool
    embedding: str
    semantic_search: bool


class ExportBody(BaseModel):
    markdown: str = Field(min_length=1, max_length=300_000)
    title: str = Field(default="", max_length=200)
    language: Language = "en"


class PageText(BaseModel):
    page: int
    text: str


class DocumentText(BaseModel):
    id: str
    filename: str
    pages: list[PageText]


def query_response(query_id: str, answer, timings_ms: dict) -> QueryResponse:
    return QueryResponse(
        query_id=query_id,
        answer=answer.text,
        found=answer.found,
        sources=[SourceOut(**s.__dict__) for s in answer.sources],
        citation_check=CitationCheck(
            valid=answer.report.valid,
            removed=answer.removed_citations,
            grounding_score=round(answer.grounding_score, 3),
        ),
        model=answer.model,
        prompt_version=answer.prompt_version,
        cached=answer.cached,
        timings_ms=timings_ms,
    )
