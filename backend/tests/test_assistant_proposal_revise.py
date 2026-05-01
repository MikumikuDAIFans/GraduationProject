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
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposal_revise.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantProposalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantProposalManager(repository, execute_on_confirm=False), engine


def test_revise_creates_child_and_supersedes_original(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="task_schedule_plan",
                    summary="安排复习",
                    dedup_key="task:review-plan",
                    payload_json={"options": [{"option_id": "A", "title": "今晚复习"}]},
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到明天上午",
            )
            old = await manager.get_proposal(user_id="local-user", proposal_id=original.id)

            assert old.status == "superseded"
            assert revised.status == "pending"
            assert revised.supersedes_proposal_id == original.id
            assert revised.payload_json["revision_request"] == "改到明天上午"
            assert revised.payload_json["superseded_proposal_id"] == original.id
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_expired_proposal_is_rejected(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="过期安排",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )

            with pytest.raises(HTTPException) as exc_info:
                await manager.revise_proposal(user_id="local-user", proposal_id=proposal.id, message="改一下")

            assert exc_info.value.status_code == 409
            assert (await manager.get_proposal(user_id="local-user", proposal_id=proposal.id)).status == "expired"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
