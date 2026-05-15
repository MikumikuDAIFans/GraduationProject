from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.assistant_agents.contracts import ProposalDraft, ProposalOptionDraft
from app.assistant_agents.specialists.negotiation import NegotiationSpecialist
from app.services.assistant import AssistantService


def test_negotiation_text_labels_multiple_proposals() -> None:
    proposals = [
        ProposalDraft(
            proposal_type="event_creation",
            summary="建议创建日程 A",
            display_id="P1",
            options=[ProposalOptionDraft(option_id="A", title="创建", summary="明天 15:00-16:00")],
        ),
        ProposalDraft(
            proposal_type="task_creation",
            summary="建议创建任务 B",
            display_id="P2",
            options=[ProposalOptionDraft(option_id="A", title="创建", summary="进入待排程")],
        ),
    ]

    text = NegotiationSpecialist().format_proposals(proposals)

    assert "P1" in text
    assert "P2" in text
    assert "确认 P1 方案A" in text
    assert "不会直接写入" in text


def test_negotiation_text_includes_recommendation_reason_and_examples() -> None:
    proposals = [
        ProposalDraft(
            proposal_type="event_creation",
            summary="建议创建日程 去学校和同学见面",
            display_id="P1",
            recommended_option_id="A",
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="按建议创建",
                    summary="05-12 15:00-16:00，地点：学校",
                    rationale="结束时间未明确，先按 1 小时估算，可在确认前修改。",
                )
            ],
        )
    ]

    text = NegotiationSpecialist().format_proposals(proposals)

    assert "推荐：" in text
    assert "原因：" in text
    assert "可回复示例：" in text
    assert "接受：" in text
    assert "修改：" in text
    assert "拒绝：" in text


def test_contextual_proposal_revision_allows_single_pending_short_reply() -> None:
    service = AssistantService()

    assert service._looks_like_contextual_proposal_revision("改成4点开始") is True
    assert service._looks_like_contextual_proposal_revision("结束时间缩短半小时") is True
    assert service._looks_like_contextual_proposal_revision("开到5点") is True
    assert service._looks_like_contextual_proposal_revision("下午1点开始，晚上10点结束") is True
    assert service._looks_like_contextual_proposal_revision("今天不去了") is False
    assert service._looks_like_contextual_proposal_revision("明天晚上6点去约会") is False


def test_proposal_rejection_protocol_phrases() -> None:
    service = AssistantService()

    assert service._classify_proposal_text_protocol("先不要安排") == "reject"
    assert service._classify_proposal_text_protocol("P2 先不安排") == "reject"
    assert service._classify_proposal_text_protocol("可以") == "confirm"
    assert service._classify_proposal_text_protocol("P1 按方案A安排") == "confirm"
    assert service._classify_proposal_text_protocol("确认 P1 方案A") == "confirm"
    assert service._classify_proposal_text_protocol("接受 P1 方案A") == "confirm"
    assert service._classify_proposal_text_protocol("拒绝 P1 全部方案") == "reject"
    assert service._classify_proposal_text_protocol("拒绝全部 P3") == "reject"
    assert service._classify_proposal_text_protocol("算了，不选了") == "reject"
    assert service._classify_proposal_text_protocol("不选了") == "reject"
    assert service._classify_proposal_text_protocol("P1 开到5点") == "revise"
    assert service._classify_proposal_text_protocol("重试 P1") == "retry"
    assert service._extract_proposal_option_id("P1 按方案A安排") == "A"
    assert service._extract_proposal_option_id("P2 按方案B") == "B"
    assert service._extract_proposal_option_id("确认 P1 方案A") == "A"
    assert service._extract_proposal_option_id("接受 P1 方案B") == "B"


def test_conductor_reply_uses_persisted_proposal_labels() -> None:
    service = AssistantService()

    reply = service._apply_persisted_proposal_labels(
        "P1：建议创建日程\n方案 A：...\n确认 P1 方案A",
        {"persisted_proposal_labels": ["P2"]},
    )

    assert "P2：建议创建日程" in reply
    assert "确认 P2 方案A" in reply
    assert "P1" not in reply


def test_proposal_revision_can_target_visible_global_pending_proposal() -> None:
    async def scenario() -> None:
        service = AssistantService()
        revised_calls: list[tuple[int, str]] = []
        global_proposal = SimpleNamespace(
            id=101,
            session_id=None,
            status="pending",
            proposal_type="event_creation",
            summary="建议创建日程“下午见面”：05-11 15:00-16:00",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={
                "protocol_label": "P1",
                "options": [
                    {
                        "option_id": "A",
                        "actions": [
                            {
                                "type": "create_event",
                                "payload": {
                                    "title": "下午见面",
                                    "start_time": "2026-05-11T15:00:00",
                                    "end_time": "2026-05-11T16:00:00",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                if statuses != ["pending"]:
                    return []
                return [] if session_id == 1 else [global_proposal]

            async def revise_proposal(self, *, user_id, proposal_id, message):
                revised_calls.append((proposal_id, message))
                return SimpleNamespace(
                    **{
                        **global_proposal.__dict__,
                        "id": 202,
                        "status": "pending",
                        "summary": "建议创建日程“下午见面”：05-11 16:00-17:00",
                        "payload_json": {
                            "protocol_label": "P1",
                            "options": [
                                {
                                    "option_id": "A",
                                    "title": "按修改后的方案执行",
                                    "summary": "建议创建日程“下午见面”：05-11 16:00-17:00",
                                    "actions": [
                                        {
                                            "type": "create_event",
                                            "payload": {
                                                "title": "下午见面",
                                                "start_time": "2026-05-11T16:00:00",
                                                "end_time": "2026-05-11T17:00:00",
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                )

        class FakeThreadStateRepository:
            async def upsert_active_target_state(self, **_kwargs):
                return SimpleNamespace(id=1)

        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

        reply = await service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="下午的见面改到4点",
            external_context={},
        )

        assert reply is not None
        assert "新的待确认方案" in reply
        assert revised_calls == [(101, "下午的见面改到4点")]
        blocks = service._take_inline_render_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == "proposal_options"
        assert blocks[0].payload["proposal_id"] == 202
        assert blocks[0].payload["protocol_label"] == "P1"

    asyncio.run(scenario())


def test_proposal_retry_text_protocol_targets_failed_proposal() -> None:
    async def scenario() -> None:
        service = AssistantService()
        retry_calls: list[int] = []
        failed_proposal = SimpleNamespace(
            id=303,
            session_id=1,
            status="execution_failed",
            proposal_type="event_creation",
            summary="建议创建日程“失败方案”",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={
                "protocol_label": "P1",
                "options": [{"option_id": "A", "actions": []}],
                "execution": {"last_error": "boom"},
            },
        )

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                if statuses == ["pending"]:
                    return []
                if statuses == ["expired", "superseded", "execution_failed"]:
                    return [failed_proposal]
                return []

            async def retry_proposal(self, *, user_id, proposal_id):
                retry_calls.append(proposal_id)
                return SimpleNamespace(**{**failed_proposal.__dict__, "status": "executed"})

        class FakeThreadStateRepository:
            async def upsert_active_target_state(self, **_kwargs):
                return SimpleNamespace(id=1)

        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

        reply = await service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="重试 P1",
            external_context={},
        )

        assert reply is not None
        assert "重试" in reply
        assert retry_calls == [303]

    asyncio.run(scenario())


def test_time_detail_reply_revises_single_pending_event_proposal() -> None:
    async def scenario() -> None:
        service = AssistantService()
        revised_calls: list[tuple[int, str]] = []
        proposal = SimpleNamespace(
            id=101,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="建议创建日程“去学校”：05-12 14:00-15:00",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={
                "protocol_label": "P1",
                "options": [
                    {
                        "option_id": "A",
                        "actions": [
                            {
                                "type": "create_event",
                                "payload": {
                                    "title": "去学校",
                                    "start_time": "2026-05-12T14:00:00",
                                    "end_time": "2026-05-12T15:00:00",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                if statuses != ["pending"]:
                    return []
                return [proposal] if session_id == 1 else []

            async def revise_proposal(self, *, user_id, proposal_id, message):
                revised_calls.append((proposal_id, message))
                return SimpleNamespace(
                    **{
                        **proposal.__dict__,
                        "id": 202,
                        "status": "pending",
                        "summary": "建议创建日程“去学校”：05-12 13:00-22:00",
                    }
                )

        class FakeThreadStateRepository:
            async def upsert_active_target_state(self, **_kwargs):
                return SimpleNamespace(id=1)

        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]
        service.thread_state_repository = FakeThreadStateRepository()  # type: ignore[assignment]

        reply = await service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="下午1点开始，晚上10点结束",
            external_context={},
        )

        assert reply is not None
        assert "新的待确认方案" in reply
        assert revised_calls == [(101, "下午1点开始，晚上10点结束")]

    asyncio.run(scenario())


def test_create_independent_event_directive_points_to_existing_pending_event_proposal() -> None:
    async def scenario() -> None:
        service = AssistantService()
        proposal = SimpleNamespace(
            id=101,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="建议创建日程“去学校”：05-12 13:00-22:00",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={"protocol_label": "P1", "options": [{"option_id": "A", "actions": []}]},
        )

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                if statuses != ["pending"]:
                    return []
                return [proposal] if session_id == 1 else []

        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

        reply = await service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="创建独立日程",
            external_context={},
        )

        assert reply is not None
        assert "已经有待确认的独立日程方案" in reply
        assert "确认 P1 方案A" in reply

    asyncio.run(scenario())


def test_new_timed_event_does_not_revise_single_pending_event_proposal() -> None:
    async def scenario() -> None:
        service = AssistantService()
        revised_calls: list[tuple[int, str]] = []
        proposal = SimpleNamespace(
            id=101,
            session_id=1,
            status="pending",
            proposal_type="event_creation",
            summary="建议创建日程“去学校”：06-01 13:00-14:00",
            recommended_option_id="A",
            related_event_id=None,
            related_task_id=None,
            payload_json={"protocol_label": "P1", "options": [{"option_id": "A", "actions": []}]},
        )

        class FakeProposalManager:
            async def list_proposals(self, *, user_id, session_id, statuses, limit):
                if statuses != ["pending"]:
                    return []
                return [proposal] if session_id == 1 else []

            async def revise_proposal(self, *, user_id, proposal_id, message):
                revised_calls.append((proposal_id, message))
                return proposal

        service.proposal_manager = FakeProposalManager()  # type: ignore[assignment]

        reply = await service._maybe_handle_proposal_text_protocol(
            user_id="demo-user",
            session_id=1,
            user_message="明天晚上6点去约会",
            external_context={},
        )

        assert reply is None
        assert revised_calls == []

    asyncio.run(scenario())
