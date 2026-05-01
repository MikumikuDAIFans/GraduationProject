from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.assistant_agents import AssistantAgentContext, AssistantConductor
from app.services.assistant import AssistantService


def run_conductor(message: str):
    conductor = AssistantConductor.build_default()
    context = AssistantAgentContext(
        user_id="demo-user",
        session_id=1,
        user_message=message,
        history=[],
        events=[],
        tasks=[],
        profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
        external_context={},
    )
    return asyncio.run(conductor.run(context, mode="shadow"))


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
            external_context={},
        )
    )

    assert result is not None
    assert result.mode == "shadow"
    assert result.decision == "proposal"
