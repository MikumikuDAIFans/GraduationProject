from __future__ import annotations

import asyncio

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState, UnderstandingResult
from app.assistant_agents.registry import SpecialistRegistry
from app.assistant_agents.specialists.planning import PlanningSpecialist
from app.assistant_agents.specialists.proposal_manager import ProposalManagerSpecialist


def test_specialist_registry_runs_registered_specialist() -> None:
    registry = SpecialistRegistry()
    registry.register(PlanningSpecialist())
    assert registry.names() == ["planning"]


def test_planning_and_proposal_manager_prepare_create_payload_without_persistence() -> None:
    state = ConductorState(
        understanding=UnderstandingResult(
            intent="create_event",
            goal_type="event",
            confidence=0.8,
            slots={
                "title": "和同学见面",
                "start_time": "2026-05-01T15:00:00",
                "end_time": None,
                "location_name": "学校",
            },
            missing_fields=["end_time_or_duration"],
            assumptions=["default_event_duration_60_minutes"],
            can_propose_without_clarification=True,
            requires_clarification=True,
        )
    )
    context = AssistantAgentContext(user_id="demo-user", session_id=9, user_message="明天下午3点去学校和同学见面")

    state = asyncio.run(PlanningSpecialist().run(context, state))
    state = asyncio.run(ProposalManagerSpecialist().run(context, state))

    assert len(state.proposals) == 1
    assert state.proposals[0].display_id == "P1"
    assert state.proposals[0].dedup_key is not None
    create_payload = state.metadata["proposal_create_payloads"][0]
    assert create_payload["session_id"] == 9
    assert create_payload["payload_json"]["options"][0]["actions"][0]["type"] == "create_event"
