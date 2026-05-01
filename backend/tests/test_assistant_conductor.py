from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.assistant_agents import AssistantAgentContext, AssistantConductor
from app.api.schemas import AssistantMessageCreate
from app.services.assistant import AssistantService


def run_conductor(message: str, *, events=None, tasks=None):
    conductor = AssistantConductor.build_default()
    context = AssistantAgentContext(
        user_id="demo-user",
        session_id=1,
        user_message=message,
        history=[],
        events=events or [],
        tasks=tasks or [],
        profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
        external_context={},
        now=datetime(2026, 5, 2, 9, 0),
    )
    return asyncio.run(conductor.run(context, mode="shadow"))


def _event(event_id: int, title: str, *, hour: int = 10, status: str = "planned"):
    return SimpleNamespace(
        id=event_id,
        title=title,
        start_time=datetime(2026, 5, 3, hour, 0),
        end_time=datetime(2026, 5, 3, hour + 1, 30),
        location_name="学校",
        status=status,
    )


def _task(task_id: int, content: str, *, status: str = "pending"):
    return SimpleNamespace(id=task_id, content=content, status=status)


def test_conductor_clarifies_vague_dating_request() -> None:
    result = run_conductor("我要去约会")

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.reply is not None
    assert "日期" in result.reply or "时间" in result.reply


def test_conductor_proposes_clear_event_with_assumed_duration() -> None:
    result = run_conductor("明天下午3点我要去学校和同学见面")

    assert result.decision == "proposal"
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.display_id == "P1"
    assert proposal.proposal_type == "event_creation"
    assert proposal.options[0].actions[0]["type"] == "create_event"
    assert proposal.options[0].actions[0]["payload"]["location_name"] == "学校"
    assert "不会直接写入" in (result.reply or "")


def test_conductor_clarifies_generic_study_task() -> None:
    result = run_conductor("帮我安排复习")

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.goal_type == "task"
    assert "科目" in (result.reply or "")
    assert "截止" in (result.reply or "")


def test_conductor_proposes_reschedule_for_unique_event_target() -> None:
    result = run_conductor("把组会改到明天下午4点", events=[_event(12, "组会")])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 12
    action = proposal.options[0].actions[0]
    assert action["type"] == "reschedule_event"
    assert action["payload"]["event_id"] == 12
    update = action["payload"]["update"]
    start_time = datetime.fromisoformat(update["start_time"])
    end_time = datetime.fromisoformat(update["end_time"])
    assert start_time.hour == 16
    assert start_time.date().isoformat() == "2026-05-03"
    assert int((end_time - start_time).total_seconds() // 60) == 90
    assert "确认" in (result.reply or "")


def test_conductor_clarifies_ambiguous_event_update_target() -> None:
    result = run_conductor(
        "取消组会",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert "哪一个日程" in (result.reply or "")
    assert "项目组会" in (result.reply or "")


def test_conductor_proposes_cancel_for_unique_event_target() -> None:
    result = run_conductor("取消政治课", events=[_event(14, "政治课")])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_cancel"
    action = proposal.options[0].actions[0]
    assert action == {"type": "cancel_event", "payload": {"event_id": 14}}


def test_conductor_proposes_task_completion_for_unique_task_target() -> None:
    result = run_conductor("整理毕设论文任务完成了", tasks=[_task(21, "整理毕设论文")])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 21
    action = proposal.options[0].actions[0]
    assert action == {"type": "mark_task_completed", "payload": {"task_id": 21}}


def test_assistant_service_runs_conductor_shadow_without_persistence() -> None:
    service = AssistantService()
    service.settings.assistant_conductor_mode = "shadow"

    result = asyncio.run(
        service._run_conductor_for_message(
            user_id="demo-user",
            session_id=1,
            user_message="明天下午3点我要去学校和同学见面",
            history=[],
            events=[],
            tasks=[],
            profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
            external_context={
                "assistant_memory": {
                    "source": "confirmed_long_term_memory",
                    "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
                }
            },
        )
    )

    assert result is not None
    assert result.mode == "shadow"
    assert result.decision == "proposal"


def test_assistant_service_persists_conductor_proposals_in_proposal_mode() -> None:
    service = AssistantService()
    service.settings.assistant_conductor_mode = "proposal"
    persisted_payloads = []

    class FakeProposalManager:
        async def create_proposal(self, *, user_id, payload):
            persisted_payloads.append((user_id, payload))
            return SimpleNamespace(id=101, status="pending")

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    result = asyncio.run(
        service._run_conductor_for_message(
            user_id="demo-user",
            session_id=1,
            user_message="明天下午3点我要去学校和同学见面",
            history=[],
            events=[],
            tasks=[],
            profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
            external_context={
                "assistant_memory": {
                    "source": "confirmed_long_term_memory",
                    "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
                }
            },
        )
    )

    assert result is not None
    assert result.mode == "proposal"
    assert result.decision == "proposal"
    assert result.metadata["persisted_proposal_ids"] == [101]
    assert len(persisted_payloads) == 1
    user_id, payload = persisted_payloads[0]
    assert user_id == "demo-user"
    assert payload.session_id == 1
    assert payload.status == "pending"
    event_action = payload.payload_json["options"][0]["actions"][0]
    assert event_action["type"] == "create_event"
    assert event_action["payload"]["location_name"] == "北京大学东门"
    assert event_action["payload"]["location_coords"] == "116.310918,39.992873"


def test_send_message_proposal_mode_short_circuits_legacy_write_path() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        service.settings.enable_workflow = False
        messages = []
        persisted_payloads = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        class FakeProposalManager:
            async def create_proposal(self, *, user_id, payload):
                persisted_payloads.append((user_id, payload))
                return SimpleNamespace(id=202, status="pending")

        async def fail_create_event(**_kwargs):
            raise AssertionError("legacy event write path should not run in proposal mode")

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name="宿舍",
                home_location_coords=None,
                work_location_name="学校",
                work_location_coords=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            )

        async def fake_list_tasks(**_kwargs):
            return []

        async def fake_build_external_context(**_kwargs):
            return {}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service.event_service.create_event = fail_create_event  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="明天下午3点我要去学校和同学见面"),
        )

        assert response.actions == []
        assert "待确认方案" in response.reply
        assert "不会直接写入" in response.reply
        assert len(persisted_payloads) == 1
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())
