from __future__ import annotations

import asyncio

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState
from app.assistant_agents.registry import SpecialistRegistry
from app.assistant_agents.specialists.memory import MemorySpecialist


def test_memory_specialist_extracts_explicit_place_candidate() -> None:
    specialist = MemorySpecialist()
    candidate = specialist.extract_candidate("记住学校是北京大学东门，坐标 116.310918,39.992873")

    assert candidate is not None
    assert candidate["memory_type"] == "places"
    assert candidate["status"] == "proposed"
    assert candidate["proposed_change_json"]["operation"] == "append_entry"
    assert "北京大学东门" in candidate["proposed_change_json"]["content"]
    assert candidate["dedup_key"].startswith("memory:places:")


def test_memory_specialist_strips_polite_memory_prefix() -> None:
    specialist = MemorySpecialist()
    candidate = specialist.extract_candidate("请帮我记住图书馆在中心校区东门旁边")

    assert candidate is not None
    assert candidate["memory_type"] == "places"
    assert candidate["proposed_change_json"]["content"] == "图书馆在中心校区东门旁边"


def test_memory_specialist_does_not_extract_without_explicit_memory_request() -> None:
    specialist = MemorySpecialist()

    assert specialist.extract_candidate("我下午三点去学校") is None


def test_memory_specialist_runs_through_registry() -> None:
    async def scenario() -> None:
        registry = SpecialistRegistry()
        registry.register(MemorySpecialist())
        state = await registry.run(
            "memory",
            AssistantAgentContext(
                user_id="local-user",
                session_id=1,
                user_message="记住我喜欢上午安排深度任务",
            ),
            ConductorState(),
        )

        assert state.metadata["memory_candidate_create_payloads"][0]["memory_type"] == "preferences"

    asyncio.run(scenario())
