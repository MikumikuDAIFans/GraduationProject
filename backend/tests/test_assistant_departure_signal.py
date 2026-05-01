from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import WeatherNowRead, WeatherSnapshotRead
from app.core.config import get_settings
from app.db.base import Base
from app.jobs.assistant_signals import (
    _scan_conflict_repair_signals,
    _scan_deadline_risk_signals,
    _scan_departure_readiness_signals,
)
from app.models import Event, Task
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_signal_manager import AssistantSignalManager


class FakeWeatherContext:
    async def weather_snapshot(self, *, location: str, allow_refresh: bool = False) -> WeatherSnapshotRead:
        assert allow_refresh is False
        return WeatherSnapshotRead(
            location=location,
            source="cache",
            is_stale=False,
            weather=WeatherNowRead(location=location, temp=24, text="Cloudy"),
        )


async def _make_context(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_signal_jobs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = AssistantSignalRepository(session_factory)
    await repository.get_or_create_user("local-user")
    manager = AssistantSignalManager(repository)
    return session_factory, manager, engine


def test_deadline_risk_signal_job_uses_dedup(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        now = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        try:
            async with session_factory() as session:
                session.add(
                    Task(
                        user_id="local-user",
                        content="交材料",
                        deadline=now + timedelta(hours=3),
                        status="pending",
                    )
                )
                await session.commit()

            first = await _scan_deadline_risk_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            second = await _scan_deadline_risk_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="deadline_risk")

            assert first["generated_count"] == 1
            assert second["generated_count"] == 0
            assert len(signals) == 1
            assert signals[0].target_type == "task"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_deadline_risk_signal_job_runs_when_proactive_mode_enabled(tmp_path: Path, monkeypatch) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        now = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        try:
            async with session_factory() as session:
                session.add(
                    Task(
                        user_id="local-user",
                        content="交材料",
                        deadline=now + timedelta(hours=2),
                        status="pending",
                    )
                )
                await session.commit()

            result = await _scan_deadline_risk_signals(now=now, session_factory=session_factory, manager=manager)
            signals = await manager.list_signals(user_id="local-user", signal_type="deadline_risk")

            assert result["status"] == "ok"
            assert result["generated_count"] == 1
            assert len(signals) == 1
        finally:
            await engine.dispose()

    monkeypatch.setenv("ASSISTANT_PROACTIVE_MODE", "signals")
    get_settings.cache_clear()
    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()


def test_conflict_signal_job_detects_buffer_overlap(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        now = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        try:
            async with session_factory() as session:
                session.add_all(
                    [
                        Event(
                            user_id="local-user",
                            title="政治课",
                            start_time=now + timedelta(hours=1),
                            end_time=now + timedelta(hours=2),
                            buffer_after=15,
                            status="planned",
                        ),
                        Event(
                            user_id="local-user",
                            title="和同学见面",
                            start_time=now + timedelta(hours=2, minutes=5),
                            end_time=now + timedelta(hours=3),
                            status="planned",
                        ),
                    ]
                )
                await session.commit()

            result = await _scan_conflict_repair_signals(now=now, session_factory=session_factory, manager=manager, force=True)
            signals = await manager.list_signals(user_id="local-user", signal_type="conflict_warning")

            assert result["generated_count"] == 1
            assert len(signals) == 1
            assert signals[0].context_json["event_a_title"] == "政治课"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_departure_signal_job_uses_departure_time_not_event_start(tmp_path: Path) -> None:
    async def scenario() -> None:
        session_factory, manager, engine = await _make_context(tmp_path)
        now = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        try:
            async with session_factory() as session:
                session.add(
                    Event(
                        user_id="local-user",
                        title="去学校上课",
                        start_time=now + timedelta(hours=1),
                        end_time=now + timedelta(hours=2),
                        departure_time=now + timedelta(minutes=20),
                        travel_duration_minutes=30,
                        location_name="学校",
                        location_coords="116.40,39.90",
                        status="planned",
                    )
                )
                await session.commit()

            result = await _scan_departure_readiness_signals(
                now=now,
                session_factory=session_factory,
                manager=manager,
                context_service=FakeWeatherContext(),
                force=True,
            )
            signals = await manager.list_signals(user_id="local-user", signal_type="departure_readiness")

            assert result["generated_count"] == 1
            assert len(signals) == 1
            assert signals[0].context_json["departure_time"].startswith("2026-05-01T09:20")
            assert signals[0].context_json["event_start"].startswith("2026-05-01T10:00")
            assert signals[0].context_json["weather_snapshot"]["weather"]["text"] == "Cloudy"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
