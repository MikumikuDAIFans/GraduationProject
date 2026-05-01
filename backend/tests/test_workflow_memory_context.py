from __future__ import annotations

import asyncio

from app.workflow.nodes import WorkflowNodes
from app.services.assistant import AssistantService


def test_workflow_collect_context_preserves_assistant_memory() -> None:
    async def scenario() -> None:
        state = await WorkflowNodes.collect_context(
            {
                "user_id": "local-user",
                "intent": "unknown",
                "user_message": "你好",
                "extracted_slots": {},
                "external_context": {
                    "assistant_memory": {
                        "source": "confirmed_long_term_memory",
                        "places": ["学校: 学校 = 北京大学东门"],
                    }
                },
            }
        )

        assert state["external_context"]["assistant_memory"]["places"] == ["学校: 学校 = 北京大学东门"]
        assert "weather_now" in state["external_context"]
        assert "default_commute" in state["external_context"]

    asyncio.run(scenario())


def test_workflow_parse_intent_resolves_confirmed_place_memory() -> None:
    async def scenario() -> None:
        service = AssistantService()
        state = await WorkflowNodes.parse_intent(
            {
                "assistant_service": service,
                "user_id": "local-user",
                "user_message": "明天下午三点去学校上课",
                "external_context": {
                    "assistant_memory": {
                        "source": "confirmed_long_term_memory",
                        "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
                    }
                },
            }
        )

        payload = state["extracted_slots"]["new_event"]
        assert payload["location_name"] == "北京大学东门"
        assert payload["location_coords"] == "116.310918,39.992873"
        assert state["extracted_slots"]["location"] == "116.310918,39.992873"

    asyncio.run(scenario())
