from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ...generation.study import StudyError, StudyRequest
from ...services import Services
from ..deps import get_services
from ..schemas import StudyBody, StudyResponse
from ..sse import sse

router = APIRouter(tags=["study"])


def _request(body: StudyBody) -> StudyRequest:
    return StudyRequest(
        task=body.task, document_ids=body.document_ids, topic=body.topic, pages=body.pages,
        instructions=body.instructions, language=body.language, difficulty=body.difficulty,
        length=body.length, count=body.count, total_marks=body.total_marks,
    )


@router.post("/study", response_model=StudyResponse)
async def study(body: StudyBody, services: Services = Depends(get_services)) -> StudyResponse:
    """Make a summary, explanation, notes, quiz, flashcards, assignment or exam paper."""
    try:
        result = await run_in_threadpool(services.study.run_all, _request(body))
    except StudyError as error:
        raise HTTPException(422, str(error)) from error
    return StudyResponse(**result)


@router.post("/study/stream")
def study_stream(body: StudyBody, services: Services = Depends(get_services)):
    """Same as /study but streamed. Events: meta, status, token (many), final, error."""
    request = _request(body)

    def generate():
        try:
            for event in services.study.run(request):
                yield sse(event["type"], event)
        except Exception as error:  # noqa: BLE001
            yield sse("error", {"message": str(error)})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
