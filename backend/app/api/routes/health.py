"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import HealthRead
from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthRead)
async def health_check() -> HealthRead:
    settings = get_settings()
    database_path = settings.sqlite_db_file
    return HealthRead(
        service="Personal Affairs Assistant",
        version="0.1.0",
        environment=settings.app_env,
        database_path=str(database_path),
        database_ready=database_path.exists(),
    )
