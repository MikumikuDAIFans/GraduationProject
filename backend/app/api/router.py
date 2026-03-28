"""Public API router assembly for the backend."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.assistant import router as assistant_router
from app.api.routes.context import router as context_router
from app.api.routes.events import router as events_router
from app.api.routes.google_calendar import router as google_calendar_router
from app.api.routes.health import router as health_router
from app.api.routes.profile import router as profile_router
from app.api.routes.reminders import router as reminders_router
from app.api.routes.suggestions import router as suggestions_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(assistant_router)
api_router.include_router(context_router)
api_router.include_router(events_router)
api_router.include_router(google_calendar_router)
api_router.include_router(profile_router)
api_router.include_router(tasks_router)
api_router.include_router(reminders_router)
api_router.include_router(suggestions_router)
