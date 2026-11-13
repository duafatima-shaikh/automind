from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ...services import Services
from ..deps import get_services
from ..schemas import QueryRequest, QueryResponse, SourceOut, query_response
from ..sse import sse as _sse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, services: Services = Depends(get_services)) -> QueryResponse:
    """Ask a question. Returns the answer, the sources used, and a citation check."""
    result = await run_in_threadpool(
        services.answer_question, body.question, body.top_k, body.document_ids,
        body.language, body.history_pairs()
    )
    return query_response(result.query_id, result.answer, result.timings_ms)


@router.post("/query/stream")
def query_stream(body: QueryRequest, services: Services = Depends(get_services)):
    """Same as /query but streamed. Events: sources, token (many), final, error."""

    def generate():
        try:
            for event in services.stream_question(body.question, body.top_k, body.document_ids,
                                                  body.language, body.history_pairs()):
                if event["type"] == "sources":
                    payload = [SourceOut(**s.__dict__).model_dump() for s in event["sources"]]
                    yield _sse("sources", {"sources": payload})
                elif event["type"] == "token":
                    yield _sse("token", {"text": event["text"]})
                else:
                    response = query_response(event["query_id"], event["answer"],
                                              event["timings_ms"])
                    yield _sse("final", response.model_dump())
        except Exception as error:  # noqa: BLE001
            yield _sse("error", {"message": str(error)})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
