from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ...utils.docx_export import markdown_to_docx
from ..schemas import ExportBody

router = APIRouter(prefix="/export", tags=["export"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/docx")
async def export_docx(body: ExportBody) -> Response:
    """Turn generated Markdown (notes, exam paper...) into a Word file."""
    data = await run_in_threadpool(
        markdown_to_docx, body.markdown, body.title, body.language in ("ur", "sd"))
    return Response(content=data, media_type=DOCX,
                    headers={"Content-Disposition": 'attachment; filename="automind.docx"'})
