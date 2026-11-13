from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...generation.llm_client import LLMError
from ...services import Services
from ..deps import get_services
from ..schemas import LLMSettingsIn, LLMStatus

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm", response_model=LLMStatus)
def get_llm(services: Services = Depends(get_services)) -> LLMStatus:
    """Which answer model is active. The API key is never returned."""
    return LLMStatus(**services.llm_status())


@router.post("/llm", response_model=LLMStatus)
async def set_llm(body: LLMSettingsIn, services: Services = Depends(get_services)) -> LLMStatus:
    """Choose the answer model. A test message is sent first, so a wrong key is caught here."""
    config = body.model_dump(exclude={"test"})
    try:
        status = await run_in_threadpool(services.configure_llm, config, body.test)
    except LLMError as error:
        raise HTTPException(400, str(error)) from error
    return LLMStatus(**status)
