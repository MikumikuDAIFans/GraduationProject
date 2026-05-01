from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantSignalCreate
from app.db.base import Base
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_signal_manager import AssistantSignalManager


async def _make_manager(tmp_path: Path) -> tuple[AssistantSignalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_signals_manager.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantSignalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantSignalManager(repository), engine


def test_signal_dedup_reuses_active_signal(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            payload = AssistantSignalCreate(
                signal_type="deadline_risk",
                severity="negotiate",
                dedup_key="deadline_risk:task:23:2026-05-01",
                target_type="task",
                target_id=23,
                context_json={"remaining_minutes": 90},
            )

            first = await manager.create_signal(user_id="local-user", payload=payload)
            second = await manager.create_signal(user_id="local-user", payload=payload)

            assert second.id == first.id
            assert first.cooldown_until is not None
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_signal_cooldown_blocks_recreation_after_dismiss(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            payload = AssistantSignalCreate(
                signal_type="conflict_warning",
                severity="negotiate",
                dedup_key="conflict:event:1-2",
                cooldown_until=datetime.now(timezone.utc) + timedelta(hours=4),
            )

            first = await manager.create_signal(user_id="local-user", payload=payload)
            dismissed = await manager.dismiss_signal(user_id="local-user", signal_id=first.id)
            recreated = await manager.create_signal(user_id="local-user", payload=payload)

            assert dismissed.status == "dismissed"
            assert recreated.id == first.id
            assert recreated.status == "dismissed"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_signal_can_be_recreated_after_cooldown(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            payload = AssistantSignalCreate(
                signal_type="departure_readiness",
                dedup_key="departure:event:9",
                cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
            )

            first = await manager.create_signal(user_id="local-user", payload=payload)
            await manager.dismiss_signal(user_id="local-user", signal_id=first.id)
            second = await manager.create_signal(user_id="local-user", payload=payload)

            assert second.id != first.id
            assert second.status == "new"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_terminal_signal_cannot_be_evaluated(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            signal = await manager.create_signal(
                user_id="local-user",
                payload=AssistantSignalCreate(signal_type="daily_morning_review", dedup_key="daily:morning"),
            )
            await manager.dismiss_signal(user_id="local-user", signal_id=signal.id)

            with pytest.raises(HTTPException) as exc_info:
                await manager.mark_evaluated(user_id="local-user", signal_id=signal.id)

            assert exc_info.value.status_code == 409
        finally:
            await engine.dispose()

    asyncio.run(scenario())
