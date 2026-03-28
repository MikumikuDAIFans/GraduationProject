"""Event repository."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Event, ScheduleChangeLog
from app.repositories.base import AsyncRepository


class EventRepository(AsyncRepository[Event]):
    model = Event

    async def list_events(
        self,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        await self.get_or_create_user(user_id)
        stmt = select(Event).where(Event.user_id == user_id).order_by(Event.start_time.asc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def get_event(self, event_id: int, *, user_id: str) -> Event | None:
        await self.get_or_create_user(user_id)
        return await self.get(Event.id == event_id, Event.user_id == user_id)

    async def get_by_external_event_id(self, *, user_id: str, external_event_id: str) -> Event | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            Event.user_id == user_id,
            Event.external_event_id == external_event_id,
        )

    async def list_events_for_task_ids(self, *, user_id: str, task_ids: list[int]) -> list[Event]:
        await self.get_or_create_user(user_id)
        if not task_ids:
            return []
        stmt = (
            select(Event)
            .where(Event.user_id == user_id, Event.linked_task_id.in_(task_ids))
            .order_by(Event.start_time.asc(), Event.id.asc())
        )
        return await self.list(stmt)

    async def create_event(self, payload: Mapping[str, Any]) -> Event:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def update_event(self, event_id: int, *, user_id: str, payload: Mapping[str, Any]) -> Event | None:
        event = await self.get_event(event_id, user_id=user_id)
        if event is None:
            return None
        return await self.update(event, payload)

    async def delete_event(self, event_id: int, *, user_id: str) -> bool:
        event = await self.get_event(event_id, user_id=user_id)
        if event is None:
            return False
        await self.delete(event)
        return True

    async def write_change_log(
        self,
        *,
        user_id: str,
        event_id: int | None,
        change_type: str,
        old_value_json: dict | None = None,
        new_value_json: dict | None = None,
        trigger_source: str = "user",
        reason: str | None = None,
    ) -> None:
        from datetime import datetime, timezone
        async with self.session_factory() as session:
            log = ScheduleChangeLog(
                user_id=user_id,
                event_id=event_id,
                change_type=change_type,
                old_value_json=old_value_json,
                new_value_json=new_value_json,
                trigger_source=trigger_source,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.commit()
