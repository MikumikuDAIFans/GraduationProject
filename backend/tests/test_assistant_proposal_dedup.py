from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantProposalCreate
from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager


async def _make_manager(tmp_path: Path) -> tuple[AssistantProposalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposal_dedup.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantProposalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantProposalManager(repository, execute_on_confirm=False), engine


def test_create_proposal_reuses_active_dedup_key(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            payload = AssistantProposalCreate(
                proposal_type="event_creation",
                summary="明天下午 3 点去学校和同学见面",
                dedup_key="event:school-meet:tomorrow-1500",
                payload_json={"options": [{"option_id": "A", "title": "15:00-16:00"}]},
            )

            first = await manager.create_proposal(user_id="local-user", payload=payload)
            second = await manager.create_proposal(user_id="local-user", payload=payload)

            assert second.id == first.id
            active = await manager.repository.list_active_proposals(user_id="local-user")
            assert [proposal.id for proposal in active] == [first.id]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_create_proposal_allows_same_dedup_after_terminal_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            payload = AssistantProposalCreate(
                proposal_type="event_creation",
                summary="安排见面",
                dedup_key="event:meet",
                payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
            )

            first = await manager.create_proposal(user_id="local-user", payload=payload)
            await manager.reject_proposal(user_id="local-user", proposal_id=first.id)
            second = await manager.create_proposal(user_id="local-user", payload=payload)

            assert second.id != first.id
            assert second.status == "pending"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
