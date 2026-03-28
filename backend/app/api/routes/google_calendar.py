"""Google Calendar sync routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    GoogleCalendarService,
    get_current_user_id,
    get_google_calendar_service,
)
from app.api.schemas import (
    GoogleCalendarAuthCallbackRead,
    GoogleCalendarAuthStartRead,
    GoogleCalendarStatusRead,
    GoogleCalendarSyncRead,
)

router = APIRouter(prefix="/google-calendar", tags=["google-calendar"])


@router.get("/status", response_model=GoogleCalendarStatusRead)
async def get_status(
    user_id: str = Depends(get_current_user_id),
    service: GoogleCalendarService = Depends(get_google_calendar_service),
) -> GoogleCalendarStatusRead:
    return await service.get_status(user_id=user_id)


@router.get("/auth/start", response_model=GoogleCalendarAuthStartRead)
async def start_auth(
    user_id: str = Depends(get_current_user_id),
    service: GoogleCalendarService = Depends(get_google_calendar_service),
) -> GoogleCalendarAuthStartRead:
    return await service.start_auth(user_id=user_id)


@router.get("/auth/callback", response_model=GoogleCalendarAuthCallbackRead)
async def complete_auth(
    code: str = Query(..., min_length=1),
    state: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    service: GoogleCalendarService = Depends(get_google_calendar_service),
) -> GoogleCalendarAuthCallbackRead:
    return await service.complete_auth(user_id=user_id, code=code, state=state)


@router.post("/sync", response_model=GoogleCalendarSyncRead)
async def sync_calendar(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    service: GoogleCalendarService = Depends(get_google_calendar_service),
) -> GoogleCalendarSyncRead:
    return await service.sync(user_id=user_id, start=start, end=end)
