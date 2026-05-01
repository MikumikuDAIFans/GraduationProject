from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantSignalCreate
from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager
from app.services.assistant_signal_manager import AssistantSignalManager


async def _make_managers(tmp_path: Path) -> tuple[AssistantSignalManager, AssistantProposalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_signal_to_proposal.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    proposal_manager = AssistantProposalManager(AssistantProposalRepository(session_factory))
    signal_manager = AssistantSignalManager(
        AssistantSignalRepository(session_factory),
        proposal_manager=proposal_manager,
    )
    return signal_manager, proposal_manager, engine


def test_signal_can_create_pending_acknowledgement_proposal(tmp_path: Path) -> None:
    async def scenario() -> None:
        signal_manager, proposal_manager, engine = await _make_managers(tmp_path)
        try:
            signal = await signal_manager.create_signal(
                user_id="local-user",
                payload=AssistantSignalCreate(
                    signal_type="deadline_risk",
                    severity="negotiate",
                    dedup_key="deadline_risk:task:1:2026-05-01",
                    target_type="task",
                    target_id=1,
                    context_json={"content": "交材料"},
                ),
            )

            proposal = await signal_manager.create_proposal_from_signal(user_id="local-user", signal_id=signal.id)
            updated_signal = await signal_manager.get_signal(user_id="local-user", signal_id=signal.id)

            assert proposal.status == "pending"
            assert proposal.source_signal_id == signal.id
            assert proposal.proposal_type == "deadline_recovery"
            assert proposal.payload_json["options"][0]["actions"][0]["type"] == "acknowledge_signal"
            assert updated_signal.status == "proposal_created"

            executed = await proposal_manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")
            assert executed.status == "executed"
            assert executed.payload_json["execution"]["result"]["actions"][0]["type"] == "acknowledge_signal"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_signal_to_proposal_is_deduped(tmp_path: Path) -> None:
    async def scenario() -> None:
        signal_manager, _, engine = await _make_managers(tmp_path)
        try:
            signal = await signal_manager.create_signal(
                user_id="local-user",
                payload=AssistantSignalCreate(signal_type="daily_morning_review", dedup_key="daily:morning"),
            )

            first = await signal_manager.create_proposal_from_signal(user_id="local-user", signal_id=signal.id)
            second = await signal_manager.create_proposal_from_signal(user_id="local-user", signal_id=signal.id)

            assert second.id == first.id
        finally:
            await engine.dispose()

    asyncio.run(scenario())
