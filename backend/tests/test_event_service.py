from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.services.events import EventService


def _make_existing_event(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=99,
        user_id="local-user",
        title="Test Event",
        description=None,
        start_time=datetime.fromisoformat("2026-04-01T10:00:00"),
        end_time=datetime.fromisoformat("2026-04-01T11:00:00"),
        location_name=None,
        location_coords=None,
        event_type="general",
        source="local",
        is_fixed=False,
        buffer_before=0,
        buffer_after=0,
        travel_mode=None,
        travel_duration_minutes=None,
        departure_time=None,
        status="planned",
        linked_task_id=None,
        external_event_id=None,
        external_calendar_id=None,
        external_etag=None,
        sync_status="local_only",
        last_synced_at=None,
    )
    defaults.update(kwargs)
    obj = SimpleNamespace(**defaults)
    # Allow EventRead.model_validate and .model_dump(mode="json") in tests
    obj.model_dump = lambda mode=None: {k: v for k, v in vars(obj).items() if k != "model_dump"}
    return obj


def test_update_event_syncs_linked_task_state() -> None:
    service = EventService()
    existing = _make_existing_event(id=11, event_type="focus_block", status="planned", linked_task_id=9)

    async def fake_get_event(event_id: int, *, user_id: str):
        return existing

    async def fake_update_event(event_id: int, *, user_id: str, payload: dict):
        for key, value in payload.items():
            setattr(existing, key, value)
        return existing

    async def fake_sync_event(*, user_id: str, event_id: int):
        return existing

    synced_task_ids: list[int] = []

    async def fake_sync_task_schedule_state(*, user_id: str, task_id: int):
        synced_task_ids.append(task_id)
        return None

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        pass

    service.repository.get_event = fake_get_event  # type: ignore[method-assign]
    service.repository.update_event = fake_update_event  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]
    service.google_calendar_service.sync_event = fake_sync_event  # type: ignore[method-assign]
    service.task_service.sync_task_schedule_state = fake_sync_task_schedule_state  # type: ignore[method-assign]

    result = asyncio.run(
        service.update_event(
            user_id="local-user",
            event_id=11,
            payload=SimpleNamespace(model_dump=lambda exclude_none=True: {"status": "completed"}),
        )
    )

    assert result.status == "completed"
    assert synced_task_ids == [9]


def test_update_event_creates_task_replan_reminder_for_canceled_focus_block() -> None:
    service = EventService()
    existing = _make_existing_event(id=21, event_type="focus_block", status="planned", linked_task_id=10)

    async def fake_get_event(event_id: int, *, user_id: str):
        return existing

    async def fake_update_event(event_id: int, *, user_id: str, payload: dict):
        for key, value in payload.items():
            setattr(existing, key, value)
        return existing

    async def fake_sync_event(*, user_id: str, event_id: int):
        return existing

    async def fake_sync_task_schedule_state(*, user_id: str, task_id: int):
        return SimpleNamespace(
            id=task_id,
            content="Write thesis chapter",
            remaining_minutes=60,
            estimated_duration_minutes=180,
            completed_minutes=60,
            status="in_progress",
        )

    created_reminders: list[dict] = []

    async def fake_create_reminder(payload: dict):
        created_reminders.append(payload)
        return None

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        pass

    service.repository.get_event = fake_get_event  # type: ignore[method-assign]
    service.repository.update_event = fake_update_event  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]
    service.google_calendar_service.sync_event = fake_sync_event  # type: ignore[method-assign]
    service.task_service.sync_task_schedule_state = fake_sync_task_schedule_state  # type: ignore[method-assign]
    service.reminder_repository.create_reminder = fake_create_reminder  # type: ignore[method-assign]

    asyncio.run(
        service.update_event(
            user_id="local-user",
            event_id=21,
            payload=SimpleNamespace(model_dump=lambda exclude_none=True: {"status": "canceled"}),
        )
    )

    assert created_reminders
    assert created_reminders[0]["remind_type"] == "task_replan"


def test_update_event_creates_task_progress_reminder_for_completed_focus_block() -> None:
    service = EventService()
    existing = _make_existing_event(id=20, event_type="focus_block", status="planned", linked_task_id=10)

    async def fake_get_event(event_id: int, *, user_id: str):
        return existing

    async def fake_update_event(event_id: int, *, user_id: str, payload: dict):
        for key, value in payload.items():
            setattr(existing, key, value)
        return existing

    async def fake_sync_event(*, user_id: str, event_id: int):
        return existing

    async def fake_sync_task_schedule_state(*, user_id: str, task_id: int):
        return SimpleNamespace(
            id=task_id,
            content="Write thesis chapter",
            remaining_minutes=120,
            estimated_duration_minutes=180,
            completed_minutes=60,
            status="in_progress",
        )

    created_reminders: list[dict] = []

    async def fake_create_reminder(payload: dict):
        created_reminders.append(payload)
        return None

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        pass

    service.repository.get_event = fake_get_event  # type: ignore[method-assign]
    service.repository.update_event = fake_update_event  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]
    service.google_calendar_service.sync_event = fake_sync_event  # type: ignore[method-assign]
    service.task_service.sync_task_schedule_state = fake_sync_task_schedule_state  # type: ignore[method-assign]
    service.reminder_repository.create_reminder = fake_create_reminder  # type: ignore[method-assign]

    asyncio.run(
        service.update_event(
            user_id="local-user",
            event_id=20,
            payload=SimpleNamespace(model_dump=lambda exclude_none=True: {"status": "completed"}),
        )
    )

    assert created_reminders
    assert created_reminders[0]["remind_type"] == "task_progress"


def test_create_event_writes_change_log() -> None:
    """create_event should write a 'created' entry to schedule_change_logs."""
    service = EventService()
    existing = _make_existing_event(id=50)

    async def fake_create_event(payload):
        return existing

    async def fake_sync_event(*, user_id, event_id):
        return existing

    logged: list[dict] = []

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        logged.append({"user_id": user_id, "event_id": event_id, "change_type": change_type, **kwargs})

    service.repository.create_event = fake_create_event  # type: ignore[method-assign]
    service.google_calendar_service.sync_event = fake_sync_event  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]

    asyncio.run(
        service.create_event(
            user_id="local-user",
            payload=SimpleNamespace(model_dump=lambda: {"title": "Test", "start_time": None, "location_name": None}),
        )
    )

    assert len(logged) == 1
    assert logged[0]["change_type"] == "created"
    assert logged[0]["event_id"] == 50


def test_update_event_writes_change_log() -> None:
    """update_event should write an 'updated' entry with old and new snapshots."""
    service = EventService()
    existing = _make_existing_event(id=51, status="planned")

    async def fake_get_event(event_id, *, user_id):
        return existing

    async def fake_update_event(event_id, *, user_id, payload):
        for k, v in payload.items():
            setattr(existing, k, v)
        return existing

    async def fake_sync_event(*, user_id, event_id):
        return existing

    async def fake_sync_task(*, user_id, task_id):
        return None

    logged: list[dict] = []

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        logged.append({"change_type": change_type, "old": kwargs.get("old_value_json"), "new": kwargs.get("new_value_json")})

    service.repository.get_event = fake_get_event  # type: ignore[method-assign]
    service.repository.update_event = fake_update_event  # type: ignore[method-assign]
    service.google_calendar_service.sync_event = fake_sync_event  # type: ignore[method-assign]
    service.task_service.sync_task_schedule_state = fake_sync_task  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]

    asyncio.run(
        service.update_event(
            user_id="local-user",
            event_id=51,
            payload=SimpleNamespace(model_dump=lambda exclude_none=True: {"status": "completed"}),
        )
    )

    assert len(logged) == 1
    assert logged[0]["change_type"] == "updated"
    assert logged[0]["old"] is not None
    assert logged[0]["new"] is not None


def test_delete_event_writes_change_log() -> None:
    """delete_event should write a 'deleted' entry with the old snapshot."""
    service = EventService()
    existing = _make_existing_event(id=52)

    async def fake_get_event(event_id, *, user_id):
        return existing

    async def fake_delete_mirror(*, user_id, external_event_id, source):
        pass

    async def fake_delete_event(event_id, *, user_id):
        return True

    logged: list[dict] = []

    async def fake_write_change_log(*, user_id, event_id, change_type, **kwargs):
        logged.append({"change_type": change_type, "event_id": event_id, "old": kwargs.get("old_value_json")})

    service.repository.get_event = fake_get_event  # type: ignore[method-assign]
    service.google_calendar_service.delete_event_mirror = fake_delete_mirror  # type: ignore[method-assign]
    service.repository.delete_event = fake_delete_event  # type: ignore[method-assign]
    service.repository.write_change_log = fake_write_change_log  # type: ignore[method-assign]

    asyncio.run(service.delete_event(user_id="local-user", event_id=52))

    assert len(logged) == 1
    assert logged[0]["change_type"] == "deleted"
    assert logged[0]["event_id"] is None  # deleted records store None
    assert logged[0]["old"] is not None
