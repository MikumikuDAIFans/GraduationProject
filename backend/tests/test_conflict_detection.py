from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace

from app.services.events import EventService


class FakeEventRepository:
    def __init__(self, events):
        self._events = events

    async def list_events(self, user_id: str, **kwargs):
        return self._events


def test_no_conflict_when_no_overlap() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting A",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=0,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 12, 0),
            end_time=datetime(2026, 4, 1, 13, 0),
        )
    )

    assert conflicts == []


def test_conflict_when_overlap() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting A",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=0,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 10, 30),
            end_time=datetime(2026, 4, 1, 11, 30),
        )
    )

    assert len(conflicts) == 1
    assert conflicts[0].id == 1


def test_conflict_due_to_buffer() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting A",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=15,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 11, 10),
            end_time=datetime(2026, 4, 1, 12, 0),
        )
    )

    assert len(conflicts) == 1


def test_no_conflict_when_buffer_fits() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting A",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=5,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 11, 10),
            end_time=datetime(2026, 4, 1, 12, 0),
        )
    )

    assert conflicts == []


def test_conflict_due_to_new_event_buffer_before() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting A",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 10, 45),
                buffer_before=0,
                buffer_after=0,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 11, 0),
            end_time=datetime(2026, 4, 1, 12, 0),
            buffer_before=20,
        )
    )

    assert len(conflicts) == 1


def test_exclude_self_on_update() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=5,
                user_id="test-user",
                title="Self",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=0,
            ),
        ]
    )

    conflicts = asyncio.run(
        service.detect_conflicts(
            user_id="test-user",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            exclude_event_id=5,
        )
    )

    assert conflicts == []


def test_find_alternative_slots_returns_non_conflicting() -> None:
    service = EventService()
    service.repository = FakeEventRepository(
        [
            SimpleNamespace(
                id=1,
                user_id="test-user",
                title="Meeting",
                start_time=datetime(2026, 4, 1, 10, 0),
                end_time=datetime(2026, 4, 1, 11, 0),
                buffer_before=0,
                buffer_after=0,
            ),
            SimpleNamespace(
                id=2,
                user_id="test-user",
                title="Lunch",
                start_time=datetime(2026, 4, 1, 12, 0),
                end_time=datetime(2026, 4, 1, 13, 0),
                buffer_before=0,
                buffer_after=0,
            ),
        ]
    )

    async def fake_get_profile(user_id: str):
        return SimpleNamespace(wake_up_time="08:00", sleep_time="22:00")

    service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]

    alternatives = asyncio.run(
        service.find_alternative_slots(
            user_id="test-user",
            duration_minutes=60,
            preferred_date=date(2026, 4, 1),
        )
    )

    assert alternatives
    alt_start = datetime.fromisoformat(alternatives[0]["start_time"])
    assert alt_start.hour < 10 or alt_start.hour >= 11
