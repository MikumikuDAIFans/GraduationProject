from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.repositories.assistant_thread_states import AssistantThreadStateRepository


async def _make_session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposals.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_proposal_repository_tracks_active_dedup_and_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, engine = await _make_session_factory(tmp_path)
        try:
            proposals = AssistantProposalRepository(session_factory)

            proposal = await proposals.create_proposal(
                {
                    "user_id": "local-user",
                    "proposal_type": "event_creation",
                    "trigger_type": "user_message",
                    "status": "pending",
                    "dedup_key": "event_creation:local-user:tomorrow-school",
                    "summary": "明天下午 3 点去学校和同学见面",
                    "payload_json": {
                        "options": [
                            {
                                "option_id": "A",
                                "title": "15:00-16:00",
                                "actions": [{"type": "create_event"}],
                            }
                        ]
                    },
                    "recommended_option_id": "A",
                    "is_time_sensitive": True,
                }
            )

            assert proposal.id is not None
            assert proposal.payload_json["options"][0]["option_id"] == "A"

            active = await proposals.get_active_by_dedup_key(
                user_id="local-user",
                dedup_key="event_creation:local-user:tomorrow-school",
            )
            assert active is not None
            assert active.id == proposal.id

            updated = await proposals.update_proposal(
                proposal.id,
                user_id="local-user",
                payload={"status": "accepted", "selected_option_id": "A"},
            )
            assert updated is not None
            assert updated.status == "accepted"
            assert updated.selected_option_id == "A"

            accepted = await proposals.list_proposals(user_id="local-user", statuses=["accepted"])
            assert [item.id for item in accepted] == [proposal.id]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_thread_state_repository_is_context_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, engine = await _make_session_factory(tmp_path)
        try:
            thread_states = AssistantThreadStateRepository(session_factory)

            state = await thread_states.create_thread_state(
                {
                    "user_id": "local-user",
                    "thread_type": "event_planning",
                    "status": "waiting_user",
                    "state_json": {"last_question": "你想把它当成任务还是日程？"},
                    "is_waiting_user": True,
                    "last_specialist": "task_or_event_clarifier",
                }
            )

            assert state.id is not None
            assert state.status == "waiting_user"
            assert state.state_json["last_question"].startswith("你想")

            updated = await thread_states.update_thread_state(
                state.id,
                user_id="local-user",
                payload={"active_proposal_id": 42, "status": "active"},
            )
            assert updated is not None
            assert updated.active_proposal_id == 42

            active = await thread_states.list_thread_states(user_id="local-user", statuses=["active"])
            assert [item.id for item in active] == [state.id]
        finally:
            await engine.dispose()

    asyncio.run(scenario())
