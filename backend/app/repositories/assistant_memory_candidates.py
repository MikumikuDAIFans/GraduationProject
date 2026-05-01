"""Assistant memory update candidate repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select

from app.models import AssistantMemoryUpdateCandidate
from app.repositories.base import AsyncRepository


ACTIVE_MEMORY_CANDIDATE_STATUSES = ("proposed", "confirmed")


class AssistantMemoryCandidateRepository(AsyncRepository[AssistantMemoryUpdateCandidate]):
    model = AssistantMemoryUpdateCandidate

    async def create_candidate(self, payload: Mapping[str, Any]) -> AssistantMemoryUpdateCandidate:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def get_candidate(self, candidate_id: int, *, user_id: str) -> AssistantMemoryUpdateCandidate | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            AssistantMemoryUpdateCandidate.id == candidate_id,
            AssistantMemoryUpdateCandidate.user_id == user_id,
        )

    async def list_candidates(
        self,
        *,
        user_id: str,
        statuses: Sequence[str] | None = None,
        memory_type: str | None = None,
        limit: int = 50,
    ) -> list[AssistantMemoryUpdateCandidate]:
        await self.get_or_create_user(user_id)
        stmt = select(AssistantMemoryUpdateCandidate).where(AssistantMemoryUpdateCandidate.user_id == user_id)
        if statuses:
            stmt = stmt.where(AssistantMemoryUpdateCandidate.status.in_(list(statuses)))
        if memory_type:
            stmt = stmt.where(AssistantMemoryUpdateCandidate.memory_type == memory_type)
        stmt = stmt.order_by(AssistantMemoryUpdateCandidate.created_at.desc(), AssistantMemoryUpdateCandidate.id.desc()).limit(limit)
        return await self.list(stmt)

    async def get_active_by_dedup_key(
        self,
        *,
        user_id: str,
        dedup_key: str,
    ) -> AssistantMemoryUpdateCandidate | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            AssistantMemoryUpdateCandidate.user_id == user_id,
            AssistantMemoryUpdateCandidate.dedup_key == dedup_key,
            AssistantMemoryUpdateCandidate.status.in_(list(ACTIVE_MEMORY_CANDIDATE_STATUSES)),
        )

    async def update_candidate(
        self,
        candidate_id: int,
        *,
        user_id: str,
        payload: Mapping[str, Any],
    ) -> AssistantMemoryUpdateCandidate | None:
        candidate = await self.get_candidate(candidate_id, user_id=user_id)
        if candidate is None:
            return None
        return await self.update(candidate, payload)
