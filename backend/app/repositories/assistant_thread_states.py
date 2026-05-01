"""Assistant thread-state repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select

from app.models import AssistantThreadState
from app.repositories.base import AsyncRepository


class AssistantThreadStateRepository(AsyncRepository[AssistantThreadState]):
    model = AssistantThreadState

    async def create_thread_state(self, payload: Mapping[str, Any]) -> AssistantThreadState:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def get_thread_state(self, thread_state_id: int, *, user_id: str) -> AssistantThreadState | None:
        await self.get_or_create_user(user_id)
        return await self.get(AssistantThreadState.id == thread_state_id, AssistantThreadState.user_id == user_id)

    async def list_thread_states(
        self,
        *,
        user_id: str,
        session_id: int | None = None,
        statuses: Sequence[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssistantThreadState]:
        await self.get_or_create_user(user_id)
        stmt = select(AssistantThreadState).where(AssistantThreadState.user_id == user_id)
        if session_id is not None:
            stmt = stmt.where(AssistantThreadState.session_id == session_id)
        if statuses:
            stmt = stmt.where(AssistantThreadState.status.in_(list(statuses)))
        stmt = stmt.order_by(AssistantThreadState.updated_at.desc(), AssistantThreadState.id.desc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def update_thread_state(
        self,
        thread_state_id: int,
        *,
        user_id: str,
        payload: Mapping[str, Any],
    ) -> AssistantThreadState | None:
        thread_state = await self.get_thread_state(thread_state_id, user_id=user_id)
        if thread_state is None:
            return None
        return await self.update(thread_state, payload)
