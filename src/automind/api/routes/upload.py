from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from ...ingestion.ocr import OCRUnavailable
from ...ingestion.parsers import EmptyDocumentError, UnsupportedFileType
from ...services import Services
from ..deps import get_services
from ..schemas import DocumentOut

router = APIRouter(tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload(
    response: Response,
    file: UploadFile = File(...),
    services: Services = Depends(get_services),
) -> DocumentOut:
    """Upload almost any document or image. It is read, split into chunks and indexed.

    Supported: PDF (including scans), Word, PowerPoint, Excel, CSV, OpenDocument, RTF, EPUB,
    HTML, text and code files, and images (text in pictures is read with text recognition).
    """
    if not file.filename:
        raise HTTPException(400, "The file needs a name")
    limit = services.settings.max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"File is larger than {services.settings.max_upload_mb} MB")
    if not content:
        raise HTTPException(400, "The file is empty")
    try:
        result = await run_in_threadpool(services.ingestion.ingest, file.filename, content)
    except UnsupportedFileType as error:
        raise HTTPException(415, str(error)) from error
    except OCRUnavailable as error:
        raise HTTPException(501, str(error)) from error
    except EmptyDocumentError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(422, f"Could not read this file: {error}") from error
    services.metrics.incr("uploads_total")
    if result.duplicate:
        response.status_code = 200
    record = result.document
    return DocumentOut(
        id=record.id, filename=record.filename, n_pages=record.n_pages,
        n_chunks=record.n_chunks, size_bytes=record.size_bytes,
        created_at=record.created_at, duplicate=result.duplicate,
    )
