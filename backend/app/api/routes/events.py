"""Event routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import EventService, get_current_user_id, get_event_service
from app.api.schemas import EventCreate, EventRead, EventUpdate, OperationResult

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
async def list_events(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    service: EventService = Depends(get_event_service),
) -> list[EventRead]:
    return await service.list_events(user_id=user_id, start=start, end=end)


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    user_id: str = Depends(get_current_user_id),
    service: EventService = Depends(get_event_service),
) -> EventRead:
    return await service.create_event(user_id=user_id, payload=payload)


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: EventService = Depends(get_event_service),
) -> EventRead:
    return await service.get_event(user_id=user_id, event_id=event_id)


@router.put("/{event_id}", response_model=EventRead)
async def update_event(
    payload: EventUpdate,
    event_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: EventService = Depends(get_event_service),
) -> EventRead:
    return await service.update_event(user_id=user_id, event_id=event_id, payload=payload)


@router.delete("/{event_id}", response_model=OperationResult)
async def delete_event(
    event_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: EventService = Depends(get_event_service),
) -> OperationResult:
    await service.delete_event(user_id=user_id, event_id=event_id)
    return OperationResult(message="event deleted", id=event_id)
