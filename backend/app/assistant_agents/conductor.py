"""Assistant conductor that routes user input to specialist modules."""

from __future__ import annotations

from loguru import logger

from app.assistant_agents.contracts import (
    AssistantAgentContext,
    ConductorResult,
    ConductorState,
    SpecialistCall,
)
from app.assistant_agents.registry import SpecialistRegistry
from app.assistant_agents.specialists.negotiation import NegotiationSpecialist
from app.assistant_agents.specialists.memory import MemorySpecialist
from app.assistant_agents.specialists.planning import PlanningSpecialist
from app.assistant_agents.specialists.proposal_manager import ProposalManagerSpecialist
from app.assistant_agents.specialists.task_or_event_clarifier import TaskOrEventClarifierSpecialist
from app.assistant_agents.specialists.understanding import UnderstandingSpecialist
from app.services.assistant_runtime_text import AssistantTextRuntime


class AssistantConductor:
    """Routes a passive user message through the minimal specialist set.

    Phase 3 intentionally produces in-memory clarification/proposal drafts only.
    Event/task writes remain blocked until Phase 4 Action Executor.
    """

    def __init__(self, registry: SpecialistRegistry) -> None:
        self.registry = registry

    @classmethod
    def build_default(cls, text_runtime: AssistantTextRuntime | None = None) -> "AssistantConductor":
        runtime = text_runtime or AssistantTextRuntime()
        registry = SpecialistRegistry()
        registry.register(UnderstandingSpecialist(runtime))
        registry.register(TaskOrEventClarifierSpecialist())
        registry.register(PlanningSpecialist())
        registry.register(ProposalManagerSpecialist())
        registry.register(NegotiationSpecialist())
        registry.register(MemorySpecialist())
        return cls(registry)

    async def run(self, context: AssistantAgentContext, *, mode: str = "shadow") -> ConductorResult:
        state = ConductorState()
        trace: list[SpecialistCall] = []

        state = await self._run_specialist("understanding", context, state, trace)
        understanding = state.understanding
        if understanding is None:
            return ConductorResult(
                decision="unsupported",
                understanding=None,
                trace=trace,
                mode=mode,
                unsupported_reason="understanding_missing",
            )

        if understanding.goal_type == "unknown":
            state = await self._run_specialist("task_or_event_clarifier", context, state, trace)
            state = await self._run_specialist("negotiation", context, state, trace)
            return ConductorResult(
                decision="clarification",
                reply=state.reply,
                understanding=understanding,
                trace=trace,
                mode=mode,
                metadata=state.metadata,
            )

        if understanding.requires_clarification and not understanding.can_propose_without_clarification:
            state = await self._run_specialist("task_or_event_clarifier", context, state, trace)
            state = await self._run_specialist("negotiation", context, state, trace)
            return ConductorResult(
                decision="clarification",
                reply=state.reply,
                understanding=understanding,
                trace=trace,
                mode=mode,
                metadata=state.metadata,
            )

        if understanding.can_propose_without_clarification:
            state = await self._run_specialist("planning", context, state, trace)
            if state.clarification_question:
                state = await self._run_specialist("negotiation", context, state, trace)
                return ConductorResult(
                    decision="clarification",
                    reply=state.reply,
                    understanding=understanding,
                    trace=trace,
                    mode=mode,
                    metadata=state.metadata,
                )
            if state.proposals:
                state = await self._run_specialist("proposal_manager", context, state, trace)
                state = await self._run_specialist("negotiation", context, state, trace)
                return ConductorResult(
                    decision="proposal",
                    reply=state.reply,
                    proposals=state.proposals,
                    understanding=understanding,
                    trace=trace,
                    mode=mode,
                    metadata=state.metadata,
                )

        logger.bind(component="assistant.conductor").debug(
            "Conductor fell back to legacy: {reason}",
            reason="no_supported_specialist_output",
        )
        return ConductorResult(
            decision="legacy",
            understanding=understanding,
            trace=trace,
            mode=mode,
            unsupported_reason="no_supported_specialist_output",
            metadata=state.metadata,
        )

    async def _run_specialist(
        self,
        name: str,
        context: AssistantAgentContext,
        state: ConductorState,
        trace: list[SpecialistCall],
    ) -> ConductorState:
        try:
            updated = await self.registry.run(name, context, state)
            trace.append(SpecialistCall(name=name, detail=self._trace_detail(name, updated)))
            return updated
        except Exception as exc:
            trace.append(SpecialistCall(name=name, status="error", detail={"error": str(exc)}))
            raise

    def _trace_detail(self, name: str, state: ConductorState) -> dict[str, object]:
        if name == "understanding" and state.understanding:
            return state.understanding.to_log_payload()
        if name == "planning":
            return {"proposal_count": len(state.proposals)}
        if name == "proposal_manager":
            return {
                "proposal_ids": [proposal.display_id for proposal in state.proposals],
                "proposal_count": len(state.proposals),
            }
        if name == "negotiation":
            return {"has_reply": bool(state.reply)}
        if name == "task_or_event_clarifier":
            return {"has_question": bool(state.clarification_question)}
        return {}
