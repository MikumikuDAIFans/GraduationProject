from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
import asyncio

from app.api.schemas import AssistantAction, AssistantInboxItem, AssistantInboxRead
from app.services.assistant import AssistantService


def test_extract_time_range_from_english_message() -> None:
    service = AssistantService()

    start_time, end_time = service._extract_time_range("create an event tomorrow from 15:00 to 16:00")

    assert start_time is not None
    assert end_time is not None
    assert start_time.hour == 15
    assert end_time.hour == 16


def test_extract_event_title_from_message() -> None:
    service = AssistantService()

    title = service._extract_event_title("create an event called mock defense tomorrow from 15:00 to 16:00")

    assert title == "mock defense"


def test_find_event_conflicts() -> None:
    service = AssistantService()
    existing_events = [
        SimpleNamespace(
            id=1,
            title="Existing rehearsal",
            start_time=datetime.fromisoformat("2026-03-26T15:00:00"),
            end_time=datetime.fromisoformat("2026-03-26T16:00:00"),
        )
    ]

    conflicts = service._find_event_conflicts(
        existing_events=existing_events,
        start_time=datetime.fromisoformat("2026-03-26T15:30:00"),
        end_time=datetime.fromisoformat("2026-03-26T16:30:00"),
    )

    assert len(conflicts) == 1
    assert conflicts[0]["title"] == "Existing rehearsal"


def test_suggest_alternative_slots() -> None:
    service = AssistantService()
    existing_events = [
        SimpleNamespace(
            id=1,
            title="Existing rehearsal",
            start_time=datetime.fromisoformat("2026-03-26T15:00:00"),
            end_time=datetime.fromisoformat("2026-03-26T16:00:00"),
        )
    ]

    suggestions = service._suggest_alternative_slots(
        existing_events=existing_events,
        start_time=datetime.fromisoformat("2026-03-26T15:30:00"),
        end_time=datetime.fromisoformat("2026-03-26T16:30:00"),
    )

    assert suggestions
    assert suggestions[0]["start_time"].startswith("2026-03-26T08:00:00")


def test_conflict_reply_does_not_claim_creation() -> None:
    service = AssistantService()

    reply = service._compose_reply(
        base_reply="I created it.",
        actions=[
            AssistantAction(
                type="conflict_warning",
                payload={
                    "title": "conflict test",
                    "conflicts": [{"title": "Existing rehearsal"}],
                    "suggestions": [
                        {
                            "start_time": "2026-03-26T08:00:00",
                            "end_time": "2026-03-26T09:00:00",
                        }
                    ],
                },
            )
        ],
        requested_actions=[{"type": "create_event", "payload": {}}],
        fallback_message="create event",
        event_count=1,
        task_count=0,
    )

    assert "did not create" in reply
    assert "Suggested slots" in reply


def test_extract_time_range_from_chinese_afternoon_message() -> None:
    service = AssistantService()

    start_time, end_time = service._extract_time_range(
        "帮我安排明天下午三点到四点在图书馆开组会",
        reference=datetime.fromisoformat("2026-03-27T09:00:00"),
    )

    assert start_time is not None
    assert end_time is not None
    assert start_time.isoformat().startswith("2026-03-28T15:00:00")
    assert end_time.isoformat().startswith("2026-03-28T16:00:00")


def test_extract_time_range_from_next_weekday_message() -> None:
    service = AssistantService()

    start_time, end_time = service._extract_time_range(
        "下周一上午十点到十一点答辩彩排",
        reference=datetime.fromisoformat("2026-03-27T09:00:00"),
    )

    assert start_time is not None
    assert end_time is not None
    assert start_time.isoformat().startswith("2026-03-30T10:00:00")
    assert end_time.isoformat().startswith("2026-03-30T11:00:00")


def test_extract_location_from_chinese_message() -> None:
    service = AssistantService()

    location = service._extract_location("明天下午三点到四点在图书馆开组会")

    assert location == "图书馆"


def test_build_rule_based_task_payload_from_chinese_deadline_message() -> None:
    service = AssistantService()

    payload = service._build_rule_based_task_payload("提醒我明晚之前完成论文初稿，预计两小时，可以拆分")

    assert payload["content"] == "完成论文初稿"
    assert payload["estimated_duration_minutes"] == 120
    assert payload["can_split"] is True
    assert payload["deadline"] is not None


def test_build_schedule_guidance_reply_uses_context() -> None:
    service = AssistantService()
    events = [
        SimpleNamespace(
            title="组会",
            start_time=datetime.fromisoformat("2026-03-28T10:00:00"),
            end_time=datetime.fromisoformat("2026-03-28T11:00:00"),
        )
    ]
    tasks = [SimpleNamespace(content="复习答辩", priority=3)]
    profile = SimpleNamespace(home_location_name="宿舍", work_location_name="图书馆")

    reply = service._build_schedule_guidance_reply(
        user_message="明天把复习和买东西插进去",
        events=events,
        tasks=tasks,
        profile=profile,
        external_context={
            "default_commute": {"duration_minutes": 35},
            "weather_now": {"text": "晴", "temp": "22"},
        },
        schedule_items=[],
    )

    assert "可用空档" in reply
    assert "复习" in reply
    assert "天气" in reply


def test_build_plan_falls_back_to_rule_based_actions_when_gemini_has_no_actions() -> None:
    service = AssistantService()

    async def fake_generate_plan(**kwargs):
        return {"reply": "模型没有给动作。", "actions": []}

    service.gemini.generate_plan = fake_generate_plan  # type: ignore[method-assign]

    result = asyncio.run(
        service._build_plan(
            user_id="demo-user",
            user_message="帮我安排明天下午三点到四点在图书馆开组会",
            history=[],
            events=[],
            tasks=[],
            profile=SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                work_location_name=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            ),
            external_context={},
        )
    )

    assert result["actions"]
    assert result["actions"][0]["type"] == "create_event"


def test_format_schedule_summary_includes_split_segments() -> None:
    service = AssistantService()

    summary = service._format_schedule_summary(
        action=AssistantAction(
            type="suggest_schedule",
            payload={
                "items": [
                    {
                        "title": "Split Write thesis chapter",
                        "start_time": "2026-03-28T12:00:00",
                        "end_time": "2026-03-28T13:00:00",
                        "segment_index": 1,
                        "segment_total": 3,
                    },
                    {
                        "title": "Split Write thesis chapter",
                        "start_time": "2026-03-28T13:05:00",
                        "end_time": "2026-03-28T14:05:00",
                        "segment_index": 2,
                        "segment_total": 3,
                    },
                ]
            },
        ),
        prefers_chinese=True,
    )

    assert "第 1/3 段" in summary
    assert "2026-03-28T12:00:00" in summary


def test_build_plan_returns_schedule_suggestions_for_guidance_requests() -> None:
    service = AssistantService()

    async def fake_generate_plan(**kwargs):
        return {"reply": "", "actions": []}

    async def fake_build_suggestions_for_dates(**kwargs):
        return [
            SimpleNamespace(
                model_dump=lambda mode="json": {
                    "type": "task_split_slot",
                    "title": "Split thesis writing",
                    "start_time": "2026-03-28T12:00:00",
                    "end_time": "2026-03-28T13:00:00",
                    "segment_index": 1,
                    "segment_total": 2,
                },
                title="Split thesis writing",
                start_time=datetime.fromisoformat("2026-03-28T12:00:00"),
                end_time=datetime.fromisoformat("2026-03-28T13:00:00"),
                segment_index=1,
                segment_total=2,
            )
        ]

    service.gemini.generate_plan = fake_generate_plan  # type: ignore[method-assign]
    service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]
    service._classify_intent = lambda *_args, **_kwargs: "schedule_guidance"  # type: ignore[method-assign]

    result = asyncio.run(
        service._build_plan(
            user_id="demo-user",
            user_message="明天把论文插进去",
            history=[],
            events=[],
            tasks=[],
            profile=SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                work_location_name=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            ),
            external_context={},
        )
    )

    assert result["actions"]
    assert result["actions"][0]["type"] == "suggest_schedule"


def test_classify_intent_detects_schedule_guidance_phrases() -> None:
    service = AssistantService()

    intent = service._classify_intent("明天把论文安排进去")

    assert intent == "schedule_guidance"


def test_classify_intent_detects_event_context_advice() -> None:
    service = AssistantService()

    intent = service._classify_intent("明天下午三点去图书馆开组会，我几点出发，要不要带伞")

    assert intent == "event_context_advice"


def test_build_plan_short_circuits_gemini_for_event_context_advice() -> None:
    service = AssistantService()

    async def fail_generate_plan(**kwargs):
        raise AssertionError("Gemini should not be called for direct event context advice")

    service.gemini.generate_plan = fail_generate_plan  # type: ignore[method-assign]
    service._classify_intent = lambda *_args, **_kwargs: "event_context_advice"  # type: ignore[method-assign]

    async def fake_build_event_specific_context(**kwargs):
        return {
            "commute_summary": "从宿舍到图书馆预计约 25 分钟。",
            "weather_summary": "图书馆当前天气 小雨, 18°C。",
            "advice_summary": "建议带伞或预留天气变化时间。",
        }

    service._build_event_specific_context = fake_build_event_specific_context  # type: ignore[method-assign]

    result = asyncio.run(
        service._build_plan(
            user_id="demo-user",
            user_message="明天下午三点去图书馆开组会，我几点出发，要不要带伞",
            history=[],
            events=[],
            tasks=[],
            profile=SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name="宿舍",
                work_location_name="实验室",
                transport_preference="driving",
                wake_up_time=None,
                sleep_time=None,
            ),
            external_context={},
        )
    )

    assert "带伞" in result["reply"]
    assert result["actions"]
    assert result["actions"][0]["type"] == "propose_event"


def test_build_event_advice_reply_uses_event_specific_context() -> None:
    service = AssistantService()

    reply = service._build_event_advice_reply(
        payload={
            "title": "组会",
            "start_time": "2026-03-28T15:00:00",
            "end_time": "2026-03-28T16:00:00",
            "location_name": "图书馆",
        },
        user_message="明天下午三点去图书馆开组会，我几点出发，要不要带伞",
        event_context={
            "commute_summary": "从宿舍到图书馆预计约 25 分钟。",
            "weather_summary": "图书馆当前天气 小雨, 18°C。",
            "advice_summary": "建议带伞或预留天气变化时间。",
        },
        profile=SimpleNamespace(home_location_name="宿舍", work_location_name="实验室"),
    )

    assert "25 分钟" in reply
    assert "小雨" in reply
    assert "带伞" in reply


def test_classify_intent_detects_progress_followup() -> None:
    service = AssistantService()

    intent = service._classify_intent("现在进展如何，接下来怎么安排")

    assert intent == "progress_followup"


def test_classify_confirmation_intent_detects_confirm_and_cancel() -> None:
    service = AssistantService()

    assert service._classify_confirmation_intent("按这个安排执行") == "confirm"
    assert service._classify_confirmation_intent("按这个建议创建") == "confirm"
    assert service._classify_confirmation_intent("取消这个计划") == "cancel"


def test_persist_pending_action_only_overwrites_with_new_action() -> None:
    service = AssistantService()
    calls: list[dict] = []

    async def fake_update_session_context(session_id, *, user_id, context_json):
        calls.append(context_json)
        return None

    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]

    asyncio.run(
        service._persist_pending_action(
            user_id="demo-user",
            session_id=1,
            existing_context={"pending_action": {"type": "schedule", "payload": {"items": [{"title": "old"}]}}},
            actions=[],
        )
    )

    assert calls == []

    asyncio.run(
        service._persist_pending_action(
            user_id="demo-user",
            session_id=1,
            existing_context={},
            actions=[
                AssistantAction(
                    type="suggest_schedule",
                    payload={"items": [{"title": "new"}]},
                )
            ],
        )
    )

    assert calls
    assert calls[-1]["pending_action"]["payload"]["items"][0]["title"] == "new"


def test_apply_pending_action_creates_schedule_events_and_clears_context() -> None:
    service = AssistantService()
    created_payloads: list[dict] = []
    updated_contexts: list[dict] = []

    async def fake_create_event(*, user_id, payload):
        created_payloads.append(payload.model_dump())
        return SimpleNamespace(
            id=len(created_payloads),
            title=payload.title,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=payload.location_name,
            location_coords=None,
            departure_time=None,
            travel_duration_minutes=None,
            sync_status="local_only",
        )

    async def fake_update_session_context(session_id, *, user_id, context_json):
        updated_contexts.append(context_json)
        return None

    async def fake_build_event_specific_context(**kwargs):
        return {}

    async def fake_sync_task_schedule_state(*, user_id, task_id):
        return SimpleNamespace(
            id=task_id,
            content="Write thesis chapter",
            status="scheduled",
            scheduled_minutes=120,
            scheduled_blocks_count=2,
            remaining_minutes=60,
        )

    service.event_service.create_event = fake_create_event  # type: ignore[method-assign]
    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]
    service._build_event_specific_context = fake_build_event_specific_context  # type: ignore[method-assign]
    service.task_service.sync_task_schedule_state = fake_sync_task_schedule_state  # type: ignore[method-assign]

    response = asyncio.run(
        service._apply_pending_action(
            user_id="demo-user",
            session_id=1,
            session_context={"pending_action": {"type": "schedule", "payload": {"items": [
                {
                    "title": "Split Write thesis chapter",
                    "description": "Segment 1",
                    "start_time": "2026-03-28T12:00:00",
                    "end_time": "2026-03-28T13:00:00",
                    "related_task_id": 99,
                    "segment_index": 1,
                    "segment_total": 2,
                },
                {
                    "title": "Split Write thesis chapter",
                    "description": "Segment 2",
                    "start_time": "2026-03-28T13:05:00",
                    "end_time": "2026-03-28T14:05:00",
                    "related_task_id": 99,
                    "segment_index": 2,
                    "segment_total": 2,
                },
            ]}}},
            pending_action={"type": "schedule", "payload": {"items": [
                {
                    "title": "Split Write thesis chapter",
                    "description": "Segment 1",
                    "start_time": "2026-03-28T12:00:00",
                    "end_time": "2026-03-28T13:00:00",
                    "related_task_id": 99,
                    "segment_index": 1,
                    "segment_total": 2,
                },
                {
                    "title": "Split Write thesis chapter",
                    "description": "Segment 2",
                    "start_time": "2026-03-28T13:05:00",
                    "end_time": "2026-03-28T14:05:00",
                    "related_task_id": 99,
                    "segment_index": 2,
                    "segment_total": 2,
                },
            ]}},
            profile=SimpleNamespace(),
            user_message="按这个安排执行",
        )
    )

    assert len(created_payloads) == 2
    assert created_payloads[0]["linked_task_id"] == 99
    assert response.actions[0].type == "apply_schedule"
    assert response.actions[0].payload["linked_tasks"][0]["status"] == "scheduled"
    assert updated_contexts[-1] == {}


def test_apply_pending_event_creates_event_and_clears_context() -> None:
    service = AssistantService()
    updated_contexts: list[dict] = []

    async def fake_create_event(*, user_id, payload):
        return SimpleNamespace(
            id=10,
            title=payload.title,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=payload.location_name,
            location_coords=None,
            departure_time=None,
            travel_duration_minutes=None,
            sync_status="local_only",
        )

    async def fake_update_session_context(session_id, *, user_id, context_json):
        updated_contexts.append(context_json)
        return None

    async def fake_build_event_specific_context(**kwargs):
        return {"commute_summary": "从宿舍到图书馆预计约 25 分钟。"}

    service.event_service.create_event = fake_create_event  # type: ignore[method-assign]
    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]
    service._build_event_specific_context = fake_build_event_specific_context  # type: ignore[method-assign]

    response = asyncio.run(
        service._apply_pending_action(
            user_id="demo-user",
            session_id=1,
            session_context={"pending_action": {"type": "event", "payload": {"title": "组会", "start_time": "2026-03-28T15:00:00", "end_time": "2026-03-28T16:00:00", "location_name": "图书馆"}}},
            pending_action={"type": "event", "payload": {"title": "组会", "start_time": "2026-03-28T15:00:00", "end_time": "2026-03-28T16:00:00", "location_name": "图书馆"}},
            profile=SimpleNamespace(),
            user_message="按这个建议创建",
        )
    )

    assert response.actions[0].type == "apply_event_proposal"
    assert response.actions[1].type == "create_event"
    assert updated_contexts[-1] == {}


def test_build_progress_followup_plan_returns_reply_and_schedule_action() -> None:
    service = AssistantService()

    async def fake_list_recent_task_followups(*, user_id: str, limit: int = 6):
        return [
            SimpleNamespace(message="Task progress updated: Write thesis chapter is now 60 / 180 minutes complete."),
            SimpleNamespace(message="Task replan needed: Write thesis chapter still has 60 minutes remaining."),
        ]

    async def fake_build_suggestions_for_dates(**kwargs):
        return [
            SimpleNamespace(
                model_dump=lambda mode="json": {
                    "type": "task_replan_slot",
                    "title": "Replan Write thesis chapter",
                    "start_time": "2026-03-29T15:10:00",
                    "end_time": "2026-03-29T16:10:00",
                },
                title="Replan Write thesis chapter",
                start_time=datetime.fromisoformat("2026-03-29T15:10:00"),
                end_time=datetime.fromisoformat("2026-03-29T16:10:00"),
            )
        ]

    service.reminder_repository.list_recent_task_followups = fake_list_recent_task_followups  # type: ignore[method-assign]
    service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]

    result = asyncio.run(
        service._build_progress_followup_plan(
            user_id="demo-user",
            user_message="现在进展如何，接下来怎么安排",
            tasks=[
                SimpleNamespace(
                    id=12,
                    content="Write thesis chapter",
                    status="in_progress",
                    completed_minutes=60,
                    remaining_minutes=60,
                    scheduled_minutes=120,
                )
            ],
        )
    )

    assert result is not None
    assert "Write thesis chapter" in result["reply"]
    assert result["actions"]
    assert result["actions"][0]["type"] == "suggest_schedule"


def test_get_inbox_combines_followups_tasks_and_suggestions() -> None:
    service = AssistantService()

    async def fake_list_tasks(user_id: str):
        return [
            SimpleNamespace(
                id=12,
                content="Write thesis chapter",
                status="in_progress",
                completed_minutes=60,
                remaining_minutes=60,
                scheduled_minutes=120,
            )
        ]

    async def fake_list_recent_task_followups(*, user_id: str, limit: int = 10):
        return [
            SimpleNamespace(
                id=25,
                remind_type="task_replan",
                message="Task replan needed: Write thesis chapter still has 60 minutes remaining.",
                target_id=12,
                remind_at=datetime.fromisoformat("2026-03-28T02:00:00"),
            )
        ]

    async def fake_build_suggestions_for_dates(**kwargs):
        return [
            SimpleNamespace(
                model_dump=lambda mode="json": {
                    "type": "task_replan_slot",
                    "title": "Replan Write thesis chapter",
                    "start_time": "2026-03-29T15:10:00",
                    "end_time": "2026-03-29T16:10:00",
                },
                title="Replan Write thesis chapter",
                start_time=datetime.fromisoformat("2026-03-29T15:10:00"),
                end_time=datetime.fromisoformat("2026-03-29T16:10:00"),
                related_task_id=12,
            )
        ]

    service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
    service.reminder_repository.list_recent_task_followups = fake_list_recent_task_followups  # type: ignore[method-assign]
    service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]

    inbox = asyncio.run(service.get_inbox("demo-user"))

    assert inbox.total >= 1
    kinds = [item.kind for item in inbox.items]
    assert "task_followup_group" in kinds


def test_build_summary_cards_include_cross_panel_targets() -> None:
    service = AssistantService()

    cards = service._build_summary_cards(
        inbox=AssistantInboxRead(
            items=[
                AssistantInboxItem(
                    id="group-task-12",
                    kind="task_followup_group",
                    title="Write thesis chapter",
                    description="summary",
                    priority=3,
                    thread_id="task-12",
                    related_task_id=12,
                    read=False,
                )
            ],
            total=1,
            unread_total=1,
        ),
        tasks=[
            SimpleNamespace(
                id=12,
                content="Write thesis chapter",
                status="in_progress",
                completed_minutes=60,
                remaining_minutes=60,
                scheduled_minutes=120,
            )
        ],
        reminders=[
            SimpleNamespace(
                target_type="task",
                target_id=12,
                remind_type="task_replan",
                remind_at=datetime.fromisoformat("2026-03-29T08:00:00"),
                message="Task replan needed.",
                status="pending",
            )
        ],
        suggestions=[
            SimpleNamespace(
                type="task_replan_slot",
                title="Replan Write thesis chapter",
                start_time=datetime.fromisoformat("2026-03-29T15:10:00"),
                end_time=datetime.fromisoformat("2026-03-29T16:10:00"),
                related_task_id=12,
                related_event_id=None,
            )
        ],
    )

    followups = next(card for card in cards if card.id == "followups")
    top_task = next(card for card in cards if card.id == "top-task")
    next_suggestion = next(card for card in cards if card.id == "next-suggestion")
    next_reminder = next(card for card in cards if card.id == "next-reminder")

    assert followups.thread_id == "task-12"
    assert followups.related_task_id == 12
    assert top_task.related_task_id == 12
    assert next_suggestion.related_task_id == 12
    assert next_suggestion.meta["suggestion_type"] == "task_replan_slot"
    assert next_reminder.related_task_id == 12
    assert next_reminder.meta["target_type"] == "task"


def test_sync_inbox_to_session_creates_message_once_per_item() -> None:
    service = AssistantService()
    created_messages: list[dict] = []
    updated_contexts: list[dict] = []
    next_id = 1

    async def fake_create_message(*, session_id: int, role: str, content: str, tool_calls_json=None):
        nonlocal next_id
        created_messages.append(
            {
                "id": next_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "tool_calls_json": tool_calls_json,
            }
        )
        message = SimpleNamespace(id=next_id)
        next_id += 1
        return message

    async def fake_update_session_context(session_id, *, user_id, context_json):
        updated_contexts.append(context_json)
        return SimpleNamespace(id=session_id, context_json=context_json)

    service.repository.create_message = fake_create_message  # type: ignore[method-assign]
    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]

    session = SimpleNamespace(id=1, context_json={})
    inbox = SimpleNamespace(
        items=[
            AssistantInboxItem(
                id="reminder-1",
                kind="task_replan",
                title="Task Replan Needed",
                description="Write thesis chapter still has 60 minutes remaining.",
                priority=3,
                action_label="Review Plan",
                action_message="现在进展如何，接下来怎么安排",
                related_task_id=1,
            )
        ]
    )

    asyncio.run(service._sync_inbox_to_session(user_id="demo-user", session=session, inbox=inbox))
    asyncio.run(
        service._sync_inbox_to_session(
            user_id="demo-user",
            session=SimpleNamespace(id=1, context_json=updated_contexts[-1]),
            inbox=inbox,
        )
    )

    assert len(created_messages) == 1
    assert updated_contexts[-1]["surfaced_inbox_ids"] == ["reminder-1"]


def test_sync_inbox_to_session_hides_old_task_followups_when_group_arrives() -> None:
    service = AssistantService()
    updated_contexts: list[dict] = []
    next_id = 20

    async def fake_create_message(*, session_id: int, role: str, content: str, tool_calls_json=None):
        nonlocal next_id
        message = SimpleNamespace(id=next_id)
        next_id += 1
        return message

    async def fake_update_session_context(session_id, *, user_id, context_json):
        updated_contexts.append(context_json)
        return SimpleNamespace(id=session_id, context_json=context_json)

    service.repository.create_message = fake_create_message  # type: ignore[method-assign]
    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]

    session = SimpleNamespace(
        id=1,
        context_json={
            "surfaced_inbox_ids": ["reminder-1", "task-1"],
            "task_followup_message_ids": {"1": [11, 12]},
        },
    )
    inbox = SimpleNamespace(
        items=[
            AssistantInboxItem(
                id="group-task-1",
                kind="task_followup_group",
                title="Task Follow-up · 1",
                description="summary",
                priority=3,
                related_task_id=1,
                meta={"entries": []},
            )
        ]
    )

    asyncio.run(service._sync_inbox_to_session(user_id="demo-user", session=session, inbox=inbox))

    assert updated_contexts[-1]["hidden_message_ids"] == [11, 12]
    assert updated_contexts[-1]["task_followup_message_ids"]["1"] == [20]


def test_get_session_filters_hidden_messages() -> None:
    service = AssistantService()
    session = SimpleNamespace(
        id=1,
        user_id="demo-user",
        session_type="chat",
        context_json={"hidden_message_ids": [2]},
        created_at=None,
        updated_at=None,
    )
    messages = [
        SimpleNamespace(id=1, session_id=1, role="assistant", content="keep", tool_calls_json=None, created_at=datetime.now()),
        SimpleNamespace(id=2, session_id=1, role="assistant", content="hide", tool_calls_json=None, created_at=datetime.now()),
    ]

    async def fake_get_session(session_id: int, *, user_id: str):
        return session

    async def fake_list_messages(session_id: int):
        return messages

    service.repository.get_session = fake_get_session  # type: ignore[method-assign]
    service.repository.list_messages = fake_list_messages  # type: ignore[method-assign]

    result = asyncio.run(service.get_session(user_id="demo-user", session_id=1))

    assert len(result.messages) == 1
    assert result.messages[0].content == "keep"


def test_render_inbox_group_as_summary_message() -> None:
    service = AssistantService()

    content = service._render_inbox_item_as_message(
        AssistantInboxItem(
            id="group-task-1",
            kind="task_followup_group",
            title="Write thesis chapter",
            description="summary",
            priority=3,
            related_task_id=1,
            meta={
                "entries": [
                    {
                        "title": "Task Replan Needed",
                        "description": "Still has 60 minutes remaining.",
                    },
                    {
                        "title": "Task Progress Update",
                        "description": "Completed 60 minutes.",
                    },
                ]
            },
        )
    )

    assert "Task Replan Needed" in content
    assert "Completed 60 minutes" in content


def test_mark_inbox_item_read_and_archive() -> None:
    service = AssistantService()
    updated_contexts: list[dict] = []
    session = SimpleNamespace(id=1, context_json={})

    async def fake_get_latest_session(*, user_id: str, session_type: str = "chat"):
        return session

    async def fake_update_session_context(session_id, *, user_id, context_json):
        updated_contexts.append(context_json)
        session.context_json = context_json
        return session

    async def fake_get_inbox(user_id: str):
        return SimpleNamespace(
            items=[
                AssistantInboxItem(
                    id="group-task-1",
                    kind="task_followup_group",
                    title="Task Follow-up · 1",
                    description="summary",
                    priority=3,
                    thread_id="task-1",
                    related_task_id=1,
                    meta={"entries": []},
                )
            ]
        )

    service.repository.get_latest_session = fake_get_latest_session  # type: ignore[method-assign]
    service.repository.update_session_context = fake_update_session_context  # type: ignore[method-assign]
    service.get_inbox = fake_get_inbox  # type: ignore[method-assign]

    asyncio.run(service.mark_inbox_item(user_id="demo-user", item_id="group-task-1", action="read"))
    assert updated_contexts[-1]["inbox_item_state"]["group-task-1"]["read"] is True
    assert "updated_at" in updated_contexts[-1]["inbox_item_state"]["group-task-1"]

    asyncio.run(service.mark_inbox_item(user_id="demo-user", item_id="group-task-1", action="archive"))
    assert updated_contexts[-1]["inbox_item_state"]["group-task-1"]["archived"] is True


def test_cleanup_inbox_state_drops_expired_archived_items() -> None:
    service = AssistantService()
    now = datetime.now()

    cleaned = service._cleanup_inbox_state(
        {
            "fresh-archived": {
                "archived": True,
                "updated_at": now.isoformat(),
            },
            "expired-archived": {
                "archived": True,
                "updated_at": (now - timedelta(days=service.INBOX_ARCHIVE_RETENTION_DAYS + 1)).isoformat(),
            },
            "active": {
                "read": True,
                "updated_at": now.isoformat(),
            },
        }
    )

    assert "fresh-archived" in cleaned
    assert "active" in cleaned
    assert "expired-archived" not in cleaned


def test_build_summary_cards_top_task_has_related_task_id() -> None:
    """Summary card for the primary task must carry related_task_id for cross-panel focus."""
    service = AssistantService()

    task = SimpleNamespace(
        id=42,
        content="Write thesis draft",
        status="in_progress",
        completed_minutes=60,
        scheduled_minutes=120,
        remaining_minutes=60,
        completion_ratio=0.5,
        completed_blocks_count=1,
        scheduled_blocks_count=2,
    )

    inbox = AssistantInboxRead(items=[], total=0, unread_total=0)
    cards = service._build_summary_cards(
        inbox=inbox,
        tasks=[task],
        reminders=[],
        suggestions=[],
    )

    top_task_cards = [card for card in cards if card.id == "top-task"]
    assert top_task_cards, "Expected a 'top-task' card"
    assert top_task_cards[0].related_task_id == 42


def test_build_summary_cards_followups_card_unread_total() -> None:
    """Followups card must reflect inbox unread count and carry action_message when unread > 0."""
    service = AssistantService()

    inbox = AssistantInboxRead(
        items=[
            AssistantInboxItem(
                id="group-task-1",
                kind="task_followup_group",
                title="Test Task",
                description="desc",
                priority=2,
                related_task_id=1,
            )
        ],
        total=1,
        unread_total=1,
    )

    cards = service._build_summary_cards(
        inbox=inbox,
        tasks=[],
        reminders=[],
        suggestions=[],
    )

    followup_cards = [card for card in cards if card.id == "followups"]
    assert followup_cards, "Expected a 'followups' card"
    card = followup_cards[0]
    assert card.value == "1"
    assert card.action_message is not None
    assert card.tone == "warning"
