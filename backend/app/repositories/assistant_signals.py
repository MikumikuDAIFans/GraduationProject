"""Assistant signal repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from app.models import AssistantSignal
from app.repositories.base import AsyncRepository


ACTIVE_SIGNAL_STATUSES = ("new", "evaluated", "proposal_created", "cooling")


class AssistantSignalRepository(AsyncRepository[AssistantSignal]):
    model = AssistantSignal

    async def create_signal(self, payload: Mapping[str, Any]) -> AssistantSignal:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def get_signal(self, signal_id: int, *, user_id: str) -> AssistantSignal | None:
        await self.get_or_create_user(user_id)
        return await self.get(AssistantSignal.id == signal_id, AssistantSignal.user_id == user_id)

    async def list_signals(
        self,
        *,
        user_id: str,
        statuses: Sequence[str] | None = None,
        signal_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssistantSignal]:
        await self.get_or_create_user(user_id)
        stmt = select(AssistantSignal).where(AssistantSignal.user_id == user_id)
        if statuses:
            stmt = stmt.where(AssistantSignal.status.in_(list(statuses)))
        if signal_type:
            stmt = stmt.where(AssistantSignal.signal_type == signal_type)
        stmt = stmt.order_by(AssistantSignal.created_at.desc(), AssistantSignal.id.desc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def get_active_by_dedup_key(self, *, user_id: str, dedup_key: str) -> AssistantSignal | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            AssistantSignal.user_id == user_id,
            AssistantSignal.dedup_key == dedup_key,
            AssistantSignal.status.in_(list(ACTIVE_SIGNAL_STATUSES)),
        )

    async def get_blocking_by_dedup_key(self, *, user_id: str, dedup_key: str, now: datetime) -> AssistantSignal | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            AssistantSignal.user_id == user_id,
            AssistantSignal.dedup_key == dedup_key,
            or_(
                AssistantSignal.status.in_(list(ACTIVE_SIGNAL_STATUSES)),
                AssistantSignal.cooldown_until > now,
            ),
        )

    async def update_signal(
        self,
        signal_id: int,
        *,
        user_id: str,
        payload: Mapping[str, Any],
    ) -> AssistantSignal | None:
        signal = await self.get_signal(signal_id, user_id=user_id)
        if signal is None:
            return None
        return await self.update(signal, payload)
