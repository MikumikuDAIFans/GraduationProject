"""Reminder service layer."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.api.schemas import ReminderRead
from app.db.session import get_sessionmaker
from app.repositories.reminders import ReminderRepository


class ReminderService:
    """Reminder CRUD service."""

    def __init__(self) -> None:
        self.repository = ReminderRepository(get_sessionmaker())

    async def list_reminders(self, user_id: str) -> list[ReminderRead]:
        return [ReminderRead.model_validate(item) for item in await self.repository.list_reminders(user_id=user_id)]

    async def mark_read(self, user_id: str, reminder_id: int) -> ReminderRead:
        reminder = await self.repository.update_reminder(reminder_id, user_id=user_id, payload={"status": "read"})
        if reminder is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reminder not found")
        return ReminderRead.model_validate(reminder)
