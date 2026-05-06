from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.assistant_agents import AssistantAgentContext, AssistantConductor
from app.api.schemas import AssistantMessageCreate
from app.services.assistant import AssistantService


def run_conductor(message: str, *, events=None, tasks=None, history=None, external_context=None):
    conductor = AssistantConductor.build_default()
    context = AssistantAgentContext(
        user_id="demo-user",
        session_id=1,
        user_message=message,
        history=history or [],
        events=events or [],
        tasks=tasks or [],
        profile=SimpleNamespace(home_location_name="宿舍", work_location_name="学校"),
        external_context=external_context or {},
        now=datetime(2026, 5, 2, 9, 0),
    )
    return asyncio.run(conductor.run(context, mode="shadow"))


def _event(event_id: int, title: str, *, hour: int = 10, day: int = 3, status: str = "planned"):
    return SimpleNamespace(
        id=event_id,
        title=title,
        start_time=datetime(2026, 5, day, hour, 0),
        end_time=datetime(2026, 5, day, hour + 1, 30),
        location_name="学校",
        status=status,
    )


def _task(task_id: int, content: str, *, status: str = "pending"):
    return SimpleNamespace(id=task_id, content=content, status=status)


def _message(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


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
    assert "日期范围" in (result.reply or "")


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
    assert "整体推迟一天" in (result.reply or "")


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
    assert "日期范围" in (result.reply or "")


def test_conductor_proposes_task_completion_for_unique_task_target() -> None:
    result = run_conductor("整理毕设论文任务完成了", tasks=[_task(21, "整理毕设论文")])

    assert result.decision == "proposal"
    proposal = result.proposals[0]
    assert proposal.proposal_type == "task_status_update"
    assert proposal.related_task_id == 21
    action = proposal.options[0].actions[0]
    assert action == {"type": "mark_task_completed", "payload": {"task_id": 21}}


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
    assert "哪一个日程" in (result.reply or "")


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


def test_assistant_service_does_not_treat_generic_this_as_proposal_revision() -> None:
    service = AssistantService()

    assert service._looks_like_proposal_revision("把这个改到明天下午4点") is False
    assert service._looks_like_proposal_revision("把这个方案改到明天下午4点") is True


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
