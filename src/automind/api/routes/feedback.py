from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...services import Services
from ..deps import get_services
from ..schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(body: FeedbackRequest, services: Services = Depends(get_services)) -> FeedbackResponse:
    if not services.metadata.query_exists(body.query_id):
        raise HTTPException(404, "Unknown query_id")
    services.metadata.add_feedback(body.query_id, body.helpful, body.comment)
    services.metrics.incr("feedback_helpful" if body.helpful else "feedback_not_helpful")
    return FeedbackResponse()
