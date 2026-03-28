from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.services.tasks import TaskService


def test_build_task_read_includes_scheduling_progress() -> None:
    service = TaskService()
    task = SimpleNamespace(
        id=3,
        user_id="local-user",
        content="Write thesis chapter",
        description=None,
        estimated_duration_minutes=180,
        priority=3,
        deadline=None,
        status="pending",
        can_split=True,
        preferred_period="afternoon",
        linked_event_id=None,
        created_at=None,
        updated_at=None,
    )
    linked_events = [
        SimpleNamespace(
            start_time=datetime.fromisoformat("2026-03-28T12:00:00"),
            end_time=datetime.fromisoformat("2026-03-28T13:00:00"),
        ),
        SimpleNamespace(
            start_time=datetime.fromisoformat("2026-03-28T13:05:00"),
            end_time=datetime.fromisoformat("2026-03-28T14:05:00"),
        ),
    ]

    read_model = service._build_task_read(task, linked_events)

    assert read_model.scheduled_minutes == 120
    assert read_model.scheduled_blocks_count == 2
    assert read_model.remaining_minutes == 60
    assert read_model.completion_ratio == 0.67


def test_sync_task_schedule_state_marks_task_scheduled() -> None:
    service = TaskService()

    async def fake_get_task(task_id: int, *, user_id: str):
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status="pending",
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=None,
            created_at=None,
            updated_at=None,
        )

    async def fake_list_events_for_task_ids(*, user_id: str, task_ids: list[int]):
        return [
            SimpleNamespace(
                id=11,
                linked_task_id=task_ids[0],
                start_time=datetime.fromisoformat("2026-03-28T12:00:00"),
                end_time=datetime.fromisoformat("2026-03-28T13:00:00"),
            ),
            SimpleNamespace(
                id=12,
                linked_task_id=task_ids[0],
                start_time=datetime.fromisoformat("2026-03-28T13:05:00"),
                end_time=datetime.fromisoformat("2026-03-28T14:05:00"),
            ),
        ]

    updated_payloads: list[dict] = []

    async def fake_update_task(task_id: int, *, user_id: str, payload: dict):
        updated_payloads.append(payload)
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status=payload["status"],
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=payload["linked_event_id"],
            created_at=None,
            updated_at=None,
        )

    service.repository.get_task = fake_get_task  # type: ignore[method-assign]
    service.event_repository.list_events_for_task_ids = fake_list_events_for_task_ids  # type: ignore[method-assign]
    service.repository.update_task = fake_update_task  # type: ignore[method-assign]

    result = asyncio.run(service.sync_task_schedule_state(user_id="local-user", task_id=3))

    assert updated_payloads[0]["status"] == "scheduled"
    assert updated_payloads[0]["linked_event_id"] == 11
    assert result is not None
    assert result.scheduled_minutes == 120


def test_sync_task_schedule_state_marks_task_in_progress_when_block_completed() -> None:
    service = TaskService()

    async def fake_get_task(task_id: int, *, user_id: str):
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status="scheduled",
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=11,
            created_at=None,
            updated_at=None,
        )

    async def fake_list_events_for_task_ids(*, user_id: str, task_ids: list[int]):
        return [
            SimpleNamespace(
                id=11,
                linked_task_id=task_ids[0],
                status="completed",
                start_time=datetime.fromisoformat("2026-03-28T12:00:00"),
                end_time=datetime.fromisoformat("2026-03-28T13:00:00"),
            ),
            SimpleNamespace(
                id=12,
                linked_task_id=task_ids[0],
                status="planned",
                start_time=datetime.fromisoformat("2026-03-28T13:05:00"),
                end_time=datetime.fromisoformat("2026-03-28T14:05:00"),
            ),
        ]

    async def fake_update_task(task_id: int, *, user_id: str, payload: dict):
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status=payload["status"],
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=payload["linked_event_id"],
            created_at=None,
            updated_at=None,
        )

    service.repository.get_task = fake_get_task  # type: ignore[method-assign]
    service.event_repository.list_events_for_task_ids = fake_list_events_for_task_ids  # type: ignore[method-assign]
    service.repository.update_task = fake_update_task  # type: ignore[method-assign]

    result = asyncio.run(service.sync_task_schedule_state(user_id="local-user", task_id=3))

    assert result is not None
    assert result.status == "in_progress"
    assert result.completed_minutes == 60
    assert result.execution_ratio == 0.33


def test_sync_task_schedule_state_excludes_canceled_blocks_from_schedule() -> None:
    service = TaskService()

    async def fake_get_task(task_id: int, *, user_id: str):
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status="scheduled",
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=11,
            created_at=None,
            updated_at=None,
        )

    async def fake_list_events_for_task_ids(*, user_id: str, task_ids: list[int]):
        return [
            SimpleNamespace(
                id=11,
                linked_task_id=task_ids[0],
                status="completed",
                start_time=datetime.fromisoformat("2026-03-28T12:00:00"),
                end_time=datetime.fromisoformat("2026-03-28T13:00:00"),
            ),
            SimpleNamespace(
                id=12,
                linked_task_id=task_ids[0],
                status="canceled",
                start_time=datetime.fromisoformat("2026-03-28T13:05:00"),
                end_time=datetime.fromisoformat("2026-03-28T14:05:00"),
            ),
        ]

    async def fake_update_task(task_id: int, *, user_id: str, payload: dict):
        return SimpleNamespace(
            id=task_id,
            user_id=user_id,
            content="Write thesis chapter",
            description=None,
            estimated_duration_minutes=180,
            priority=3,
            deadline=None,
            status=payload["status"],
            can_split=True,
            preferred_period="afternoon",
            linked_event_id=payload["linked_event_id"],
            created_at=None,
            updated_at=None,
        )

    service.repository.get_task = fake_get_task  # type: ignore[method-assign]
    service.event_repository.list_events_for_task_ids = fake_list_events_for_task_ids  # type: ignore[method-assign]
    service.repository.update_task = fake_update_task  # type: ignore[method-assign]

    result = asyncio.run(service.sync_task_schedule_state(user_id="local-user", task_id=3))

    assert result is not None
    assert result.scheduled_minutes == 60
    assert result.scheduled_blocks_count == 2
    assert result.remaining_minutes == 120
