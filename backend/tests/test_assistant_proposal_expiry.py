from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantProposalCreate
from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager


async def _make_manager(tmp_path: Path) -> tuple[AssistantProposalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposal_expiry.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantProposalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantProposalManager(repository, execute_on_confirm=False), engine


def test_confirm_expired_proposal_marks_expired_and_rejects(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="已过期的安排",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )

            with pytest.raises(HTTPException) as exc_info:
                await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")

            assert exc_info.value.status_code == 409
            expired = await manager.get_proposal(user_id="local-user", proposal_id=proposal.id)
            assert expired.status == "expired"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_pending_proposal_gets_default_expiry(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            before = datetime.now(timezone.utc)
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="默认过期时间",
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )
            after = datetime.now(timezone.utc)

            assert proposal.expires_at is not None
            expires_at = proposal.expires_at.replace(tzinfo=timezone.utc) if proposal.expires_at.tzinfo is None else proposal.expires_at
            assert before + timedelta(hours=23, minutes=59) <= expires_at <= after + timedelta(hours=24, minutes=1)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_expire_due_proposals_only_expires_due_items(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            due = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="过期 proposal",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )
            future = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="未过期 proposal",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    payload_json={"options": [{"option_id": "A", "title": "16:00"}]},
                ),
            )

            expired = await manager.expire_due_proposals(user_id="local-user")

            assert [proposal.id for proposal in expired] == [due.id]
            assert (await manager.get_proposal(user_id="local-user", proposal_id=due.id)).status == "expired"
            assert (await manager.get_proposal(user_id="local-user", proposal_id=future.id)).status == "pending"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
