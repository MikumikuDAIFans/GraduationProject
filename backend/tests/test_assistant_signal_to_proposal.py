from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantSignalCreate
from app.db.base import Base
from app.models import AssistantProposal
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


def test_daily_night_review_proposal_uses_structured_review_template(tmp_path: Path) -> None:
    async def scenario() -> None:
        signal_manager, _, engine = await _make_managers(tmp_path)
        try:
            signal = await signal_manager.create_signal(
                user_id="local-user",
                payload=AssistantSignalCreate(
                    signal_type="daily_night_review",
                    dedup_key="daily:night",
                    context_json={"local_date": "2026-05-01"},
                ),
            )

            proposal = await signal_manager.create_proposal_from_signal(user_id="local-user", signal_id=signal.id)

            assert proposal.proposal_type == "daily_review_followup"
            assert "今日日程完成核对" in proposal.summary
            assert "未完成任务" in proposal.summary
            assert "pending proposal 跟进" in proposal.summary
            assert "可回复" in proposal.summary
            assert "政治课完成了，复习没做" in proposal.summary
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_pending_proposal_followup_signal_creates_reminder_proposal(tmp_path: Path) -> None:
    async def scenario() -> None:
        signal_manager, proposal_manager, engine = await _make_managers(tmp_path)
        now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        try:
            async with signal_manager.repository.session_factory() as session:
                session.add(
                    AssistantProposal(
                        user_id="local-user",
                        proposal_type="event_create",
                        trigger_type="user_message",
                        status="pending",
                        summary="建议把明天下午三点去学校和同学见面。",
                        payload_json={
                            "protocol_label": "P1",
                            "options": [
                                {
                                    "option_id": "A",
                                    "title": "按这个建议创建",
                                    "actions": [],
                                }
                            ],
                        },
                        recommended_option_id="A",
                        created_at=now - timedelta(hours=3),
                        updated_at=now - timedelta(hours=3),
                    )
                )
                await session.commit()

            from app.jobs.assistant_signals import _scan_pending_proposal_followup_signals

            result = await _scan_pending_proposal_followup_signals(
                now=now,
                session_factory=signal_manager.repository.session_factory,
                manager=signal_manager,
                force=True,
            )
            signals = await signal_manager.list_signals(user_id="local-user", signal_type="proposal_followup")
            proposal_followup = await signal_manager.create_proposal_from_signal(user_id="local-user", signal_id=signals[0].id)
            second = await _scan_pending_proposal_followup_signals(
                now=now,
                session_factory=signal_manager.repository.session_factory,
                manager=signal_manager,
                force=True,
            )

            assert result["generated_count"] == 1
            assert second["generated_count"] == 0
            assert len(signals) == 1
            assert proposal_followup.proposal_type == "proposal_followup"
            assert "待确认方案跟进" in proposal_followup.summary
            assert "P1" in proposal_followup.summary
            assert "建议把明天下午三点去学校和同学见面" in proposal_followup.summary
            assert "按方案A安排" in proposal_followup.summary
            assert "改成4点开始" in proposal_followup.summary
            assert "先不要安排" in proposal_followup.summary
            assert proposal_followup.payload_json["options"][0]["actions"][0]["type"] == "acknowledge_signal"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
