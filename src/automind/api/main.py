from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import Settings, get_settings
from ..generation.llm_client import LLMError
from ..logging import configure_logging
from ..services import Services
from .deps import get_services
from .routes import documents, export, feedback, query, settings as settings_routes, study, upload
from .schemas import HealthResponse

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = Services(settings)
        logger.info("AutoMind ready (embeddings: %s, llm: %s)",
                    app.state.services.encoder.name, app.state.services.llm.name)
        yield
        app.state.services.close()

    app = FastAPI(
        title="AutoMind",
        version=__version__,
        description="Upload documents and ask questions. Answers come with source citations.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.middleware("http")
    async def measure(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        services: Optional[Services] = getattr(request.app.state, "services", None)
        if services is not None:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            services.metrics.incr("http_requests_total")
            services.metrics.incr(f"http_{response.status_code // 100}xx")
            services.metrics.observe(f"{request.method} {path}", time.perf_counter() - started)
        return response

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, error: LLMError):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    app.include_router(upload.router)
    app.include_router(documents.router)
    app.include_router(query.router)
    app.include_router(feedback.router)
    app.include_router(study.router)
    app.include_router(settings_routes.router)
    app.include_router(export.router)

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def home() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health(services: Services = Depends(get_services)) -> HealthResponse:
        return HealthResponse(
            status="ok", version=__version__,
            documents=len(services.metadata.list_documents()),
            chunks=services.metadata.count_chunks(),
            embedding_model=services.encoder.name, llm=services.llm.name,
        )

    @app.get("/metrics", tags=["system"])
    def metrics(services: Services = Depends(get_services)) -> dict:
        snapshot = services.metrics.snapshot()
        snapshot["feedback"] = services.metadata.feedback_stats()
        snapshot["index"] = {"vectors": len(services.vectors), "keyword_chunks": len(services.bm25)}
        if hasattr(services.encoder, "hits"):
            snapshot["embedding_cache"] = {
                "hits": services.encoder.hits, "misses": services.encoder.misses
            }
        return snapshot

    return app


app = create_app()
