"""Reminder repository."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.models import Reminder
from app.repositories.base import AsyncRepository


class ReminderRepository(AsyncRepository[Reminder]):
    model = Reminder

    async def list_reminders(
        self,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Reminder]:
        await self.get_or_create_user(user_id)
        stmt = select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at.asc(), Reminder.id.asc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def list_recent_task_followups(self, *, user_id: str, limit: int = 10) -> list[Reminder]:
        await self.get_or_create_user(user_id)
        stmt = (
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.target_type == "task",
                Reminder.remind_type.in_(["task_progress", "task_replan"]),
            )
            .order_by(Reminder.created_at.desc(), Reminder.id.desc())
            .limit(limit)
        )
        return await self.list(stmt)

    async def get_reminder(self, reminder_id: int, *, user_id: str) -> Reminder | None:
        await self.get_or_create_user(user_id)
        return await self.get(Reminder.id == reminder_id, Reminder.user_id == user_id)

    async def create_reminder(self, payload: Mapping[str, Any]) -> Reminder:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def update_reminder(self, reminder_id: int, *, user_id: str, payload: Mapping[str, Any]) -> Reminder | None:
        reminder = await self.get_reminder(reminder_id, user_id=user_id)
        if reminder is None:
            return None
        return await self.update(reminder, payload)

    async def delete_reminder(self, reminder_id: int, *, user_id: str) -> bool:
        reminder = await self.get_reminder(reminder_id, user_id=user_id)
        if reminder is None:
            return False
        await self.delete(reminder)
        return True
