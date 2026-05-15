from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.jobs.assistant_signals import _scan_daily_rhythm_signals
from app.models import AssistantProposal, Event, Task, UserProfile
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_signal_manager import AssistantSignalManager


async def _make_context(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_daily_review.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = AssistantSignalRepository(session_factory)
    manager = AssistantSignalManager(repository)
    return session_factory, manager, engine


def test_daily_morning_review_uses_wake_time_plus_30_minutes(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        try:
            async with session_factory() as session:
                session.add(
                    UserProfile(
                        username="local-user",
                        display_name="local-user",
                        timezone="Asia/Shanghai",
                        wake_up_time="07:30",
                        sleep_time="23:30",
                    )
                )
                await session.commit()

            now = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)  # 08:00 Asia/Shanghai
            result = await _scan_daily_rhythm_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="daily_morning_review")

            assert result["generated_count"] == 1
            assert len(signals) == 1
            assert signals[0].dedup_key == "daily_morning_review:local-user:2026-05-01"
            assert signals[0].context_json["trigger_at"].startswith("2026-05-01T08:00")
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_daily_night_review_uses_sleep_time_minus_30_minutes(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        try:
            async with session_factory() as session:
                session.add(
                    UserProfile(
                        username="local-user",
                        display_name="local-user",
                        timezone="Asia/Shanghai",
                        wake_up_time="08:00",
                        sleep_time="23:00",
                    )
                )
                await session.commit()

            now = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)  # 22:30 Asia/Shanghai
            result = await _scan_daily_rhythm_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="daily_night_review")

            assert result["generated_count"] == 1
            assert len(signals) == 1
            assert signals[0].dedup_key == "daily_night_review:local-user:2026-05-01"
            assert signals[0].context_json["trigger_at"].startswith("2026-05-01T22:30")
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_daily_rhythm_dedups_same_day_signal(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        try:
            await manager.repository.get_or_create_user("local-user")
            now = datetime(2026, 5, 1, 0, 30, tzinfo=timezone.utc)  # fallback 08:30 Asia/Shanghai

            first = await _scan_daily_rhythm_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            second = await _scan_daily_rhythm_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="daily_morning_review")

            assert first["generated_count"] == 1
            assert second["generated_count"] == 0
            assert len(signals) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_daily_morning_review_includes_today_snapshot_message(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        try:
            async with session_factory() as session:
                session.add(
                    UserProfile(
                        username="local-user",
                        display_name="local-user",
                        timezone="Asia/Shanghai",
                        wake_up_time="07:30",
                        sleep_time="23:30",
                    )
                )
                session.add(
                    Event(
                        user_id="local-user",
                        title="图书馆自习",
                        start_time=datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc),
                        end_time=datetime(2026, 5, 1, 16, 0, tzinfo=timezone.utc),
                        status="planned",
                    )
                )
                session.add(
                    Task(
                        user_id="local-user",
                        content="毕设论文",
                        priority=5,
                        status="pending",
                        deadline=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
                    )
                )
                session.add(
                    AssistantProposal(
                        user_id="local-user",
                        proposal_type="event_creation",
                        status="pending",
                        summary="建议创建日程“下午见面”",
                        payload_json={"options": [{"option_id": "A", "title": "按建议创建"}]},
                    )
                )
                await session.commit()

            now = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)  # 08:00 Asia/Shanghai
            result = await _scan_daily_rhythm_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="daily_morning_review")

            assert result["generated_count"] == 1
            assert len(signals) == 1
            message = signals[0].context_json["message"]
            assert "晨间汇报" in message
            assert "图书馆自习" in message
            assert "毕设论文" in message
            assert "建议创建日程" in message
            assert "可回复" in message
        finally:
            await engine.dispose()

    asyncio.run(scenario())
