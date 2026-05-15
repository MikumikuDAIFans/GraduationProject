from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.assistant_agents import AssistantAgentContext, AssistantConductor, ConductorResult
from app.api.schemas import AssistantMessageCreate
from app.services.assistant import AssistantService


def run_conductor(
    message: str,
    *,
    events=None,
    tasks=None,
    history=None,
    external_context=None,
    semantic_extractor=None,
    now=None,
):
    conductor = AssistantConductor.build_default(semantic_extractor=semantic_extractor)
    context = AssistantAgentContext(
        user_id="demo-user",
        session_id=1,
        user_message=message,
        history=history or [],
        events=events or [],
        tasks=tasks or [],
        profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
        external_context=external_context or {},
        now=now or datetime(2026, 5, 2, 9, 0),
    )
    return asyncio.run(conductor.run(context, mode="shadow"))


class FakeEventSemanticExtractor:
    enabled = True

    async def extract_event_creation_semantics(self, **_kwargs):
        return {
            "goal_type": "event",
            "title": "去驾校接李婷",
            "location_name": "驾校",
            "missing_fields": [],
            "confidence": 0.94,
        }


class FakeMessageUnderstandingExtractor:
    enabled = True

    async def extract_message_understanding(self, **_kwargs):
        return {
            "intent": "create_event",
            "goal_type": "event",
            "title": "驾校接李婷",
            "location_name": "驾校",
            "missing_fields": [],
            "ambiguities": [],
            "confidence": 0.93,
        }

    async def extract_event_creation_semantics(self, **_kwargs):
        raise AssertionError("event-specific extraction should not run when message understanding has event slots")


class FakeTaskUnderstandingExtractor:
    enabled = True

    async def extract_message_understanding(self, **_kwargs):
        return {
            "intent": "create_task",
            "goal_type": "task",
            "task_content": "整理毕设答辩材料",
            "missing_fields": [],
            "ambiguities": [],
            "confidence": 0.9,
        }


class StaticUnderstandingExtractor:
    enabled = True

    def __init__(self, payload):
        self.payload = payload

    async def extract_message_understanding(self, **_kwargs):
        return dict(self.payload)


class InvalidUnderstandingExtractor:
    enabled = True

    async def extract_message_understanding(self, **_kwargs):
        return {
            "intent": "invent_calendar",
            "goal_type": "event",
            "title": "错误结构",
            "confidence": 0.9,
        }


def _event(
    event_id: int,
    title: str,
    *,
    hour: int = 10,
    day: int = 3,
    status: str = "planned",
    linked_task_id: int | None = None,
    event_type: str = "general",
):
    return SimpleNamespace(
        id=event_id,
        title=title,
        start_time=datetime(2026, 5, day, hour, 0),
        end_time=datetime(2026, 5, day, hour + 1, 30),
        location_name="学校",
        status=status,
        linked_task_id=linked_task_id,
        event_type=event_type,
    )


def _event_window(event_id: int, title: str, start: datetime, end: datetime, *, location_name: str = "学校"):
    return SimpleNamespace(
        id=event_id,
        title=title,
        start_time=start,
        end_time=end,
        location_name=location_name,
        status="planned",
    )


def _task(task_id: int, content: str, *, status: str = "pending"):
    return SimpleNamespace(id=task_id, content=content, status=status)


def _message(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_conductor_clarifies_vague_dating_request() -> None:
    result = run_conductor("我要去约会")

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.metadata.get("clarification_source") == "specialized_fallback"
    assert result.reply is not None
    assert "日期" in result.reply or "时间" in result.reply


def test_conductor_proposes_clear_event_with_assumed_duration() -> None:
    result = run_conductor(
        "明天下午3点我要去学校和同学见面",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "和同学见面",
                "location_name": "学校",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.93,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "proposal"
    assert result.understanding.orchestration.user_goal == "create_event"
    assert result.understanding.orchestration.target_scope.kind == "event"
    assert result.understanding.orchestration.proposal_shape == "event_creation"
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.display_id == "P1"
    assert proposal.proposal_type == "event_creation"
    assert proposal.options[0].actions[0]["type"] == "create_event"
    assert proposal.options[0].actions[0]["payload"]["location_name"] == "学校"
    assert proposal.options[0].rationale == "结束时间未明确，先按 1 小时估算，可在确认前修改。"
    assert result.metadata.get("proposal_reply_source") == "orchestration"
    assert "新日程方案" in (result.reply or "")
    assert "先按 1 小时估算" in (result.reply or "")
    assert "不会直接写入" in (result.reply or "")


def test_conductor_falls_back_to_rule_location_for_clear_event() -> None:
    result = run_conductor("明天下午3点我要去学校和同学见面")

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["title"] == "和同学见面"
    assert result.understanding.assumptions == ["default_event_duration_60_minutes"]
    proposal = result.proposals[0]
    assert proposal.options[0].actions[0]["payload"]["location_name"] == "学校"


def test_conductor_falls_back_when_llm_understanding_schema_is_invalid() -> None:
    result = run_conductor(
        "明天下午3点我要去学校和同学见面",
        semantic_extractor=InvalidUnderstandingExtractor(),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "和同学见面"
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["semantic_source"] == "llm_missing"


def test_conductor_falls_back_to_location_before_group_meeting_verb() -> None:
    result = run_conductor("明天下午三点去学校开组会")

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "开组会"
    assert result.understanding.slots["location_name"] == "学校"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "开组会"
    assert payload["location_name"] == "学校"
    assert proposal.options[0].rationale == "结束时间未明确，先按 1 小时估算，可在确认前修改。"
    assert "默认1小时" in (result.reply or "")


def test_conductor_falls_back_to_location_after_chinese_time_range_separator() -> None:
    result = run_conductor("后天上午十点到十一点在培训室培训")

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "培训"
    assert result.understanding.slots["location_name"] == "培训室"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "培训"
    assert payload["location_name"] == "培训室"
    assert payload["start_time"] == "2026-05-04T10:00:00"
    assert payload["end_time"] == "2026-05-04T11:00:00"


def test_conductor_broad_afternoon_destination_event_proposes_time_options() -> None:
    result = run_conductor("下午我想去图书馆")

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["broad_time_period"] == "afternoon"
    proposal = result.proposals[0]
    assert len(proposal.options) >= 3
    assert [option.option_id for option in proposal.options[:3]] == ["A", "B", "C"]
    starts = [
        option.actions[0]["payload"]["start_time"]
        for option in proposal.options[:3]
    ]
    assert starts == [
        "2026-05-02T14:00:00",
        "2026-05-02T15:30:00",
        "2026-05-02T17:00:00",
    ]
    assert all("大概时段" in (option.rationale or "") for option in proposal.options[:3])


def test_assistant_service_assigns_stable_unique_proposal_labels() -> None:
    service = AssistantService()

    labels = service._assign_stable_proposal_labels(  # noqa: SLF001 - protocol regression coverage
        [
            SimpleNamespace(id=1, payload_json={"protocol_label": "P1"}),
            SimpleNamespace(id=2, payload_json={"protocol_label": "P5"}),
            SimpleNamespace(id=3, payload_json={"protocol_label": "P5"}),
            SimpleNamespace(id=4, payload_json={}),
        ]
    )

    assert labels == {1: "P1", 2: "P5", 3: "P6", 4: "P7"}


def test_event_proposal_marks_direct_conflict_and_offers_two_options() -> None:
    existing = _event_window(
        12,
        "图书馆自习",
        datetime(2026, 5, 3, 15, 0),
        datetime(2026, 5, 3, 17, 0),
        location_name="图书馆",
    )
    result = run_conductor(
        "明天下午3点到4点去学校上课",
        events=[existing],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "上课",
                "location_name": "学校",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert "与图书馆自习存在时间冲突" in proposal.summary
    assert len(proposal.options) == 2
    assert proposal.options[0].option_id == "A"
    assert "16:00-17:00" in proposal.options[0].summary
    assert proposal.options[0].actions == [
        {
            "type": "create_event",
            "payload": {
                "title": "上课",
                "start_time": "2026-05-03T16:00:00",
                "end_time": "2026-05-03T17:00:00",
                "location_name": "学校",
                "event_type": "general",
            },
        }
    ]
    assert proposal.options[1].option_id == "B"
    assert "取消或调整“图书馆自习”" in proposal.options[1].summary


def test_event_proposal_marks_travel_buffer_risk_and_suggests_delay() -> None:
    existing = _event_window(
        12,
        "学校上课",
        datetime(2026, 5, 3, 13, 0),
        datetime(2026, 5, 3, 13, 30),
        location_name="学校",
    )
    result = run_conductor(
        "明天下午2点在市中心有个会议",
        events=[existing],
        external_context={"travel_estimates": {"学校->市中心": 35}, "travel_safety_buffer_minutes": 10},
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "会议",
                "location_name": "市中心",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert "出发缓冲不足" in proposal.summary
    assert "14:45或更晚" in proposal.summary
    assert len(proposal.options) == 2
    assert proposal.options[0].actions[0]["payload"]["start_time"] == "2026-05-03T14:45:00"
    assert proposal.options[1].actions[0]["payload"]["start_time"] == "2026-05-03T14:00:00"


def test_event_proposal_adds_departure_guidance_without_direct_conflict() -> None:
    result = run_conductor(
        "后天上午10点去医院体检",
        external_context={"travel_estimates": {"宿舍->医院": 40}, "travel_safety_buffer_minutes": 10},
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "体检",
                "location_name": "医院",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert "建议09:10出发" in proposal.summary
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["travel_duration_minutes"] == 40
    assert payload["departure_time"] == "2026-05-04T09:10:00"


def test_event_proposal_keeps_explicit_origin_without_travel_estimate() -> None:
    result = run_conductor(
        "后天上午10点从家去学校办手续",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "去学校办手续",
                "location_name": "学校",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert "出发地按家处理" in proposal.summary
    assert proposal.payload_json["diagnostics"]["commute_origin"] == "家"
    payload = proposal.options[0].actions[0]["payload"]
    assert "departure_time" not in payload


def test_conductor_clarifies_school_medical_location_conflict() -> None:
    result = run_conductor(
        "后天上午去学校体检",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "体检",
                "location_name": "学校",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert "medical_location_conflict" in result.understanding.ambiguities
    assert "校医院" in (result.reply or "")
    assert "校外医院" in (result.reply or "")


def test_conductor_allows_school_medical_event_when_place_alias_is_confirmed() -> None:
    result = run_conductor(
        "后天上午去学校体检",
        external_context={
            "assistant_memory": {
                "source": "confirmed_long_term_memory",
                "places": ["学校: 学校 = 测试学校地址"],
            }
        },
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "体检",
                "location_name": "学校",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.proposals
    assert "medical_location_conflict" not in (result.understanding.ambiguities if result.understanding else [])
    payload = result.proposals[0].options[0].actions[0]["payload"]
    assert payload["title"] == "体检"
    assert payload["location_name"] == "学校"


def test_conductor_uses_medical_location_clarification_reply_as_event_context() -> None:
    result = run_conductor(
        "在校医院",
        history=[
            _message("user", "后天上午去学校体检"),
            _message("assistant", "你是要去校医院，还是校外医院？如果地点还有其他细节，也请一起告诉我。"),
        ],
    )

    assert result.decision == "proposal"
    assert result.proposals
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "体检"
    assert payload["location_name"] == "校医院"
    assert payload["start_time"] == "2026-05-04T09:00:00"


def test_event_proposal_warns_for_adjacent_different_location_without_blocking() -> None:
    existing = _event_window(
        12,
        "开会",
        datetime(2026, 5, 3, 9, 0),
        datetime(2026, 5, 3, 10, 0),
        location_name="会议室",
    )
    result = run_conductor(
        "明天上午10点到11点培训",
        events=[existing],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "培训",
                "location_name": "培训室",
                "confidence": 0.92,
            }
        ),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert "两条日程之间无间隔" in proposal.summary
    assert len(proposal.options) == 1
    assert proposal.options[0].actions[0]["payload"]["start_time"] == "2026-05-03T10:00:00"


def test_conductor_uses_llm_semantics_for_event_title_and_location() -> None:
    result = run_conductor("中午12点我要去驾校接李婷", semantic_extractor=FakeEventSemanticExtractor())

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["semantic_source"] == "llm_event_semantics"
    assert result.understanding.slots["title"] == "去驾校接李婷"
    assert result.understanding.slots["location_name"] == "驾校"
    assert result.understanding.orchestration is not None
    assert "llm_event_semantics" in result.understanding.orchestration.notes
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "去驾校接李婷"
    assert payload["location_name"] == "驾校"
    assert "点我要" not in proposal.summary
    assert "地点：驾校接李婷" not in proposal.summary


def test_conductor_uses_llm_understanding_before_rule_classification() -> None:
    result = run_conductor("中午12点驾校接李婷", semantic_extractor=FakeMessageUnderstandingExtractor())

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["semantic_source"] == "llm_message_understanding"
    assert result.understanding.slots["title"] == "驾校接李婷"
    assert result.understanding.slots["location_name"] == "驾校"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "驾校接李婷"
    assert payload["location_name"] == "驾校"


def test_conductor_preserves_llm_location_without_program_split() -> None:
    result = run_conductor(
        "明天下午3点我要去学校和同学见面",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "和同学见面",
                "location_name": "学校和同学",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.9,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["semantic_source"] == "llm_message_understanding"
    assert result.understanding.slots["location_name"] == "学校和同学"


def test_conductor_uses_llm_understanding_for_task_content() -> None:
    result = run_conductor("帮我记一下答辩那堆东西", semantic_extractor=FakeTaskUnderstandingExtractor())

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["semantic_source"] == "llm_message_understanding"
    assert result.understanding.slots["content"] == "整理毕设答辩材料"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["content"] == "整理毕设答辩材料"


def test_conductor_without_llm_semantics_still_proposes_clear_pickup_event() -> None:
    result = run_conductor("中午12点我要去驾校接李婷")

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["semantic_source"] == "llm_missing"
    assert result.understanding.slots["title"] == "去驾校接李婷"
    assert result.understanding.slots["location_name"] == "驾校"
    assert result.understanding.assumptions == ["default_event_duration_60_minutes"]
    assert result.understanding.can_propose_without_clarification is True
    assert result.proposals
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "去驾校接李婷"
    assert payload["location_name"] == "驾校"
    assert payload["start_time"] == "2026-05-02T12:00:00"
    assert proposal.options[0].rationale == "结束时间未明确，先按 1 小时估算，可在确认前修改。"


def test_conductor_proposes_clear_task_with_orchestration_reply() -> None:
    result = run_conductor(
        "提醒我整理毕设论文",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_task",
                "goal_type": "task",
                "task_content": "整理毕设论文",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.91,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "proposal"
    assert result.understanding.orchestration.user_goal == "create_task"
    assert result.understanding.orchestration.proposal_shape == "task_creation"
    assert result.metadata.get("proposal_reply_source") == "orchestration"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_creation"
    assert proposal.options[0].actions[0]["type"] == "create_task"
    assert "新任务方案" in (result.reply or "")
    assert "不会直接写入任务" in (result.reply or "")


def test_conductor_task_arrangement_request_proposes_three_split_options() -> None:
    result = run_conductor("这周帮我安排复习英语", now=datetime(2026, 5, 15, 9, 0))

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "create_task"
    assert result.understanding.slots["content"] == "复习英语"
    assert result.understanding.slots["schedule_window"] == "this_week"
    assert result.understanding.slots["wants_schedule_options"] is True
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_creation"
    assert proposal.payload_json["proposal_shape"] == "task_creation_with_schedule_options"
    assert [option.option_id for option in proposal.options] == ["A", "B", "C"]
    assert len({option.title for option in proposal.options}) == 3
    for option in proposal.options:
        assert option.actions[0]["type"] == "create_task_with_events"
        payload = option.actions[0]["payload"]
        assert payload["task"]["content"] == "复习英语"
        assert payload["task"]["can_split"] is True
        assert len(payload["events"]) >= 2
        assert all(event["event_type"] == "focus_block" for event in payload["events"])
        assert all("linked_task_id" not in event for event in payload["events"])
    assert len(proposal.options[0].actions[0]["payload"]["events"]) == 3
    assert len(proposal.options[1].actions[0]["payload"]["events"]) == 2
    assert "方案 A" in (result.reply or "")
    assert "方案 B" in (result.reply or "")
    assert "方案 C" in (result.reply or "")


def test_conductor_uses_orchestration_clarification_for_incomplete_event() -> None:
    result = run_conductor("我要去学校和同学见面")

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "create_event"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "可确认的日程方案" in (result.reply or "")
    assert "开始时间" in (result.reply or "")


def test_conductor_merges_event_clarification_time_reply_with_recent_topic() -> None:
    result = run_conductor(
        "下午1点开始，晚上10点结束",
        now=datetime(2026, 5, 12, 2, 58),
        history=[
            _message("user", "3个小时后提醒我去学校"),
            _message(
                "assistant",
                "我先把“去学校”理解成一个待安排日程。为了给你生成可确认的日程方案，还需要补充：开始时间或可选时间段，以及结束时间或预计持续多久。",
            ),
            _message("user", "下午1点开始，晚上10点结束"),
        ],
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["start_time"].startswith("2026-05-12T13:00:00")
    assert result.understanding.slots["end_time"].startswith("2026-05-12T22:00:00")
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_creation"
    assert proposal.options[0].actions[0]["payload"]["title"] == "去学校"


def test_conductor_keeps_timed_destination_reminder_as_event_when_llm_says_task() -> None:
    result = run_conductor(
        "3个小时后提醒我去学校",
        now=datetime(2026, 5, 12, 11, 5),
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_task",
                "goal_type": "task",
                "task_content": "个小时后去学校",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.8,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "create_event"
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["start_time"].startswith("2026-05-12T14:05:00")
    assert result.proposals[0].proposal_type == "event_creation"


def test_conductor_keeps_merged_event_followup_as_creation_when_llm_says_reschedule() -> None:
    result = run_conductor(
        "下午1点开始，晚上10点结束",
        now=datetime(2026, 5, 12, 2, 58),
        history=[
            _message("user", "3个小时后提醒我去学校"),
            _message(
                "assistant",
                "我先把“去学校”理解成一个待安排日程。为了给你生成可确认的日程方案，还需要补充：开始时间或可选时间段，以及结束时间或预计持续多久。",
            ),
            _message("user", "下午1点开始，晚上10点结束"),
        ],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "reschedule_event",
                "goal_type": "event",
                "missing_fields": ["target_event"],
                "ambiguities": ["target_event_not_found"],
                "confidence": 0.8,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "create_event"
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["start_time"].startswith("2026-05-12T13:00:00")
    assert result.understanding.slots["end_time"].startswith("2026-05-12T22:00:00")


def test_conductor_merges_create_event_directive_with_recent_clarification_slots() -> None:
    result = run_conductor(
        "创建独立日程",
        now=datetime(2026, 5, 12, 2, 58),
        history=[
            _message("user", "3个小时后提醒我去学校"),
            _message(
                "assistant",
                "我先把“去学校”理解成一个待安排日程。为了给你生成可确认的日程方案，还需要补充：开始时间或可选时间段，以及结束时间或预计持续多久。",
            ),
            _message("user", "下午1点开始，晚上10点结束"),
            _message("assistant", "我还没确定你想让我产出什么结果。"),
            _message("user", "创建独立日程"),
        ],
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["start_time"].startswith("2026-05-12T13:00:00")
    assert result.understanding.slots["end_time"].startswith("2026-05-12T22:00:00")


def test_conductor_treats_dated_destination_as_incomplete_event() -> None:
    result = run_conductor("下个月的一号去学校", now=datetime(2026, 5, 15, 9, 0))

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.intent == "create_event"
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["location_name"] == "学校"
    assert "start_time" in result.understanding.missing_fields
    assert "开始时间" in (result.reply or "")


def test_conductor_merges_event_followup_from_conversation_state() -> None:
    result = run_conductor(
        "下午1点开始",
        now=datetime(2026, 5, 15, 9, 0),
        external_context={
            "conversation_state": {
                "active_goal": {
                    "type": "create_event",
                    "status": "collecting_slots",
                    "known_slots": {
                        "title": "去学校",
                        "date": "2026-06-01",
                        "location_name": "学校",
                    },
                    "missing_fields": ["start_time"],
                    "source_message": "下个月的一号去学校",
                }
            }
        },
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["title"] == "去学校"
    assert result.understanding.slots["location_name"] == "学校"
    assert result.understanding.slots["start_time"].startswith("2026-06-01T13:00:00")
    proposal = result.proposals[0]
    assert proposal.options[0].actions[0]["payload"]["title"] == "去学校"
    assert proposal.options[0].actions[0]["payload"]["start_time"].startswith("2026-06-01T13:00:00")


def test_conductor_clarifies_generic_study_task() -> None:
    result = run_conductor(
        "帮我安排复习",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_task",
                "goal_type": "task",
                "task_content": "复习",
                "missing_fields": ["subject", "deadline_or_time_window", "rhythm"],
                "ambiguities": ["generic_study_task"],
                "confidence": 0.88,
            }
        ),
    )

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.goal_type == "task"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "create_task"
    assert result.understanding.orchestration.target_scope.kind == "task"
    assert result.understanding.orchestration.proposal_shape == "task_creation"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "科目" in (result.reply or "")
    assert "截止" in (result.reply or "")
    assert "可确认" in (result.reply or "")


def test_conductor_uses_orchestration_clarification_for_unknown_goal() -> None:
    result = run_conductor("给我一个普通建议")

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.goal_type == "unknown"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "unknown"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "产出什么结果" in (result.reply or "")
    assert "基于现有事项给你建议" in (result.reply or "")


def test_conductor_marks_schedule_guidance_as_answer_orchestration() -> None:
    result = run_conductor("明天把论文安排进去")

    assert result.decision == "legacy"
    assert result.understanding is not None
    assert result.understanding.goal_type == "schedule_guidance"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "answer"
    assert result.understanding.orchestration.user_goal == "schedule_guidance"


def test_conductor_clarifies_generic_review_arrangement_as_task() -> None:
    result = run_conductor("帮我安排一下复习")

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.goal_type == "task"
    assert result.understanding.intent == "create_task"
    assert result.understanding.slots["content"] == "复习"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.user_goal == "create_task"
    assert result.understanding.orchestration.proposal_shape == "task_creation"
    assert "复习的科目或具体内容" in (result.reply or "")


def test_conductor_overrides_llm_event_misread_for_generic_review_task() -> None:
    result = run_conductor(
        "帮我安排一下复习",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "复习",
                "location_name": None,
                "confidence": 0.91,
            }
        ),
    )

    assert result.decision == "clarification"
    assert result.understanding is not None
    assert result.understanding.goal_type == "task"
    assert result.understanding.intent == "create_task"
    assert result.understanding.slots["content"] == "复习"


def test_conductor_marks_progress_followup_as_answer_orchestration() -> None:
    result = run_conductor(
        "现在进展如何，接下来怎么安排",
        tasks=[
            SimpleNamespace(
                id=21,
                content="整理毕设论文",
                status="pending",
                completed_minutes=80,
                scheduled_minutes=120,
                remaining_minutes=160,
            )
        ],
    )

    assert result.decision == "legacy"
    assert result.understanding is not None
    assert result.understanding.goal_type == "progress_followup"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "answer"
    assert result.understanding.orchestration.user_goal == "progress_followup"
    assert result.understanding.orchestration.target_scope.kind == "task"


def test_conductor_marks_event_context_advice_as_answer_orchestration() -> None:
    result = run_conductor(
        "明天下午三点去图书馆开组会，我几点出发，要不要带伞",
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "event_context_advice",
                "goal_type": "event",
                "title": "开组会",
                "location_name": "图书馆",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.91,
            }
        ),
    )

    assert result.decision == "legacy"
    assert result.understanding is not None
    assert result.understanding.goal_type == "event_context_advice"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "answer"
    assert result.understanding.orchestration.user_goal == "event_context_advice"
    assert result.understanding.orchestration.target_scope.kind == "event"
    assert result.understanding.orchestration.target_scope.resolution == "resolved"


def test_conductor_proposes_reschedule_for_unique_event_target() -> None:
    result = run_conductor("把组会改到明天下午4点", events=[_event(12, "组会")])

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "proposal"
    assert result.understanding.orchestration.user_goal == "reschedule_event"
    assert result.understanding.orchestration.target_scope.kind == "event"
    assert result.understanding.orchestration.target_scope.event_id == 12
    assert result.understanding.orchestration.proposal_shape == "event_reschedule"
    assert result.metadata.get("proposal_reply_source") == "orchestration"
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
    assert "可确认的改期方案" in (result.reply or "")
    assert "确认后我才会改动原日程" in (result.reply or "")


def test_conductor_inherits_afternoon_context_for_bare_hour_reschedule_target() -> None:
    result = run_conductor("下午的见面改到4点", events=[_event(12, "下午的见面", hour=15)])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    action = proposal.options[0].actions[0]
    update = action["payload"]["update"]
    start_time = datetime.fromisoformat(update["start_time"])
    assert start_time.hour == 16
    assert start_time.date().isoformat() == "2026-05-03"
    assert "可确认的改期方案" in (result.reply or "")


def test_conductor_reschedules_event_with_gaiwei_wording() -> None:
    result = run_conductor("把约会时间改为8点", events=[_event(12, "约会", hour=18)])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 12
    update = proposal.options[0].actions[0]["payload"]["update"]
    start_time = datetime.fromisoformat(update["start_time"])
    assert start_time.hour == 20
    assert start_time.date().isoformat() == "2026-05-03"


def test_conductor_event_followup_inherits_previous_next_month_date() -> None:
    result = run_conductor(
        "下午1点开始",
        history=[
            _message("user", "下个月的一号去学校"),
            _message("assistant", "这个日程还缺少开始时间。"),
        ],
        now=datetime(2026, 5, 15, 9, 0),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_creation"
    action = proposal.options[0].actions[0]
    payload = action["payload"]
    assert payload["title"] == "去学校"
    assert payload["location_name"] == "学校"
    assert datetime.fromisoformat(payload["start_time"]) == datetime(2026, 6, 1, 13, 0)


def test_conductor_treats_timed_dating_as_event_without_fake_location() -> None:
    result = run_conductor("明天晚上6点去约会", now=datetime(2026, 5, 15, 9, 0))

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_creation"
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] in {"约会", "去约会"}
    assert payload["start_time"].startswith("2026-05-16T18:00:00")
    assert payload.get("location_name") in {None, ""}


def test_conductor_does_not_merge_independent_timed_dating_with_previous_school_request() -> None:
    result = run_conductor(
        "明天晚上6点去约会",
        history=[
            _message("user", "下个月的一号去学校"),
            _message("assistant", "这个日程还缺少开始时间。"),
            _message("user", "下午1点开始"),
            _message("assistant", "P1：建议创建日程“去学校”：06-01 13:00-14:00。"),
        ],
        now=datetime(2026, 5, 15, 9, 0),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] in {"约会", "去约会"}
    assert payload["start_time"].startswith("2026-05-16T18:00:00")
    assert payload.get("location_name") in {None, ""}


def test_conductor_does_not_merge_independent_timed_study_with_previous_library_request() -> None:
    result = run_conductor(
        "后天晚上8点复习英语",
        history=[
            _message("user", "明天下午3点去图书馆自习"),
            _message("assistant", "P1：建议创建日程“去图书馆自习”：05-16 15:00-16:00，地点：图书馆。"),
        ],
        now=datetime(2026, 5, 15, 9, 0),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    payload = proposal.options[0].actions[0]["payload"]
    assert payload["title"] == "复习英语"
    assert payload["start_time"].startswith("2026-05-17T20:00:00")
    assert payload.get("location_name") in {None, ""}


def test_conductor_protects_timed_dating_when_llm_misreads_as_reschedule() -> None:
    result = run_conductor(
        "明天晚上6点去约会",
        now=datetime(2026, 5, 15, 9, 0),
        external_context={"active_target": {"proposal_id": 101, "proposal_type": "event_creation"}},
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "reschedule_event",
                "goal_type": "event",
                "missing_fields": ["target_event"],
                "ambiguities": ["target_event_not_found"],
                "confidence": 0.88,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "create_event"
    payload = result.proposals[0].options[0].actions[0]["payload"]
    assert payload["title"] in {"约会", "去约会"}
    assert payload["start_time"].startswith("2026-05-16T18:00:00")
    assert payload.get("location_name") in {None, ""}


def test_conductor_treats_explicit_schedule_word_with_ri_cheng_as_event_not_task_schedule() -> None:
    result = run_conductor(
        "请帮我安排真实逐条日程03，时间是5月23号下午11点到12点，地点真实地点3",
        now=datetime(2026, 5, 15, 9, 0),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_creation"
    payload = proposal.options[0].actions[0]["payload"]
    assert "真实逐条日程03" in payload["title"]
    assert payload["location_name"] == "真实地点3"
    assert payload["start_time"].startswith("2026-05-23T23:00:00")


def test_conductor_reschedules_exact_numbered_event_title_with_location_update() -> None:
    result = run_conductor(
        "把生产级批量日程10改到5月30号晚上7点到8点，地点改到新测试地点",
        events=[
            _event_window(
                10,
                "生产级批量日程10",
                datetime(2026, 5, 30, 17, 0),
                datetime(2026, 5, 30, 18, 0),
                location_name="测试地点5",
            ),
            _event_window(
                11,
                "生产级批量日程11",
                datetime(2026, 5, 30, 18, 0),
                datetime(2026, 5, 30, 19, 0),
                location_name="测试地点5",
            ),
        ],
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.slots["target_id"] == 10
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 10
    assert "生产级批量日程10" in proposal.summary
    assert "生产级批量日程11" not in proposal.summary
    action = proposal.options[0].actions[0]
    assert action["type"] == "reschedule_event"
    assert action["payload"]["event_id"] == 10
    update = action["payload"]["update"]
    assert datetime.fromisoformat(update["start_time"]) == datetime(2026, 5, 30, 19, 0)
    assert datetime.fromisoformat(update["end_time"]) == datetime(2026, 5, 30, 20, 0)
    assert update["location_name"] == "新测试地点"


def test_conductor_reschedule_destination_date_does_not_hide_exact_title_target() -> None:
    result = run_conductor(
        "把真实逐条日程10改到6月20号16:00到17:00，地点改到最终测试地点A",
        events=[
            _event_window(
                10,
                "处理真实逐条日程10",
                datetime(2026, 5, 30, 9, 0),
                datetime(2026, 5, 30, 10, 0),
                location_name="真实地点3",
            ),
            _event_window(
                51,
                "参加真实逐条日程51",
                datetime(2026, 6, 20, 10, 0),
                datetime(2026, 6, 20, 11, 0),
                location_name="真实地点2",
            ),
            _event_window(
                52,
                "真实逐条日程52",
                datetime(2026, 6, 20, 11, 0),
                datetime(2026, 6, 20, 12, 0),
                location_name="真实地点3",
            ),
        ],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 10
    action = proposal.options[0].actions[0]
    assert action["payload"]["event_id"] == 10
    update = action["payload"]["update"]
    assert update["start_time"].startswith("2026-06-20T16:00:00")
    assert update["location_name"] == "最终测试地点A"


def test_conductor_protects_reschedule_when_llm_misreads_numbered_update_as_creation() -> None:
    result = run_conductor(
        "把生产级批量日程10改到5月30号晚上7点到8点，地点改到新测试地点",
        events=[
            _event_window(
                10,
                "生产级批量日程10",
                datetime(2026, 5, 30, 17, 0),
                datetime(2026, 5, 30, 18, 0),
                location_name="测试地点5",
            )
        ],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "生产级批量日程10",
                "start_time": "2026-05-30T19:00:00",
                "end_time": "2026-05-30T20:00:00",
                "location_name": "新测试地点",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.95,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "reschedule_event"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 10
    action = proposal.options[0].actions[0]
    assert action["type"] == "reschedule_event"
    assert action["payload"]["event_id"] == 10


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
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "cancel_event"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "取消日程请求" in (result.reply or "")
    assert "要操作的具体日程" in (result.reply or "")
    assert "项目组会" in (result.reply or "")


def test_conductor_uses_orchestration_clarification_for_missing_event_update_target() -> None:
    result = run_conductor("取消不存在的会议", events=[_event(12, "项目组会", hour=9)])

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "cancel_event"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "取消日程请求" in (result.reply or "")
    assert "要操作的具体日程" in (result.reply or "")


def test_conductor_uses_orchestration_clarification_for_reschedule_missing_time() -> None:
    result = run_conductor("把组会改到明天", events=[_event(12, "组会", hour=9)])

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "reschedule_event"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "改期日程请求" in (result.reply or "")
    assert "新的日期和具体时间" in (result.reply or "")


def test_conductor_proposes_cancel_for_unique_event_target() -> None:
    result = run_conductor("取消政治课", events=[_event(14, "政治课")])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_cancel"
    action = proposal.options[0].actions[0]
    assert action == {"type": "cancel_event", "payload": {"event_id": 14}}


def test_conductor_uses_date_reference_to_cancel_unique_focus_block() -> None:
    result = run_conductor(
        "明天那个复习块不做了",
        events=[
            _event(31, "英语复习（第1/3段）", hour=15, day=3, linked_task_id=7, event_type="focus_block"),
            _event(32, "英语复习（第2/3段）", hour=15, day=4, linked_task_id=7, event_type="focus_block"),
            _event(33, "英语复习（第3/3段）", hour=15, day=5, linked_task_id=7, event_type="focus_block"),
        ],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_cancel"
    assert proposal.related_event_id == 31
    assert proposal.related_task_id == 7
    assert proposal.payload_json["requires_reschedule_choice"] is True
    assert [option.option_id for option in proposal.options] == ["A", "B"]
    assert "跳过" in proposal.options[0].title
    assert "补排" in proposal.options[1].title
    assert proposal.options[0].actions[0] == {"type": "cancel_event", "payload": {"event_id": 31}}
    assert not any(
        action["type"] == "mark_task_completed"
        for option in proposal.options
        for action in option.actions
    )


def test_conductor_proposes_batch_cancel_for_date_events() -> None:
    result = run_conductor(
        "取消明天所有日程",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
            _event(14, "后天复盘", day=4),
        ],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_batch_cancel"
    assert proposal.related_event_id is None
    assert proposal.payload_json["target_scope"] == "batch"
    assert proposal.payload_json["target_date"] == "2026-05-03"
    actions = proposal.options[0].actions
    assert actions == [
        {"type": "cancel_event", "payload": {"event_id": 12}},
        {"type": "cancel_event", "payload": {"event_id": 13}},
    ]
    assert "2 个日程" in proposal.summary


def test_conductor_blocks_oversized_batch_cancel_with_range_warning() -> None:
    result = run_conductor(
        "把明天所有安排都取消",
        events=[_event(100 + index, f"测试日程{index}", hour=8 + index) for index in range(9)],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert "batch_event_target_too_large" in result.understanding.ambiguities
    assert "范围过大" in (result.reply or "")
    assert "不会执行任何取消或改期" in (result.reply or "")


def test_conductor_clarifies_batch_cancel_without_date() -> None:
    result = run_conductor(
        "取消所有日程",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "cancel_events_batch"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "批量取消请求" in (result.reply or "")
    assert "日期或日期范围" in (result.reply or "")


def test_conductor_clarifies_batch_cancel_when_target_too_large() -> None:
    result = run_conductor(
        "把明天所有安排都取消",
        events=[_event(event_id, f"测试日程{event_id}", hour=8 + event_id % 10) for event_id in range(10, 19)],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert "batch_event_target_too_large" in result.understanding.ambiguities
    assert "范围过大" in (result.reply or "")
    assert "不会执行任何取消或改期" in (result.reply or "")


def test_conductor_proposes_batch_reschedule_shift_for_date_events() -> None:
    result = run_conductor(
        "把明天所有日程推迟一天",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
            _event(14, "后天复盘", day=4),
        ],
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "proposal"
    assert result.understanding.orchestration.user_goal == "reschedule_events_batch"
    assert result.understanding.orchestration.target_scope.kind == "batch_events"
    assert result.understanding.orchestration.target_scope.event_ids == [12, 13]
    assert result.understanding.orchestration.proposal_shape == "event_batch_reschedule"
    assert result.metadata.get("proposal_reply_source") == "orchestration"
    assert "批量改期方案" in (result.reply or "")
    assert "确认前不会修改日程" in (result.reply or "")
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_batch_reschedule"
    assert proposal.payload_json["batch_shift_days"] == 1
    actions = proposal.options[0].actions
    assert [action["type"] for action in actions] == ["reschedule_event", "reschedule_event"]
    first_update = actions[0]["payload"]["update"]
    second_update = actions[1]["payload"]["update"]
    assert datetime.fromisoformat(first_update["start_time"]) == datetime(2026, 5, 4, 9, 0)
    assert datetime.fromisoformat(first_update["end_time"]) == datetime(2026, 5, 4, 10, 30)
    assert datetime.fromisoformat(second_update["start_time"]) == datetime(2026, 5, 4, 15, 0)
    assert datetime.fromisoformat(second_update["end_time"]) == datetime(2026, 5, 4, 16, 30)


def test_conductor_protects_batch_reschedule_when_llm_misreads_as_event_creation() -> None:
    result = run_conductor(
        "把明天所有日程都推迟一天",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "推迟一天",
                "location_name": None,
                "confidence": 0.91,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "reschedule_event"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.user_goal == "reschedule_events_batch"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_batch_reschedule"
    assert proposal.payload_json["batch_shift_days"] == 1


def test_conductor_proposes_batch_reschedule_to_destination_date() -> None:
    result = run_conductor(
        "把明天所有日程改到后天",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_batch_reschedule"
    assert proposal.payload_json["target_date"] == "2026-05-03"
    assert proposal.payload_json["batch_destination_date"] == "2026-05-04"
    assert "改到 2026-05-04" in proposal.summary
    actions = proposal.options[0].actions
    first_update = actions[0]["payload"]["update"]
    second_update = actions[1]["payload"]["update"]
    assert datetime.fromisoformat(first_update["start_time"]) == datetime(2026, 5, 4, 9, 0)
    assert datetime.fromisoformat(first_update["end_time"]) == datetime(2026, 5, 4, 10, 30)
    assert datetime.fromisoformat(second_update["start_time"]) == datetime(2026, 5, 4, 15, 0)
    assert datetime.fromisoformat(second_update["end_time"]) == datetime(2026, 5, 4, 16, 30)


def test_conductor_proposes_batch_reschedule_to_destination_date_with_push_wording() -> None:
    result = run_conductor(
        "把今天所有的日程全部推到明天",
        events=[
            _event(12, "项目组会", hour=9, day=2),
            _event(13, "论文组会", hour=15, day=2),
            _event(14, "后天复盘", day=4),
        ],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_batch_reschedule"
    assert proposal.payload_json["target_date"] == "2026-05-02"
    assert proposal.payload_json["batch_destination_date"] == "2026-05-03"
    actions = proposal.options[0].actions
    assert datetime.fromisoformat(actions[0]["payload"]["update"]["start_time"]) == datetime(2026, 5, 3, 9, 0)
    assert datetime.fromisoformat(actions[1]["payload"]["update"]["start_time"]) == datetime(2026, 5, 3, 15, 0)


def test_conductor_clarifies_batch_reschedule_without_shift_or_destination() -> None:
    result = run_conductor(
        "把明天所有日程改一下",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "reschedule_events_batch"
    assert result.understanding.orchestration.target_scope.kind == "batch_events"
    assert result.understanding.orchestration.target_scope.resolution == "resolved"
    assert "batch_shift_days" in result.understanding.orchestration.missing_information
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "批量改期请求" in (result.reply or "")
    assert "整体移动规则" in (result.reply or "")


def test_conductor_clarifies_batch_reschedule_destination_without_source_date() -> None:
    result = run_conductor(
        "把所有日程改到后天",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
            _event(14, "后天复盘", day=4),
        ],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "reschedule_events_batch"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "批量改期请求" in (result.reply or "")
    assert "日期或日期范围" in (result.reply or "")


def test_conductor_proposes_task_completion_for_unique_task_target() -> None:
    result = run_conductor("整理毕设论文任务完成了", tasks=[_task(21, "整理毕设论文")])

    assert result.decision == "proposal"
    assert result.metadata.get("proposal_reply_source") == "orchestration"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 21
    action = proposal.options[0].actions[0]
    assert action == {"type": "mark_task_completed", "payload": {"task_id": 21}}
    assert "任务状态更新方案" in (result.reply or "")
    assert "确认前不会修改任务" in (result.reply or "")


def test_conductor_treats_task_subject_completion_as_task_update() -> None:
    result = run_conductor(
        "论文这三天的写作都完成了",
        tasks=[_task(21, "整理毕设论文")],
        events=[
            _event(31, "整理毕设论文（第1/3段）", hour=15, linked_task_id=21),
            _event(32, "整理毕设论文（第2/3段）", hour=15, day=4, linked_task_id=21),
            _event(33, "整理毕设论文（第3/3段）", hour=15, day=5, linked_task_id=21),
        ],
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "mark_task_completed"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 21
    assert proposal.options[0].actions[:3] == [
        {"type": "mark_event_completed", "payload": {"event_id": 31}},
        {"type": "mark_event_completed", "payload": {"event_id": 32}},
        {"type": "mark_event_completed", "payload": {"event_id": 33}},
    ]
    assert proposal.options[0].actions[3] == {"type": "mark_task_completed", "payload": {"task_id": 21}}


def test_conductor_protects_task_completion_when_semantic_extractor_misreads_progress() -> None:
    result = run_conductor(
        "论文这三天的写作都完成了",
        tasks=[_task(21, "整理毕设论文")],
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "progress_followup",
                "goal_type": "progress_followup",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.7,
            }
        ),
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "mark_task_completed"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 21
    assert proposal.options[0].actions[0] == {"type": "mark_task_completed", "payload": {"task_id": 21}}


def test_conductor_uses_orchestration_clarification_for_missing_task_update_target() -> None:
    result = run_conductor("不存在的任务完成了", tasks=[_task(21, "整理毕设论文")])

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "complete_task"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "完成任务请求" in (result.reply or "")
    assert "要操作的具体任务" in (result.reply or "")


def test_conductor_resolves_pronoun_from_recent_history_for_event_update() -> None:
    result = run_conductor(
        "把这个改到明天下午4点",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
        history=[_message("assistant", "P1：建议把日程“论文组会”改到明天上午。")],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 13
    assert proposal.options[0].actions[0]["payload"]["event_id"] == 13


def test_conductor_resolves_pronoun_from_active_target_for_event_update() -> None:
    result = run_conductor(
        "把这个改到明天下午4点",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
        external_context={"active_target": {"event_id": 13, "proposal_id": 101}},
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "event_reschedule"
    assert proposal.related_event_id == 13
    assert proposal.options[0].actions[0]["payload"]["event_id"] == 13


def test_conductor_clarifies_pronoun_without_unique_context() -> None:
    result = run_conductor(
        "把这个改到明天下午4点",
        events=[
            _event(12, "项目组会", hour=9),
            _event(13, "论文组会", hour=15),
        ],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "改期日程请求" in (result.reply or "")
    assert "要操作的具体日程" in (result.reply or "")
    assert "项目组会" in (result.reply or "")


def test_conductor_resolves_pronoun_from_recent_history_for_task_completion() -> None:
    result = run_conductor(
        "这个任务完成了",
        tasks=[
            _task(21, "整理毕设论文"),
            _task(22, "准备答辩材料"),
        ],
        history=[_message("assistant", "我正在跟进任务“准备答辩材料”。")],
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 22


def test_conductor_uses_orchestration_clarification_for_task_schedule_missing_target_and_time() -> None:
    result = run_conductor(
        "继续规划这个任务",
        tasks=[_task(21, "整理毕设论文"), _task(22, "准备答辩")],
    )

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "schedule_blocks"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "继续规划任务请求" in (result.reply or "")
    assert "要继续规划的具体任务" in (result.reply or "")
    assert "整理毕设论文" in (result.reply or "")


def test_conductor_uses_orchestration_clarification_for_task_schedule_missing_time() -> None:
    result = run_conductor("继续规划整理毕设论文", tasks=[_task(21, "整理毕设论文")])

    assert result.decision == "clarification"
    assert result.proposals == []
    assert result.understanding is not None
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.conversation_mode == "clarification"
    assert result.understanding.orchestration.user_goal == "schedule_blocks"
    assert result.metadata.get("clarification_source") == "orchestration"
    assert "继续规划任务请求" in (result.reply or "")
    assert "希望安排到哪天" in (result.reply or "")


def test_conductor_builds_task_schedule_plan_for_task_continuation_request() -> None:
    result = run_conductor(
        "我预计3天整理完成，帮我安排下下午3点到5点",
        tasks=[_task(21, "整理毕设论文")],
        history=[_message("assistant", "我先建议先创建任务“整理毕设论文”，后续再继续规划。")],
        external_context={"active_target": {"task_id": 21, "kind": "task"}},
    )

    assert result.decision == "proposal"
    assert result.understanding is not None
    assert result.understanding.intent == "plan_task_schedule"
    assert result.understanding.orchestration is not None
    assert result.understanding.orchestration.user_goal == "schedule_blocks"
    assert result.understanding.orchestration.target_scope.task_id == 21
    assert result.metadata.get("proposal_reply_source") == "orchestration"
    assert "任务排程方案" in (result.reply or "")
    assert "确认后我才会创建这些专注时段" in (result.reply or "")
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_schedule_plan"
    assert proposal.related_task_id == 21
    actions = proposal.options[0].actions
    assert len(actions) == 3
    assert all(action["type"] == "create_event" for action in actions)
    assert all(action["payload"]["linked_task_id"] == 21 for action in actions)
    assert actions[0]["payload"]["title"] == "整理毕设论文（第1/3段）"
    assert datetime.fromisoformat(actions[0]["payload"]["start_time"]) == datetime(2026, 5, 2, 15, 0)
    assert datetime.fromisoformat(actions[1]["payload"]["start_time"]) == datetime(2026, 5, 3, 15, 0)
    assert datetime.fromisoformat(actions[2]["payload"]["start_time"]) == datetime(2026, 5, 4, 15, 0)


def test_conductor_rolls_task_schedule_bare_time_forward_when_today_slot_has_passed() -> None:
    result = run_conductor(
        "把整理毕设论文安排到未来三天下午3点到5点",
        tasks=[_task(21, "整理毕设论文")],
        now=datetime(2026, 5, 11, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_schedule_plan"
    actions = proposal.options[0].actions
    assert len(actions) == 3
    assert all(action["payload"]["linked_task_id"] == 21 for action in actions)
    assert datetime.fromisoformat(actions[0]["payload"]["start_time"]) == datetime(2026, 5, 12, 15, 0)
    assert datetime.fromisoformat(actions[1]["payload"]["start_time"]) == datetime(2026, 5, 13, 15, 0)
    assert datetime.fromisoformat(actions[2]["payload"]["start_time"]) == datetime(2026, 5, 14, 15, 0)


def test_assistant_service_runs_conductor_shadow_without_persistence() -> None:
    service = AssistantService()
    service.settings.assistant_conductor_mode = "shadow"
    service.conductor = AssistantConductor.build_default(
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "和同学见面",
                "location_name": "学校",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.93,
            }
        )
    )

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
    service.conductor = AssistantConductor.build_default(
        semantic_extractor=StaticUnderstandingExtractor(
            {
                "intent": "create_event",
                "goal_type": "event",
                "title": "和同学见面",
                "location_name": "学校",
                "missing_fields": [],
                "ambiguities": [],
                "confidence": 0.93,
            }
        )
    )
    persisted_payloads = []
    active_target_payloads = []

    class FakeProposalManager:
        async def create_proposal(self, *, user_id, payload):
            persisted_payloads.append((user_id, payload))
            return SimpleNamespace(
                id=101,
                session_id=payload.session_id,
                status="pending",
                proposal_type=payload.proposal_type,
                summary=payload.summary,
                related_event_id=payload.related_event_id,
                related_task_id=payload.related_task_id,
                payload_json=payload.payload_json,
            )

    class FakeThreadStateRepository:
        async def get_active_target_state(self, *, user_id, session_id):
            return None

        async def upsert_active_target_state(self, *, user_id, session_id, payload):
            active_target_payloads.append((user_id, session_id, payload))
            return SimpleNamespace(id=303, **payload)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

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
    assert active_target_payloads
    _target_user_id, target_session_id, target_payload = active_target_payloads[0]
    assert target_session_id == 1
    assert target_payload["active_proposal_id"] == 101
    assert target_payload["state_json"]["active_target"]["proposal_id"] == 101


def test_assistant_service_persists_and_injects_event_conversation_state() -> None:
    service = AssistantService()
    service.settings.assistant_conductor_mode = "proposal"
    active_target_payloads = []

    class FakeThreadStateRepository:
        state = None

        async def get_active_target_state(self, *, user_id, session_id):
            return self.state

        async def upsert_active_target_state(self, *, user_id, session_id, payload):
            active_target_payloads.append((user_id, session_id, payload))
            self.state = SimpleNamespace(id=404, updated_at=datetime(2026, 5, 15, 9, 0), **payload)
            return self.state

    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
    result = run_conductor("下个月的一号去学校", now=datetime(2026, 5, 15, 9, 0))

    asyncio.run(
        service._persist_conversation_state_from_conductor(
            user_id="demo-user",
            session_id=1,
            result=result,
            user_message="下个月的一号去学校",
            external_context={},
        )
    )

    assert active_target_payloads
    payload = active_target_payloads[-1][2]
    state_json = payload["state_json"]
    conversation_state = state_json["conversation_state"]
    active_goal = conversation_state["active_goal"]
    assert active_goal["type"] == "create_event"
    assert active_goal["status"] == "collecting_slots"
    assert active_goal["known_slots"]["title"] == "去学校"
    assert active_goal["known_slots"]["location_name"] == "学校"
    assert active_goal["known_slots"]["date"] == "2026-06-01"
    assert "start_time" in active_goal["missing_fields"]

    enriched = asyncio.run(
        service._with_active_target_context(
            user_id="demo-user",
            session_id=1,
            external_context={},
        )
    )

    assert enriched["conversation_state"]["active_goal"]["known_slots"]["title"] == "去学校"


def test_assistant_service_confirms_active_proposal_from_text() -> None:
    service = AssistantService()
    confirmed_calls = []

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(
                    id=101,
                    session_id=1,
                    status="pending",
                    proposal_type="event_creation",
                    summary="建议创建日程",
                    recommended_option_id="A",
                    related_event_id=None,
                    related_task_id=None,
                    payload_json={"options": [{"option_id": "A", "actions": []}]},
                )
            ]

        async def get_proposal(self, *, user_id, proposal_id):
            return SimpleNamespace(
                id=proposal_id,
                session_id=1,
                status="pending",
                proposal_type="event_creation",
                summary="建议创建日程",
                recommended_option_id="A",
                related_event_id=None,
                related_task_id=None,
                payload_json={"options": [{"option_id": "A", "actions": []}]},
            )

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirmed_calls.append((user_id, proposal_id, option_id))
            return SimpleNamespace(
                id=proposal_id,
                session_id=1,
                status="executed",
                proposal_type="event_creation",
                summary="建议创建日程",
                related_event_id=42,
                related_task_id=None,
                payload_json={"execution": {"result": {"related_event_id": 42}}},
            )

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, **_kwargs):
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_confirm_active_proposal_from_text(
            user_id="demo-user",
            session_id=1,
            user_message="就按这个",
            external_context={"active_target": {"proposal_id": 101}},
        )
    )

    assert reply == "已按这个方案确认并执行。"
    assert confirmed_calls == [("demo-user", 101, "A")]


def test_assistant_service_confirms_active_proposal_from_short_affirmation() -> None:
    service = AssistantService()
    confirmed_calls = []

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(
                    id=101,
                    session_id=1,
                    status="pending",
                    proposal_type="event_creation",
                    summary="建议创建日程",
                    recommended_option_id="A",
                    related_event_id=None,
                    related_task_id=None,
                    payload_json={"options": [{"option_id": "A", "actions": []}]},
                )
            ]

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirmed_calls.append((user_id, proposal_id, option_id))
            return SimpleNamespace(
                id=proposal_id,
                session_id=1,
                status="executed",
                proposal_type="event_creation",
                summary="建议创建日程",
                related_event_id=42,
                related_task_id=None,
                payload_json={"execution": {"result": {"related_event_id": 42}}},
            )

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, **_kwargs):
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_confirm_active_proposal_from_text(
            user_id="demo-user",
            session_id=1,
            user_message="同意",
            external_context={"active_target": {"proposal_id": 101}},
        )
    )

    assert reply == "已按这个方案确认并执行。"
    assert confirmed_calls == [("demo-user", 101, "A")]


def test_assistant_service_reports_execution_failure_after_text_confirmation() -> None:
    service = AssistantService()

    class FakeProposalManager:
        failed = SimpleNamespace(
            id=101,
            session_id=1,
            status="execution_failed",
            proposal_type="event_reschedule",
            summary="建议调整日程",
            execution_error="event not found",
            related_event_id=999,
            related_task_id=None,
            payload_json={"execution": {"status": "failed", "error": "event not found"}},
        )

        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(
                    id=101,
                    session_id=1,
                    status="pending",
                    proposal_type="event_reschedule",
                    summary="建议调整日程",
                    recommended_option_id="A",
                    related_event_id=999,
                    related_task_id=None,
                    payload_json={"options": [{"option_id": "A", "actions": []}]},
                )
            ]

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            raise HTTPException(status_code=404, detail="event not found")

        async def get_proposal(self, *, user_id, proposal_id):
            return self.failed

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, **_kwargs):
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="按方案A安排",
            external_context={},
        )
    )

    assert reply is not None
    assert "执行失败" in reply
    assert "重试入口" in reply
    assert "已按这个方案确认并执行" not in reply


def test_assistant_service_repeated_confirmation_reports_failed_active_proposal() -> None:
    service = AssistantService()

    failed_proposal = SimpleNamespace(
        id=101,
        session_id=1,
        status="execution_failed",
        proposal_type="event_reschedule",
        summary="建议调整日程",
        recommended_option_id="A",
        execution_error="event not found",
        related_event_id=999,
        related_task_id=None,
        payload_json={"execution": {"status": "failed", "last_error": "event not found"}},
    )

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return []

        async def get_proposal(self, *, user_id, proposal_id):
            return failed_proposal

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="按方案A安排",
            external_context={"active_target": {"proposal_id": 101}},
        )
    )

    assert reply is not None
    assert "执行失败" in reply
    assert "没有待确认方案" not in reply


def test_assistant_service_rejects_expired_proposal_confirmation() -> None:
    service = AssistantService()
    confirm_calls: list[int] = []

    expired_proposal = SimpleNamespace(
        id=101,
        session_id=1,
        status="expired",
        proposal_type="event_creation",
        summary="过期方案",
        recommended_option_id="A",
        related_event_id=None,
        related_task_id=None,
        payload_json={"protocol_label": "P1", "options": [{"option_id": "A", "actions": []}]},
    )

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            if statuses == ["pending"]:
                return []
            return [expired_proposal]

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirm_calls.append(proposal_id)
            return expired_proposal

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="按方案A安排",
            external_context={},
        )
    )

    assert reply is not None
    assert "已经过期" in reply
    assert "不会写入" in reply
    assert confirm_calls == []


def test_assistant_service_rejects_superseded_label_without_confirming_replacement() -> None:
    service = AssistantService()
    confirm_calls: list[int] = []

    pending_replacement = SimpleNamespace(
        id=102,
        session_id=1,
        status="pending",
        proposal_type="event_creation",
        summary="新方案",
        recommended_option_id="A",
        related_event_id=None,
        related_task_id=None,
        payload_json={"protocol_label": "P2", "options": [{"option_id": "A", "actions": []}]},
    )
    superseded_proposal = SimpleNamespace(
        id=101,
        session_id=1,
        status="superseded",
        proposal_type="event_creation",
        summary="旧方案",
        recommended_option_id="A",
        related_event_id=None,
        related_task_id=None,
        payload_json={"protocol_label": "P1", "options": [{"option_id": "A", "actions": []}]},
    )

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            if statuses == ["pending"]:
                return [pending_replacement]
            return [superseded_proposal]

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirm_calls.append(proposal_id)
            return pending_replacement

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="P1 按方案A安排",
            external_context={},
        )
    )

    assert reply is not None
    assert "已经被新的方案替代" in reply
    assert confirm_calls == []


def test_assistant_service_reports_invalid_option_without_executing_proposal() -> None:
    service = AssistantService()
    confirm_calls: list[tuple[int, str]] = []

    proposal = SimpleNamespace(
        id=101,
        session_id=1,
        status="pending",
        proposal_type="event_creation",
        summary="待确认方案",
        recommended_option_id="A",
        related_event_id=None,
        related_task_id=None,
        payload_json={"protocol_label": "P1", "options": [{"option_id": "A"}, {"option_id": "B"}]},
    )

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [proposal] if statuses == ["pending"] else []

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirm_calls.append((proposal_id, option_id))
            raise HTTPException(status_code=400, detail="option not found")

        async def get_proposal(self, *, user_id, proposal_id):
            return proposal

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="P1 按方案C安排",
            external_context={},
        )
    )

    assert reply is not None
    assert "没有方案 C" in reply
    assert confirm_calls == [(101, "C")]


def test_assistant_service_confirms_explicit_p_number_from_text() -> None:
    service = AssistantService()
    confirmed_calls = []

    proposals = [
        SimpleNamespace(
            id=101,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="方案一",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={"options": [{"option_id": "A", "actions": []}]},
        ),
        SimpleNamespace(
            id=102,
            session_id=1,
            status="pending",
            proposal_type="event_cancel",
            summary="方案二",
            recommended_option_id="B",
            related_event_id=12,
            related_task_id=None,
            payload_json={"options": [{"option_id": "B", "actions": []}]},
        ),
    ]

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return list(proposals)

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirmed_calls.append((user_id, proposal_id, option_id))
            proposal = next(item for item in proposals if item.id == proposal_id)
            return SimpleNamespace(**{**proposal.__dict__, "status": "executed"})

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, **_kwargs):
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="按P2",
            external_context={},
        )
    )

    assert reply == "已按这个方案确认并执行。"
    assert confirmed_calls == [("demo-user", 102, "B")]


def test_assistant_service_clarifies_ambiguous_proposal_protocol() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(id=101, session_id=1, status="pending", payload_json={}),
                SimpleNamespace(id=102, session_id=1, status="pending", payload_json={}),
            ]

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="就按这个",
            external_context={},
        )
    )

    assert reply is not None
    assert "P1" in reply
    assert "P2" in reply


def test_assistant_service_does_not_use_active_target_when_multiple_pending_proposals() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(id=101, session_id=1, status="pending", payload_json={}),
                SimpleNamespace(id=102, session_id=1, status="pending", payload_json={}),
            ]

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="可以",
            external_context={"active_target": {"proposal_id": 102}},
        )
    )

    assert reply is not None
    assert "P1" in reply
    assert "P2" in reply


def test_assistant_service_reports_missing_pending_proposal_for_confirm_text() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return []

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="同意",
            external_context={},
        )
    )

    assert reply == "我知道你是在确认现有方案，但当前没有待确认方案可执行；如果你是在重复确认刚刚已执行的方案，它已经执行完成，不会重复写入。需要新安排的话，请直接告诉我要安排什么。"


def test_assistant_service_reports_executed_active_proposal_as_idempotent() -> None:
    service = AssistantService()
    confirmed_calls: list[int] = []

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return []

        async def get_proposal(self, *, user_id, proposal_id):
            return SimpleNamespace(
                id=proposal_id,
                session_id=1,
                status="executed",
                recommended_option_id="A",
                payload_json={"options": [{"option_id": "A"}]},
            )

        async def confirm_proposal(self, *, user_id, proposal_id, option_id):
            confirmed_calls.append(proposal_id)
            return SimpleNamespace(id=proposal_id, session_id=1, status="executed")

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="可以",
            external_context={"active_target": {"proposal_id": 101}},
        )
    )

    assert reply == "这个方案已经执行完成，不会重复写入。需要新安排的话，请直接告诉我要安排什么。"
    assert confirmed_calls == []


def test_assistant_service_reports_missing_pending_proposal_for_revise_text() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return []

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="把这个方案改到明天下午四点",
            external_context={},
        )
    )

    assert reply == "我知道你是在修改现有方案，但当前没有可修改的待确认方案。请先让我给你出一个方案，或者明确指出要修改哪条历史方案。"


def test_assistant_service_does_not_revise_event_cancel_for_standalone_reschedule_text() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(
                    id=101,
                    session_id=1,
                    status="pending",
                    proposal_type="event_cancel",
                    summary="建议取消日程“去学校开会”",
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "actions": [{"type": "cancel_event", "payload": {"event_id": 1}}],
                            }
                        ]
                    },
                )
            ]

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="下午的见面改到4点",
            external_context={"active_target": {"proposal_id": 101}},
        )
    )

    assert reply is None


def test_assistant_service_skips_proposal_protocol_for_explicit_event_reschedule_text() -> None:
    service = AssistantService()

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [
                SimpleNamespace(
                    id=101,
                    session_id=1,
                    status="pending",
                    proposal_type="event_creation",
                    summary="建议创建日程“去学校办手续”",
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "actions": [{"type": "create_event", "payload": {"title": "去学校办手续"}}],
                            }
                        ]
                    },
                ),
                SimpleNamespace(
                    id=102,
                    session_id=1,
                    status="pending",
                    proposal_type="deadline_recovery",
                    summary="任务「毕设论文」临近截止，需要协商安排。",
                    payload_json={"options": [{"option_id": "A", "actions": []}]},
                ),
            ]

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="下午的见面改到4点",
            external_context={"events": [SimpleNamespace(id=12, title="下午见面")]},
        )
    )

    assert reply is None


def test_assistant_service_builds_orchestration_for_proposal_confirm_text() -> None:
    service = AssistantService()

    proposal = SimpleNamespace(id=101, summary="建议创建日程")
    assessment = service._build_proposal_protocol_assessment(
        user_message="就按这个",
        intent="confirm",
        proposal=proposal,
        external_context={"active_target": {"proposal_id": 101}},
    )

    assert assessment.conversation_mode == "confirm_existing"
    assert assessment.user_goal == "confirm_existing_proposal"
    assert assessment.target_scope.kind == "proposal"
    assert assessment.target_scope.resolution == "resolved"
    assert assessment.target_scope.proposal_id == 101
    assert assessment.continuation.based_on_active_target is True


def test_assistant_service_revises_explicit_p_number_from_text() -> None:
    service = AssistantService()
    revised_calls = []
    persisted_targets = []

    proposals = [
        SimpleNamespace(
            id=101,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="方案一",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={"options": [{"option_id": "A", "actions": []}]},
        ),
        SimpleNamespace(
            id=102,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="方案二",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={"options": [{"option_id": "A", "actions": []}]},
        ),
    ]

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return list(proposals)

        async def revise_proposal(self, *, user_id, proposal_id, message):
            revised_calls.append((user_id, proposal_id, message))
            return SimpleNamespace(
                id=203,
                session_id=1,
                status="pending",
                proposal_type="event_creation",
                summary="方案二（修改中）",
                related_event_id=None,
                related_task_id=None,
                payload_json={"revision_request": message},
            )

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, *, user_id, session_id, payload):
            persisted_targets.append((user_id, session_id, payload))
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="把P2改到明天下午4点",
            external_context={},
        )
    )

    assert reply == "我已根据你的修改生成新的待确认方案，旧方案不会再执行。"
    assert revised_calls == [("demo-user", 102, "把P2改到明天下午4点")]
    assert persisted_targets[0][2]["active_proposal_id"] == 203


def test_assistant_service_treats_type_correction_as_single_pending_revision() -> None:
    service = AssistantService()
    revised_calls = []

    proposal = SimpleNamespace(
        id=101,
        session_id=1,
        status="pending",
        proposal_type="task_creation",
        summary="建议先创建任务“明天安排一下复习”",
        recommended_option_id="A",
        related_event_id=None,
        related_task_id=None,
        payload_json={"options": [{"option_id": "A", "actions": []}]},
    )

    class FakeProposalManager:
        async def list_proposals(self, *, user_id, session_id, statuses, limit):
            return [proposal]

        async def revise_proposal(self, *, user_id, proposal_id, message):
            revised_calls.append((user_id, proposal_id, message))
            return SimpleNamespace(
                id=202,
                session_id=1,
                status="pending",
                proposal_type="task_creation",
                summary="建议先创建任务“明天安排一下复习”（修改中）",
                related_event_id=None,
                related_task_id=None,
                payload_json={"revision_request": message},
            )

    class FakeThreadStateRepository:
        async def upsert_active_target_state(self, **_kwargs):
            return SimpleNamespace(id=1)

    service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
    service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

    reply = asyncio.run(
        service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="这个是任务，不是单次日程",
            external_context={},
        )
    )

    assert reply == "我已根据你的修改生成新的待确认方案，旧方案不会再执行。"
    assert revised_calls == [("demo-user", 101, "这个是任务，不是单次日程")]


def test_assistant_service_does_not_treat_generic_this_as_proposal_revision() -> None:
    service = AssistantService()

    assert service._looks_like_proposal_revision("把这个改到明天下午4点") is False
    assert service._looks_like_proposal_revision("把这个方案改到明天下午4点") is True


def test_send_message_proposal_mode_short_circuits_legacy_write_path() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
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
        service.conductor = AssistantConductor.build_default(
            semantic_extractor=StaticUnderstandingExtractor(
                {
                    "intent": "create_event",
                    "goal_type": "event",
                    "title": "和同学见面",
                    "location_name": "学校",
                    "missing_fields": [],
                    "ambiguities": [],
                    "confidence": 0.93,
                }
            )
        )
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


def test_send_message_proposal_mode_create_event_then_confirm_smoke() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        service.conductor = AssistantConductor.build_default(
            semantic_extractor=StaticUnderstandingExtractor(
                {
                    "intent": "create_event",
                    "goal_type": "event",
                    "title": "和同学见面",
                    "location_name": "学校",
                    "missing_fields": [],
                    "ambiguities": [],
                    "confidence": 0.92,
                }
            )
        )
        messages = []
        created_payloads = []
        confirmed_calls = []
        active_target_payloads = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        class FakeProposalManager:
            def __init__(self):
                self.item = None

            async def create_proposal(self, *, user_id, payload):
                created_payloads.append((user_id, payload))
                self.item = SimpleNamespace(
                    id=202,
                    session_id=payload.session_id,
                    status="pending",
                    proposal_type=payload.proposal_type,
                    summary=payload.summary,
                    related_event_id=payload.related_event_id,
                    related_task_id=payload.related_task_id,
                    payload_json=payload.payload_json,
                    recommended_option_id=payload.recommended_option_id,
                    selected_option_id=None,
                    executed_at=None,
                )
                return self.item

            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                del user_id, session_id, statuses, limit
                return [self.item] if self.item and self.item.status == "pending" else []

            async def confirm_proposal(self, *, user_id, proposal_id, option_id):
                confirmed_calls.append((user_id, proposal_id, option_id))
                self.item.status = "executed"
                self.item.selected_option_id = option_id
                self.item.executed_at = datetime(2026, 5, 2, 10, 0)
                self.item.related_event_id = 88
                self.item.payload_json = {
                    **(self.item.payload_json or {}),
                    "execution": {
                        "status": "executed",
                        "selected_option_id": option_id,
                        "result": {"related_event_id": 88},
                    },
                }
                return self.item

        class FakeThreadStateRepository:
            async def upsert_active_target_state(self, *, user_id, session_id, payload):
                active_target_payloads.append((user_id, session_id, payload))
                return SimpleNamespace(id=len(active_target_payloads), **payload)

        async def fail_create_event(**_kwargs):
            raise AssertionError("event write must wait for proposal confirmation")

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

        async def fake_with_active_target_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._with_active_target_context = fake_with_active_target_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service.event_service.create_event = fail_create_event  # type: ignore[method-assign]

        proposed = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="明天下午3点我要去学校和同学见面"),
        )
        confirmed = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="同意"),
        )

        assert proposed.actions == []
        assert "待确认方案" in proposed.reply
        assert len(created_payloads) == 1
        assert created_payloads[0][1].proposal_type == "event_creation"
        assert confirmed.reply == "已按这个方案确认并执行。"
        assert confirmed.actions == []
        assert confirmed_calls == [("demo-user", 202, "A")]
        assert active_target_payloads[-1][2]["active_proposal_id"] == 202
        assert active_target_payloads[-1][2]["related_event_id"] == 88

    asyncio.run(scenario())


def test_send_message_task_schedule_continuation_short_circuits_legacy_fallback() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []
        persisted_payloads = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return [_message("assistant", "我先建议先创建任务“整理毕设论文”，后续再继续规划。")]

        class FakeProposalManager:
            async def create_proposal(self, *, user_id, payload):
                persisted_payloads.append((user_id, payload))
                return SimpleNamespace(
                    id=303,
                    session_id=payload.session_id,
                    status="pending",
                    proposal_type=payload.proposal_type,
                    summary=payload.summary,
                    related_task_id=payload.related_task_id,
                    related_event_id=payload.related_event_id,
                    payload_json=payload.payload_json,
                )

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return SimpleNamespace(
                    id=11,
                    state_json={"active_target": {"task_id": 21, "kind": "task"}},
                    updated_at=datetime(2026, 5, 2, 9, 0),
                )

            async def upsert_active_target_state(self, *, user_id, session_id, payload):
                return SimpleNamespace(id=12, **payload)

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for task continuation in proposal mode")

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
                work_location_coords=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            )

        async def fake_list_tasks(**_kwargs):
            return [SimpleNamespace(id=21, content="整理毕设论文", status="pending")]

        async def fake_build_external_context(**_kwargs):
            return {}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="我预计3天整理完成，帮我安排下下午3点到5点"),
        )

        assert response.actions == []
        assert "待确认方案" in response.reply
        assert len(persisted_payloads) == 1
        _user_id, payload = persisted_payloads[0]
        assert payload.proposal_type == "task_schedule_plan"
        option_actions = payload.payload_json["options"][0]["actions"]
        assert len(option_actions) == 3
        assert all(action["payload"]["linked_task_id"] == 21 for action in option_actions)
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_primary_mode_blocks_legacy_fallback_chain() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "primary"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

            async def update_session_context(self, session_id, *, user_id, context_json):
                return None

            async def update_session_context(self, session_id, *, user_id, context_json):
                return None

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
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

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should be blocked in primary mode")

        class FakeConductor:
            async def run(self, context, *, mode="shadow"):
                assert mode == "primary"
                return SimpleNamespace(
                    decision="legacy",
                    reply=None,
                    proposals=[],
                    understanding=None,
                    trace=[],
                    mode=mode,
                    unsupported_reason="no_supported_specialist_output",
                    metadata={},
                    to_log_payload=lambda: {"decision": "legacy", "mode": mode},
                )

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service.conductor = FakeConductor()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="帮我处理一下"),
        )

        assert response.actions == []
        assert "旧的规则回退链路" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_does_not_fall_back_for_missing_pending_confirmation() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                return []

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
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

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for missing proposal confirmation text")

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.conductor = AssistantConductor.build_default(
            semantic_extractor=StaticUnderstandingExtractor(
                {
                    "intent": "create_event",
                    "goal_type": "event",
                    "title": "和同学见面",
                    "location_name": "学校",
                    "missing_fields": [],
                    "ambiguities": [],
                    "confidence": 0.93,
                }
            )
        )
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="同意"),
        )

        assert response.actions == []
        assert "当前没有待确认方案可执行" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_blocks_legacy_fallback_for_context_driven_message() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

            async def update_session_context(self, session_id, *, user_id, context_json):
                return None

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
                work_location_coords=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            )

        async def fake_list_tasks(**_kwargs):
            return [SimpleNamespace(id=21, content="整理毕设论文", status="pending")]

        async def fake_build_external_context(**_kwargs):
            return {}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should be blocked for context-driven message in proposal mode")

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return SimpleNamespace(
                    id=11,
                    state_json={"active_target": {"task_id": 21, "kind": "task"}},
                    updated_at=datetime(2026, 5, 2, 9, 0),
                )

        class FakeConductor:
            async def run(self, context, *, mode="shadow"):
                assert mode == "proposal"
                return SimpleNamespace(
                    decision="legacy",
                    reply=None,
                    proposals=[],
                    understanding=None,
                    trace=[],
                    mode=mode,
                    unsupported_reason="no_supported_specialist_output",
                    metadata={},
                    to_log_payload=lambda: {"decision": "legacy", "mode": mode},
                )

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service.conductor = FakeConductor()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="继续规划这个任务"),
        )

        assert response.actions == []
        assert "继续规划已有任务" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_uses_orchestration_answer_for_schedule_guidance() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

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
                work_location_name="图书馆",
                work_location_coords=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            )

        async def fake_list_tasks(**_kwargs):
            return [SimpleNamespace(id=21, content="整理毕设论文", priority=3)]

        async def fake_build_external_context(**_kwargs):
            return {"default_commute": {"duration_minutes": 20}}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        async def noop_persist_pending_action(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for schedule guidance answer path")

        async def fake_build_suggestions_for_dates(**_kwargs):
            return [
                SimpleNamespace(
                    model_dump=lambda mode="json": {
                        "type": "task_split_slot",
                        "title": "整理毕设论文",
                        "start_time": "2026-05-03T15:00:00",
                        "end_time": "2026-05-03T17:00:00",
                        "related_task_id": 21,
                        "segment_index": 1,
                        "segment_total": 1,
                    },
                    title="整理毕设论文",
                    start_time=datetime.fromisoformat("2026-05-03T15:00:00"),
                    end_time=datetime.fromisoformat("2026-05-03T17:00:00"),
                    segment_index=1,
                    segment_total=1,
                )
            ]

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._persist_pending_action = noop_persist_pending_action  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="明天把论文安排进去"),
        )

        assert any(action.type == "suggest_schedule" for action in response.actions)
        assert "可用空档" in response.reply or "建议" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_uses_orchestration_answer_for_progress_followup() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

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
                work_location_name="图书馆",
                work_location_coords=None,
                transport_preference=None,
                wake_up_time=None,
                sleep_time=None,
            )

        async def fake_list_tasks(**_kwargs):
            return [
                SimpleNamespace(
                    id=21,
                    content="整理毕设论文",
                    status="pending",
                    completed_minutes=80,
                    scheduled_minutes=120,
                    remaining_minutes=160,
                )
            ]

        async def fake_build_external_context(**_kwargs):
            return {}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def noop_autorename(**_kwargs):
            return None

        async def noop_persist_pending_action(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for progress followup answer path")

        async def fake_recent_followups(**_kwargs):
            return [SimpleNamespace(message="昨天已经完成文献综述整理")]

        async def fake_build_suggestions_for_dates(**_kwargs):
            return [
                SimpleNamespace(
                    model_dump=lambda mode="json": {
                        "type": "task_split_slot",
                        "title": "整理毕设论文",
                        "start_time": "2026-05-03T15:00:00",
                        "end_time": "2026-05-03T17:00:00",
                        "related_task_id": 21,
                    },
                    title="整理毕设论文",
                    start_time=datetime.fromisoformat("2026-05-03T15:00:00"),
                    end_time=datetime.fromisoformat("2026-05-03T17:00:00"),
                )
            ]

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._persist_pending_action = noop_persist_pending_action  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service.reminder_repository.list_recent_task_followups = fake_recent_followups  # type: ignore[method-assign]
        service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="现在进展如何，接下来怎么安排"),
        )

        assert any(action.type == "suggest_schedule" for action in response.actions)
        assert "整理毕设论文" in response.reply
        assert "最近执行反馈" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_progress_followup_empty_state_stays_on_answer_path() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
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

        async def noop_persist_pending_action(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for empty progress followup")

        async def fake_recent_followups(**_kwargs):
            return []

        async def fake_build_suggestions_for_dates(**_kwargs):
            return []

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._persist_pending_action = noop_persist_pending_action  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service.reminder_repository.list_recent_task_followups = fake_recent_followups  # type: ignore[method-assign]
        service.suggestion_service.build_suggestions_for_dates = fake_build_suggestions_for_dates  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="现在进展如何，接下来怎么安排"),
        )

        assert response.actions == []
        assert "目前没有新的进度变化" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_stream_proposal_mode_progress_followup_empty_state_stays_on_answer_path() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

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
                work_location_name="图书馆",
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

        async def noop_persist_pending_action(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for streaming empty progress followup")

        async def fake_recent_followups(**_kwargs):
            return []

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._persist_pending_action = noop_persist_pending_action  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service.reminder_repository.list_recent_task_followups = fake_recent_followups  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in service.send_message_stream(
                user_id="demo-user",
                payload=AssistantMessageCreate(session_id=1, message="现在进展如何"),
            )
        ]

        assert chunks[-1]["type"] == "done"
        assert chunks[-1]["full_reply"] == "目前没有新的进度变化。"
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_stream_persists_inline_blocks_from_proposal_protocol() -> None:
    async def scenario() -> None:
        service = AssistantService()
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(timezone="Asia/Shanghai")

        async def fake_list_tasks(**_kwargs):
            return []

        async def fake_build_external_context(**_kwargs):
            return {}

        async def fake_with_memory_context(**kwargs):
            return kwargs["external_context"]

        async def fake_with_active_target(**kwargs):
            return kwargs["external_context"]

        async def fake_protocol(**_kwargs):
            proposal = SimpleNamespace(
                id=202,
                status="pending",
                proposal_type="event_creation",
                summary="建议创建修订后的日程",
                recommended_option_id="A",
                selected_option_id=None,
                payload_json={
                    "protocol_label": "P1",
                    "options": [
                        {
                            "option_id": "A",
                            "title": "改到晚上8点",
                            "summary": "今晚 20:00-21:00",
                            "actions": [],
                        }
                    ],
                },
            )
            service._queue_inline_render_block_from_proposal(proposal)
            return "我已根据你的修改生成新的待确认方案，旧方案不会再执行。"

        async def noop_autorename(**_kwargs):
            return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._with_active_target_context = fake_with_active_target  # type: ignore[method-assign]
        service._maybe_handle_proposal_text_protocol = fake_protocol  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in service.send_message_stream(
                user_id="demo-user",
                payload=AssistantMessageCreate(session_id=1, message="把方案A改到晚上8点"),
            )
        ]

        done = chunks[-1]
        assistant_message = messages[-1]
        assert done["type"] == "done"
        assert done["render_blocks"][0]["type"] == "proposal_options"
        assert done["render_blocks"][0]["payload"]["proposal_id"] == 202
        assert assistant_message["role"] == "assistant"
        assert assistant_message["render_blocks_json"] == done["render_blocks"]

    asyncio.run(scenario())


def test_send_message_stream_proposal_mode_does_not_use_gemini_stream_as_default_fallback() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
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

        async def fail_gemini_stream(**_kwargs):
            raise AssertionError("gemini streaming plan fallback should not run after proposal-mode conductor")
            yield ""  # pragma: no cover

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run after proposal-mode conductor in stream")

        class FakeConductor:
            async def run(self, context, *, mode="shadow"):
                assert mode == "proposal"
                return ConductorResult(decision="legacy", mode="proposal", unsupported_reason="test_fallback")

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service.conductor = FakeConductor()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service.gemini = SimpleNamespace(enabled=True, generate_plan_stream=fail_gemini_stream)  # type: ignore[assignment]

        chunks = [
            chunk
            async for chunk in service.send_message_stream(
                user_id="demo-user",
                payload=AssistantMessageCreate(session_id=1, message="给我一个普通建议"),
            )
        ]

        assert chunks[-1]["type"] == "done"
        assert "旧的规则回退链路" in chunks[-1]["full_reply"]
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_does_not_use_legacy_plan_as_default_fallback() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def fake_list_events(**_kwargs):
            return []

        async def fake_get_profile(_user_id):
            return SimpleNamespace(
                display_name="Demo",
                timezone="Asia/Shanghai",
                home_location_name=None,
                home_location_coords=None,
                work_location_name=None,
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

        async def fake_run_conductor(**_kwargs):
            return ConductorResult(decision="legacy", mode="proposal", unsupported_reason="test_fallback")

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run after proposal-mode conductor")

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._run_conductor_for_message = fake_run_conductor  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="给我一个普通建议"),
        )

        assert "旧的规则回退链路" in response.reply
        assert response.actions == []
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_send_message_proposal_mode_uses_orchestration_answer_for_event_context_advice() -> None:
    async def scenario() -> None:
        service = AssistantService()
        service.settings.assistant_conductor_mode = "proposal"
        service.conductor = AssistantConductor.build_default(
            semantic_extractor=StaticUnderstandingExtractor(
                {
                    "intent": "event_context_advice",
                    "goal_type": "event",
                    "title": "开组会",
                    "location_name": "图书馆",
                    "missing_fields": [],
                    "ambiguities": [],
                    "confidence": 0.92,
                }
            )
        )
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                return []

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
                work_location_name="实验室",
                work_location_coords=None,
                transport_preference="walking",
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

        async def noop_persist_pending_action(**_kwargs):
            return None

        async def fail_build_plan(**_kwargs):
            raise AssertionError("legacy build_plan should not run for event context advice answer path")

        async def fake_build_event_specific_context(**_kwargs):
            return {
                "commute_summary": "从宿舍到图书馆预计约 25 分钟。",
                "weather_summary": "图书馆当前天气 小雨, 18°C。",
                "advice_summary": "建议带伞或预留天气变化时间。",
            }

        class FakeThreadStateRepository:
            async def get_active_target_state(self, *, user_id, session_id):
                return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service.event_repository.list_events = fake_list_events  # type: ignore[method-assign]
        service.profile_repository.get_profile = fake_get_profile  # type: ignore[method-assign]
        service.task_service.list_tasks = fake_list_tasks  # type: ignore[method-assign]
        service._build_external_context = fake_build_external_context  # type: ignore[method-assign]
        service._with_assistant_memory_context = fake_with_memory_context  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]
        service._persist_pending_action = noop_persist_pending_action  # type: ignore[method-assign]
        service._build_plan = fail_build_plan  # type: ignore[method-assign]
        service._build_event_specific_context = fake_build_event_specific_context  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="demo-user",
            payload=AssistantMessageCreate(session_id=1, message="明天下午三点去图书馆开组会，我几点出发，要不要带伞"),
        )

        assert any(action.type == "propose_event" for action in response.actions)
        assert "25 分钟" in response.reply
        assert "带伞" in response.reply
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())
