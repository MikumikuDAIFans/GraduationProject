from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api.schemas import AssistantMessageCreate
from app.services.assistant import AssistantService
from app.services.assistant_memory import AssistantMemoryService


class FakeMemoryService:
    def __init__(self) -> None:
        self.payloads = []
        self.runtime_context = {}
        self.candidates = [
            SimpleNamespace(
                id=1,
                status="proposed",
                memory_type="places",
                proposed_change_json={
                    "operation": "append_entry",
                    "title": "学校",
                    "content": "学校 = 南京大学仙林校区",
                },
            )
        ]

    async def create_candidate(self, *, user_id: str, payload):
        self.payloads.append((user_id, payload))
        return SimpleNamespace(
            id=len(self.payloads),
            status="proposed",
            memory_type=payload.memory_type,
            proposed_change_json=payload.proposed_change_json,
        )

    async def list_candidates(self, *, user_id: str, statuses=None, memory_type=None, limit: int = 50):
        del user_id, statuses, memory_type, limit
        return list(self.candidates)

    async def confirm_candidate(self, *, user_id: str, candidate_id: int):
        del user_id
        for index, candidate in enumerate(self.candidates):
            if candidate.id == candidate_id:
                updated = SimpleNamespace(**{**candidate.__dict__, "status": "written"})
                self.candidates[index] = updated
                return updated
        raise AssertionError(f"candidate {candidate_id} not found")

    async def reject_candidate(self, *, user_id: str, candidate_id: int):
        del user_id
        for index, candidate in enumerate(self.candidates):
            if candidate.id == candidate_id:
                updated = SimpleNamespace(**{**candidate.__dict__, "status": "rejected"})
                self.candidates[index] = updated
                return updated
        raise AssertionError(f"candidate {candidate_id} not found")

    async def build_runtime_context(self, *, user_id: str):
        assert user_id == "local-user"
        return self.runtime_context

    def extract_place_aliases(self, memory_context):
        return AssistantMemoryService().extract_place_aliases(memory_context)


def test_assistant_service_captures_explicit_memory_candidate_without_writing() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory

        candidates = await service._capture_memory_candidates_for_message(
            user_id="local-user",
            user_message="请帮我记住学校在北京大学东门",
        )

        assert len(candidates) == 1
        assert candidates[0].status == "proposed"
        assert len(fake_memory.payloads) == 1
        user_id, payload = fake_memory.payloads[0]
        assert user_id == "local-user"
        assert payload.memory_type == "places"
        assert payload.status == "proposed"
        assert payload.proposed_change_json["operation"] == "append_entry"
        assert payload.proposed_change_json["content"] == "学校在北京大学东门"

    asyncio.run(scenario())


def test_assistant_service_captures_explicit_place_alias_candidate_without_writing() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory

        candidates = await service._capture_memory_candidates_for_message(
            user_id="local-user",
            user_message="以后把学校理解为南京大学仙林校区",
        )

        assert len(candidates) == 1
        user_id, payload = fake_memory.payloads[0]
        assert user_id == "local-user"
        assert payload.memory_type == "places"
        assert payload.proposed_change_json["title"] == "学校"
        assert payload.proposed_change_json["content"] == "学校 = 南京大学仙林校区"

    asyncio.run(scenario())


def test_assistant_service_ignores_non_explicit_memory_message() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory

        candidates = await service._capture_memory_candidates_for_message(
            user_id="local-user",
            user_message="我下午三点去学校",
        )

        assert candidates == []
        assert fake_memory.payloads == []

    asyncio.run(scenario())


def test_memory_candidate_notice_keeps_confirmation_boundary_visible() -> None:
    service = AssistantService()

    reply = service._append_memory_candidate_notice(
        "好的。",
        user_message="记住我喜欢上午安排深度任务",
        memory_candidates=[SimpleNamespace(id=1)],
    )

    assert "待确认记忆" in reply
    assert "确认后" in reply


def test_memory_text_protocol_confirms_single_pending_candidate() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory

        reply = await service._maybe_handle_memory_candidate_text_protocol(
            user_id="local-user",
            user_message="记住",
        )

        assert reply is not None
        assert "已确认并写入长期记忆" in reply
        assert "学校" in reply
        assert fake_memory.candidates[0].status == "written"

    asyncio.run(scenario())


def test_memory_text_protocol_rejects_single_pending_candidate() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory

        reply = await service._maybe_handle_memory_candidate_text_protocol(
            user_id="local-user",
            user_message="不要记",
        )

        assert reply is not None
        assert "已拒绝这条待确认记忆" in reply
        assert fake_memory.candidates[0].status == "rejected"

    asyncio.run(scenario())


def test_memory_text_protocol_confirms_explicit_candidate_id() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        fake_memory.candidates.append(
            SimpleNamespace(
                id=2,
                status="proposed",
                memory_type="preferences",
                proposed_change_json={
                    "operation": "append_entry",
                    "title": "深度工作",
                    "content": "我喜欢上午安排深度工作",
                },
            )
        )
        service.memory_service = fake_memory

        reply = await service._maybe_handle_memory_candidate_text_protocol(
            user_id="local-user",
            user_message="记住 M2",
        )

        assert reply is not None
        assert "已确认并写入长期记忆" in reply
        assert fake_memory.candidates[0].status == "proposed"
        assert fake_memory.candidates[1].status == "written"

    asyncio.run(scenario())


def test_memory_text_protocol_rejects_explicit_candidate_id() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        fake_memory.candidates.append(
            SimpleNamespace(
                id=2,
                status="proposed",
                memory_type="preferences",
                proposed_change_json={
                    "operation": "append_entry",
                    "title": "深度工作",
                    "content": "我喜欢上午安排深度工作",
                },
            )
        )
        service.memory_service = fake_memory

        reply = await service._maybe_handle_memory_candidate_text_protocol(
            user_id="local-user",
            user_message="M2 不要记",
        )

        assert reply is not None
        assert "已拒绝这条待确认记忆" in reply
        assert fake_memory.candidates[0].status == "proposed"
        assert fake_memory.candidates[1].status == "rejected"

    asyncio.run(scenario())


def test_memory_text_protocol_stream_ends_with_done_frame() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def noop_autorename(**_kwargs):
            return None

        service.memory_service = fake_memory
        service.repository = FakeRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in service.send_message_stream(
                user_id="local-user",
                payload=AssistantMessageCreate(session_id=1, message="不要记"),
            )
        ]

        assert chunks[-1]["type"] == "done"
        assert "已拒绝这条待确认记忆" in chunks[-1]["full_reply"]
        assert fake_memory.candidates[0].status == "rejected"
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_memory_conflict_reply_mentions_old_and_new_place_values() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        fake_memory.runtime_context = {
            "source": "confirmed_long_term_memory",
            "places": ["学校: 学校 = 南京大学仙林校区"],
        }
        service.memory_service = fake_memory

        reply = await service._maybe_handle_memory_conflict_message(
            user_id="local-user",
            user_message="以后学校指的是B地址",
        )

        assert reply is not None
        assert "学校" in reply
        assert "南京大学仙林校区" in reply
        assert "B地址" in reply
        assert "替换" in reply
        assert fake_memory.payloads == []

    asyncio.run(scenario())


def test_memory_conflict_stream_ends_with_done_frame() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        fake_memory.runtime_context = {
            "source": "confirmed_long_term_memory",
            "places": ["学校: 学校 = 南京大学仙林校区"],
        }
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def noop_autorename(**_kwargs):
            return None

        service.memory_service = fake_memory
        service.repository = FakeRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in service.send_message_stream(
                user_id="local-user",
                payload=AssistantMessageCreate(session_id=1, message="以后学校指的是B地址"),
            )
        ]

        assert chunks[-1]["type"] == "done"
        assert "南京大学仙林校区" in chunks[-1]["full_reply"]
        assert "B地址" in chunks[-1]["full_reply"]
        assert fake_memory.payloads == []
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_assistant_service_injects_confirmed_memory_into_external_context() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        fake_memory.runtime_context = {
            "source": "confirmed_long_term_memory",
            "places": ["学校: 学校 = 北京大学东门"],
        }
        service.memory_service = fake_memory

        context = await service._with_assistant_memory_context(
            user_id="local-user",
            external_context={"weather_now": {"text": "晴"}},
        )

        assert context["weather_now"]["text"] == "晴"
        assert context["assistant_memory"]["places"] == ["学校: 学校 = 北京大学东门"]
        assert context["assistant_memory"]["source"] == "confirmed_long_term_memory"

    asyncio.run(scenario())


def test_assistant_service_applies_confirmed_place_memory_to_event_payload() -> None:
    service = AssistantService()
    payload = service.text_runtime._build_rule_based_event_payload("明天下午三点去学校上课")

    enriched = service._apply_place_memory_to_event_payload(
        payload=payload,
        user_message="明天下午三点去学校上课",
        external_context={
            "assistant_memory": {
                "source": "confirmed_long_term_memory",
                "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
            }
        },
    )

    assert enriched["location_name"] == "北京大学东门"
    assert enriched["location_coords"] == "116.310918,39.992873"


def test_assistant_service_short_circuits_explicit_memory_message_before_planning() -> None:
    async def scenario() -> None:
        service = AssistantService()
        fake_memory = FakeMemoryService()
        service.memory_service = fake_memory
        messages = []

        class FakeRepository:
            async def create_message(self, **kwargs):
                messages.append(kwargs)
                return SimpleNamespace(id=len(messages), **kwargs)

            async def list_messages(self, session_id):
                raise AssertionError("memory-only requests should short-circuit before loading history")

        async def fake_resolve_session(**_kwargs):
            return SimpleNamespace(id=1, title="Chat", context_json={})

        async def noop_autorename(**_kwargs):
            return None

        service.repository = FakeRepository()  # type: ignore[assignment]
        service._resolve_session = fake_resolve_session  # type: ignore[method-assign]
        service._maybe_autorename_session = noop_autorename  # type: ignore[method-assign]

        response = await service.send_message(
            user_id="local-user",
            payload=AssistantMessageCreate(
                session_id=1,
                message="请帮我记住：我喜欢周五下午集中处理行政事务",
            ),
        )

        assert "长期记忆请求" in response.reply
        assert "待确认记忆" in response.reply
        assert len(fake_memory.payloads) == 1
        assert messages[-1]["role"] == "assistant"

    asyncio.run(scenario())
