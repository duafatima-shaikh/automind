from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...services import Services
from ..deps import get_services
from ..schemas import DocumentOut, DocumentText, PageText

router = APIRouter(tags=["documents"])


def _out(record) -> DocumentOut:
    return DocumentOut(
        id=record.id, filename=record.filename, n_pages=record.n_pages,
        n_chunks=record.n_chunks, size_bytes=record.size_bytes, created_at=record.created_at,
    )


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(services: Services = Depends(get_services)) -> list[DocumentOut]:
    return [_out(r) for r in services.metadata.list_documents()]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, services: Services = Depends(get_services)) -> DocumentOut:
    record = services.metadata.get_document(doc_id)
    if record is None:
        raise HTTPException(404, "Document not found")
    return _out(record)


@router.get("/documents/{doc_id}/text", response_model=DocumentText)
async def get_document_text(doc_id: str, services: Services = Depends(get_services)) -> DocumentText:
    """The text of a document, page by page (used by the reader and read aloud)."""
    record = services.metadata.get_document(doc_id)
    pages = await run_in_threadpool(services.document_pages, doc_id)
    if record is None or pages is None:
        raise HTTPException(404, "Document not found")
    return DocumentText(id=record.id, filename=record.filename,
                        pages=[PageText(**p) for p in pages])


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, services: Services = Depends(get_services)) -> None:
    if not await run_in_threadpool(services.ingestion.delete, doc_id):
        raise HTTPException(404, "Document not found")
