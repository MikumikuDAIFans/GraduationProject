from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.assistant import AssistantService


class FakeMemoryService:
    def __init__(self) -> None:
        self.payloads = []
        self.runtime_context = {}

    async def create_candidate(self, *, user_id: str, payload):
        self.payloads.append((user_id, payload))
        return SimpleNamespace(
            id=len(self.payloads),
            status="proposed",
            memory_type=payload.memory_type,
            proposed_change_json=payload.proposed_change_json,
        )

    async def build_runtime_context(self, *, user_id: str):
        assert user_id == "local-user"
        return self.runtime_context


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
