from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantProposalCreate
from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager


class FakeExecutor:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail_first = fail_first

    async def execute(self, *, user_id: str, proposal, option_id: str):
        self.calls.append({"user_id": user_id, "proposal_id": proposal.id, "option_id": option_id})
        if self.fail_first and len(self.calls) == 1:
            raise HTTPException(status_code=400, detail="unsupported action type: noop")
        return {
            "status": "executed",
            "option_id": option_id,
            "actions": [{"type": "create_event", "result": {"kind": "event", "related_event_id": 10}}],
            "related_event_id": 10,
        }


async def _make_manager(
    tmp_path: Path,
    *,
    executor=None,
    execute_on_confirm: bool = True,
) -> tuple[AssistantProposalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposal_manager.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantProposalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantProposalManager(repository, executor=executor, execute_on_confirm=execute_on_confirm), engine


def test_confirm_proposal_can_accept_option_without_execution_when_disabled(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path, execute_on_confirm=False)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="明天下午 3 点去学校和同学见面",
                    payload_json={
                        "options": [
                            {"option_id": "A", "title": "15:00-16:00", "actions": [{"type": "create_event"}]},
                            {"option_id": "B", "title": "15:00-17:00", "actions": [{"type": "create_event"}]},
                        ]
                    },
                    recommended_option_id="A",
                ),
            )

            confirmed = await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")

            assert confirmed.status == "accepted"
            assert confirmed.selected_option_id == "A"
            assert confirmed.executed_at is None
            assert confirmed.payload_json["execution"]["status"] == "pending"
            assert confirmed.payload_json["execution"]["selected_option_id"] == "A"

            repeated = await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")
            assert repeated.id == proposal.id

            with pytest.raises(HTTPException) as exc_info:
                await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="B")
            assert exc_info.value.status_code == 409
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_confirm_proposal_executes_selected_option_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        executor = FakeExecutor()
        manager, engine = await _make_manager(tmp_path, executor=executor)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="明天下午 3 点去学校和同学见面",
                    payload_json={
                        "options": [
                            {"option_id": "A", "title": "15:00-16:00", "actions": [{"type": "create_event"}]},
                            {"option_id": "B", "title": "15:00-17:00", "actions": [{"type": "create_event"}]},
                        ]
                    },
                    recommended_option_id="A",
                ),
            )

            confirmed = await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")

            assert confirmed.status == "executed"
            assert confirmed.selected_option_id == "A"
            assert confirmed.executed_at is not None
            assert confirmed.related_event_id == 10
            assert confirmed.payload_json["execution"]["status"] == "executed"
            assert confirmed.payload_json["execution"]["selected_option_id"] == "A"
            assert len(confirmed.payload_json["execution"]["attempts"]) == 1
            assert len(executor.calls) == 1

            repeated = await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")
            assert repeated.id == proposal.id
            assert repeated.status == "executed"
            assert len(executor.calls) == 1

            with pytest.raises(HTTPException) as exc_info:
                await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="B")
            assert exc_info.value.status_code == 409
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_supersedes_original_and_returns_new_proposal(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="task_schedule_plan",
                    summary="安排政治课复习",
                    payload_json={"options": [{"option_id": "A", "title": "今晚复习"}]},
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到明天上午",
            )
            old = await manager.get_proposal(user_id="local-user", proposal_id=original.id)

            assert revised.id != original.id
            assert revised.supersedes_proposal_id == original.id
            assert revised.payload_json["revision_request"] == "改到明天上午"
            assert old.status == "superseded"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_retry_only_allows_execution_failed(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path, execute_on_confirm=False)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="安排见面",
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )
            with pytest.raises(HTTPException) as exc_info:
                await manager.retry_proposal(user_id="local-user", proposal_id=proposal.id)
            assert exc_info.value.status_code == 409

            confirmed = await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")
            await manager.repository.update_proposal(
                confirmed.id,
                user_id="local-user",
                payload={"status": "execution_failed", "execution_error": "network"},
            )

            retrying = await manager.retry_proposal(user_id="local-user", proposal_id=proposal.id)
            assert retrying.status == "execution_pending"
            assert retrying.execution_error is None
            assert retrying.payload_json["execution"]["retry_count"] == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_execution_failure_is_recorded_and_retry_executes_again(tmp_path: Path) -> None:
    async def scenario() -> None:
        executor = FakeExecutor(fail_first=True)
        manager, engine = await _make_manager(tmp_path, executor=executor)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="安排见面",
                    payload_json={"options": [{"option_id": "A", "title": "15:00", "actions": [{"type": "noop"}]}]},
                ),
            )

            with pytest.raises(HTTPException) as exc_info:
                await manager.confirm_proposal(user_id="local-user", proposal_id=proposal.id, option_id="A")
            assert exc_info.value.status_code == 400

            failed = await manager.get_proposal(user_id="local-user", proposal_id=proposal.id)
            assert failed.status == "execution_failed"
            assert failed.execution_error == "unsupported action type: noop"
            assert failed.payload_json["execution"]["status"] == "failed"

            retried = await manager.retry_proposal(user_id="local-user", proposal_id=proposal.id)
            assert retried.status == "executed"
            assert retried.payload_json["execution"]["retry_count"] == 1
            assert len(executor.calls) == 2
        finally:
            await engine.dispose()

    asyncio.run(scenario())
