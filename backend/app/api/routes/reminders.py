"""Reminder routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.api.deps import ReminderService, get_current_user_id, get_reminder_service
from app.api.schemas import OperationResult, ReminderRead

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderRead])
async def list_reminders(
    user_id: str = Depends(get_current_user_id),
    service: ReminderService = Depends(get_reminder_service),
) -> list[ReminderRead]:
    return await service.list_reminders(user_id=user_id)


@router.post("/{reminder_id}/read", response_model=ReminderRead)
async def mark_reminder_read(
    reminder_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRead:
    return await service.mark_read(user_id=user_id, reminder_id=reminder_id)
