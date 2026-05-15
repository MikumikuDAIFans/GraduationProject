"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import get_settings
from app.core.error_handler import global_exception_handler
from app.core.logging import configure_logging
from app.core.metrics import record_request
from app.core.vector_store import VectorStore

_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Get the global vector store singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(persist_directory="./chroma_db")
    return _vector_store


def _ensure_runtime_directories() -> None:
    """Create runtime directories required by the backend."""
    settings = get_settings()
    Path(settings.sqlite_db_file).parent.mkdir(parents=True, exist_ok=True)
    Path("./chroma_db").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize runtime dependencies during startup."""
    _ensure_runtime_directories()
    logger.info("Vector store initialized at ./chroma_db")
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=settings.project_name,
        version=settings.project_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.router import api_router
    from app.api.routes.debug import log_request
    from app.api.ws import router as ws_router

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(ws_router)
    app.add_exception_handler(Exception, global_exception_handler)

    @app.middleware("http")
    async def request_metrics(request, call_next):
        started = perf_counter()
        request_id = request.headers.get("X-Request-Id") or uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        elapsed_ms = (perf_counter() - started) * 1000
        record_request(request.url.path, elapsed_ms)
        log_request(request.method, request.url.path, response.status_code, elapsed_ms, request_id)
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Request-Id"] = request_id
        component = "request.slow" if elapsed_ms >= settings.slow_request_threshold_ms else "request"
        logger.bind(component=component).info(
            "{method} {path} -> {status_code} in {elapsed_ms:.2f} ms request_id={request_id}",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            request_id=request_id,
        )
        return response

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.project_name,
            "status": "ok",
            "environment": settings.app_env,
        }

    return app


app = create_app()
