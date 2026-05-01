"""Assistant proposal repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select

from app.models import AssistantProposal
from app.repositories.base import AsyncRepository


ACTIVE_PROPOSAL_STATUSES = ("draft", "pending", "accepted", "execution_pending", "execution_failed")


class AssistantProposalRepository(AsyncRepository[AssistantProposal]):
    model = AssistantProposal

    async def create_proposal(self, payload: Mapping[str, Any]) -> AssistantProposal:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def get_proposal(self, proposal_id: int, *, user_id: str) -> AssistantProposal | None:
        await self.get_or_create_user(user_id)
        return await self.get(AssistantProposal.id == proposal_id, AssistantProposal.user_id == user_id)

    async def list_proposals(
        self,
        *,
        user_id: str,
        statuses: Sequence[str] | None = None,
        proposal_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssistantProposal]:
        await self.get_or_create_user(user_id)
        stmt = select(AssistantProposal).where(AssistantProposal.user_id == user_id)
        if statuses:
            stmt = stmt.where(AssistantProposal.status.in_(list(statuses)))
        if proposal_type:
            stmt = stmt.where(AssistantProposal.proposal_type == proposal_type)
        stmt = stmt.order_by(AssistantProposal.created_at.desc(), AssistantProposal.id.desc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def list_active_proposals(self, *, user_id: str, limit: int = 20) -> list[AssistantProposal]:
        return await self.list_proposals(user_id=user_id, statuses=ACTIVE_PROPOSAL_STATUSES, limit=limit)

    async def get_active_by_dedup_key(self, *, user_id: str, dedup_key: str) -> AssistantProposal | None:
        await self.get_or_create_user(user_id)
        return await self.get(
            AssistantProposal.user_id == user_id,
            AssistantProposal.dedup_key == dedup_key,
            AssistantProposal.status.in_(list(ACTIVE_PROPOSAL_STATUSES)),
        )

    async def list_by_dedup_key(self, *, user_id: str, dedup_key: str, limit: int = 20) -> list[AssistantProposal]:
        await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantProposal)
            .where(
                AssistantProposal.user_id == user_id,
                AssistantProposal.dedup_key == dedup_key,
            )
            .order_by(AssistantProposal.created_at.desc(), AssistantProposal.id.desc())
            .limit(limit)
        )
        return await self.list(stmt)

    async def list_due_for_expiry(
        self,
        *,
        now: datetime,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[AssistantProposal]:
        if user_id:
            await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantProposal)
            .where(
                AssistantProposal.status.in_(["draft", "pending", "accepted", "execution_failed"]),
                AssistantProposal.expires_at.is_not(None),
                AssistantProposal.expires_at <= now,
            )
            .order_by(AssistantProposal.expires_at.asc(), AssistantProposal.id.asc())
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(AssistantProposal.user_id == user_id)
        return await self.list(stmt)

    async def count_by_status(self, *, user_id: str | None = None) -> dict[str, int]:
        if user_id:
            await self.get_or_create_user(user_id)
        stmt = select(AssistantProposal.status, func.count(AssistantProposal.id)).group_by(AssistantProposal.status)
        if user_id:
            stmt = stmt.where(AssistantProposal.user_id == user_id)
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return {str(status): int(count) for status, count in rows.all()}

    async def list_recent_activity(
        self,
        *,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[AssistantProposal]:
        if user_id:
            await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantProposal)
            .where(
                or_(
                    AssistantProposal.status.in_(["accepted", "execution_pending", "execution_failed", "executed", "expired", "superseded", "rejected"]),
                    AssistantProposal.execution_error.is_not(None),
                )
            )
            .order_by(AssistantProposal.updated_at.desc(), AssistantProposal.id.desc())
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(AssistantProposal.user_id == user_id)
        return await self.list(stmt)

    async def list_execution_failures(
        self,
        *,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[AssistantProposal]:
        if user_id:
            await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantProposal)
            .where(AssistantProposal.status == "execution_failed")
            .order_by(AssistantProposal.updated_at.desc(), AssistantProposal.id.desc())
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(AssistantProposal.user_id == user_id)
        return await self.list(stmt)

    async def update_proposal(
        self,
        proposal_id: int,
        *,
        user_id: str,
        payload: Mapping[str, Any],
    ) -> AssistantProposal | None:
        proposal = await self.get_proposal(proposal_id, user_id=user_id)
        if proposal is None:
            return None
        return await self.update(proposal, payload)
