"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import HealthAIRead, HealthRead, PerformanceMetricsRead
from app.core.config import get_settings
from app.core.metrics import metrics_snapshot
from app.tools.gemini import GeminiClient

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


@router.get("/ai", response_model=HealthAIRead)
async def ai_health() -> HealthAIRead:
    settings = get_settings()
    return HealthAIRead.model_validate(
        GeminiClient.health_status(enabled=settings.llm_provider == "gemini" and bool(settings.gemini_api_key), provider=settings.llm_provider)
    )


@router.get("/performance", response_model=PerformanceMetricsRead)
async def performance_health() -> PerformanceMetricsRead:
    return PerformanceMetricsRead.model_validate(metrics_snapshot())
