from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.repositories.assistant_signals import AssistantSignalRepository


async def _make_session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_signals.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_signal_repository_tracks_active_dedup_and_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, engine = await _make_session_factory(tmp_path)
        try:
            signals = AssistantSignalRepository(session_factory)

            signal = await signals.create_signal(
                {
                    "user_id": "local-user",
                    "signal_type": "deadline_risk",
                    "severity": "negotiate",
                    "status": "new",
                    "dedup_key": "deadline_risk:task:23:2026-04-30",
                    "target_type": "task",
                    "target_id": 23,
                    "context_json": {"remaining_minutes": 90},
                    "source_job": "test",
                }
            )

            assert signal.id is not None
            assert signal.context_json == {"remaining_minutes": 90}

            active = await signals.get_active_by_dedup_key(
                user_id="local-user",
                dedup_key="deadline_risk:task:23:2026-04-30",
            )
            assert active is not None
            assert active.id == signal.id

            updated = await signals.update_signal(
                signal.id,
                user_id="local-user",
                payload={"status": "proposal_created"},
            )
            assert updated is not None
            assert updated.status == "proposal_created"

            listed = await signals.list_signals(user_id="local-user", statuses=["proposal_created"])
            assert [item.id for item in listed] == [signal.id]
        finally:
            await engine.dispose()

    asyncio.run(scenario())
