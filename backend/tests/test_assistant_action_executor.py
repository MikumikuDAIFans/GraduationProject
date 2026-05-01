from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.assistant_agents.action_executor import AssistantActionExecutor


def _proposal(actions: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        payload_json={"options": [{"option_id": "A", "title": "方案 A", "actions": actions}]},
    )


def _event(event_id: int, *, linked_task_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        user_id="local-user",
        title="Focus",
        description=None,
        start_time=datetime.fromisoformat("2026-05-02T15:00:00"),
        end_time=datetime.fromisoformat("2026-05-02T16:00:00"),
        location_name=None,
        status="planned",
        linked_task_id=linked_task_id,
    )


def _task(task_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        user_id="local-user",
        content="复习政治课",
        description=None,
        estimated_duration_minutes=120,
        priority=3,
        deadline=None,
        status="pending",
        can_split=True,
        preferred_period=None,
        linked_event_id=None,
    )


def _updated_event(event_id: int, payload: dict, *, linked_task_id: int | None = None) -> SimpleNamespace:
    event = _event(event_id, linked_task_id=linked_task_id)
    for key, value in payload.items():
        setattr(event, key, value)
    return event


def _updated_task(task_id: int, payload: dict) -> SimpleNamespace:
    task = _task(task_id)
    for key, value in payload.items():
        setattr(task, key, value)
    return task


def test_action_executor_creates_event() -> None:
    created_payloads: list[dict] = []

    class FakeEventService:
        async def create_event(self, *, user_id, payload):
            created_payloads.append(payload.model_dump())
            return _event(10)

    executor = AssistantActionExecutor(event_service=FakeEventService(), task_service=SimpleNamespace())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal(
                [
                    {
                        "type": "create_event",
                        "payload": {
                            "title": "和同学见面",
                            "start_time": "2026-05-02T15:00:00",
                            "end_time": "2026-05-02T16:00:00",
                            "location_name": "学校",
                        },
                    }
                ]
            ),
            option_id="A",
        )
    )

    assert created_payloads[0]["title"] == "和同学见面"
    assert result["related_event_id"] == 10
    assert result["actions"][0]["type"] == "create_event"


def test_action_executor_acknowledges_signal_without_task_or_event_write() -> None:
    executor = AssistantActionExecutor(event_service=SimpleNamespace(), task_service=SimpleNamespace())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal(
                [
                    {
                        "type": "acknowledge_signal",
                        "payload": {
                            "signal_id": 12,
                            "signal_type": "daily_morning_review",
                            "message": "晨间计划确认",
                        },
                    }
                ]
            ),
            option_id="A",
        )
    )

    assert result["related_task_id"] is None
    assert result["related_event_id"] is None
    assert result["actions"][0]["type"] == "acknowledge_signal"
    assert result["actions"][0]["result"]["signal_id"] == 12


def test_action_executor_creates_task_with_linked_events() -> None:
    created_tasks: list[dict] = []
    created_events: list[dict] = []

    class FakeTaskService:
        async def create_task(self, *, user_id, payload):
            created_tasks.append(payload.model_dump())
            return _task(7)

    class FakeEventService:
        async def create_event(self, *, user_id, payload):
            created_events.append(payload.model_dump())
            return _event(30 + len(created_events), linked_task_id=payload.linked_task_id)

    executor = AssistantActionExecutor(event_service=FakeEventService(), task_service=FakeTaskService())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal(
                [
                    {
                        "type": "create_task_with_events",
                        "payload": {
                            "task": {
                                "content": "复习政治课",
                                "estimated_duration_minutes": 120,
                                "can_split": True,
                            },
                            "events": [
                                {
                                    "title": "复习政治课 1",
                                    "start_time": "2026-05-02T15:00:00",
                                    "end_time": "2026-05-02T16:00:00",
                                },
                                {
                                    "title": "复习政治课 2",
                                    "start_time": "2026-05-03T15:00:00",
                                    "end_time": "2026-05-03T16:00:00",
                                },
                            ],
                        },
                    }
                ]
            ),
            option_id="A",
        )
    )

    assert created_tasks[0]["content"] == "复习政治课"
    assert [item["linked_task_id"] for item in created_events] == [7, 7]
    assert [item["event_type"] for item in created_events] == ["focus_block", "focus_block"]
    assert result["related_task_id"] == 7
    assert result["related_event_id"] == 31


def test_action_executor_reschedules_event() -> None:
    updates: list[dict] = []

    class FakeEventService:
        async def update_event(self, *, user_id, event_id, payload):
            updates.append({"event_id": event_id, "payload": payload.model_dump(exclude_none=True)})
            return _updated_event(event_id, updates[-1]["payload"])

    executor = AssistantActionExecutor(event_service=FakeEventService(), task_service=SimpleNamespace())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal(
                [
                    {
                        "type": "reschedule_event",
                        "payload": {
                            "event_id": 42,
                            "update": {
                                "start_time": "2026-05-02T17:00:00",
                                "end_time": "2026-05-02T18:00:00",
                            },
                        },
                    }
                ]
            ),
            option_id="A",
        )
    )

    assert updates == [
        {
            "event_id": 42,
            "payload": {
                "start_time": datetime.fromisoformat("2026-05-02T17:00:00"),
                "end_time": datetime.fromisoformat("2026-05-02T18:00:00"),
            },
        }
    ]
    assert result["related_event_id"] == 42
    assert result["actions"][0]["type"] == "reschedule_event"


def test_action_executor_cancels_event_by_status_update() -> None:
    updates: list[dict] = []

    class FakeEventService:
        async def update_event(self, *, user_id, event_id, payload):
            updates.append({"event_id": event_id, "payload": payload.model_dump(exclude_none=True)})
            return _updated_event(event_id, updates[-1]["payload"])

    executor = AssistantActionExecutor(event_service=FakeEventService(), task_service=SimpleNamespace())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal([{"type": "cancel_event", "payload": {"event_id": 43}}]),
            option_id="A",
        )
    )

    assert updates == [{"event_id": 43, "payload": {"status": "canceled"}}]
    assert result["related_event_id"] == 43
    assert result["actions"][0]["result"]["event"]["status"] == "canceled"


def test_action_executor_marks_event_completed() -> None:
    updates: list[dict] = []

    class FakeEventService:
        async def update_event(self, *, user_id, event_id, payload):
            updates.append({"event_id": event_id, "payload": payload.model_dump(exclude_none=True)})
            return _updated_event(event_id, updates[-1]["payload"])

    executor = AssistantActionExecutor(event_service=FakeEventService(), task_service=SimpleNamespace())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal([{"type": "mark_event_completed", "payload": {"event_id": 44}}]),
            option_id="A",
        )
    )

    assert updates == [{"event_id": 44, "payload": {"status": "completed"}}]
    assert result["related_event_id"] == 44
    assert result["actions"][0]["result"]["event"]["status"] == "completed"


def test_action_executor_marks_task_completed() -> None:
    updates: list[dict] = []

    class FakeTaskService:
        async def update_task(self, *, user_id, task_id, payload):
            updates.append({"task_id": task_id, "payload": payload.model_dump(exclude_none=True)})
            return _updated_task(task_id, updates[-1]["payload"])

    executor = AssistantActionExecutor(event_service=SimpleNamespace(), task_service=FakeTaskService())
    result = asyncio.run(
        executor.execute(
            user_id="local-user",
            proposal=_proposal([{"type": "mark_task_completed", "payload": {"task_id": 45}}]),
            option_id="A",
        )
    )

    assert updates == [{"task_id": 45, "payload": {"status": "done"}}]
    assert result["related_task_id"] == 45
    assert result["actions"][0]["result"]["task"]["status"] == "done"
