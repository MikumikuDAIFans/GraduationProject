"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


def _ensure_runtime_directories() -> None:
    """Create runtime directories required by the backend."""
    settings = get_settings()
    Path(settings.sqlite_db_file).parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize runtime dependencies during startup."""
    _ensure_runtime_directories()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.project_name,
        version=settings.project_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8888",
            "http://127.0.0.1:8888",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.router import api_router
    from app.api.ws import router as ws_router

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(ws_router)

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.project_name,
            "status": "ok",
            "environment": settings.app_env,
        }

    return app


app = create_app()
