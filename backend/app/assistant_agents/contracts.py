"""Shared contracts for the assistant conductor and specialists."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol


GoalType = Literal["event", "task", "schedule_guidance", "progress_followup", "event_context_advice", "unknown"]
ConductorDecision = Literal["legacy", "clarification", "proposal", "answer", "unsupported"]
ConversationMode = Literal["proposal", "clarification", "answer", "confirm_existing", "revise_existing", "unsupported"]
TargetKind = Literal["task", "event", "proposal", "batch_events", "none"]
TargetResolution = Literal["resolved", "ambiguous", "missing"]


@dataclass(slots=True)
class TargetScope:
    """Resolved target information separated from the user goal itself."""

    kind: TargetKind = "none"
    resolution: TargetResolution = "missing"
    task_id: int | None = None
    event_id: int | None = None
    proposal_id: int | None = None
    event_ids: list[int] = field(default_factory=list)
    label: str | None = None
    candidate_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContinuationSignals:
    """Signals that the user is continuing a previous target or proposal."""

    is_following_previous_context: bool = False
    based_on_active_target: bool = False
    based_on_pending_proposal: bool = False
    based_on_history: bool = False
    reason: str | None = None


@dataclass(slots=True)
class TimePreference:
    """Normalized preferred time block for planning proposals."""

    date: str
    start: str
    end: str


@dataclass(slots=True)
class PlanningIntent:
    """Planning-specific shape hints emitted by the conductor."""

    wants_task_split: bool = False
    wants_multi_day_schedule: bool = False
    time_preferences: list[TimePreference] = field(default_factory=list)
    duration_hint_days: int | None = None
    schedule_count: int | None = None


@dataclass(slots=True)
class OrchestrationAssessment:
    """Unified model-driven intermediate state for one user turn."""

    conversation_mode: ConversationMode = "unsupported"
    user_goal: str = "unknown"
    target_scope: TargetScope = field(default_factory=TargetScope)
    continuation: ContinuationSignals = field(default_factory=ContinuationSignals)
    planning_intent: PlanningIntent = field(default_factory=PlanningIntent)
    missing_information: list[str] = field(default_factory=list)
    proposal_shape: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AssistantAgentContext:
    """Immutable-ish runtime context passed to specialists."""

    user_id: str
    session_id: int
    user_message: str
    history: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)
    profile: Any | None = None
    external_context: dict[str, Any] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(slots=True)
class UnderstandingResult:
    """Structured interpretation of a user message."""

    intent: str
    goal_type: GoalType
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    can_propose_without_clarification: bool = False
    requires_clarification: bool = False
    language: str = "zh"
    orchestration: OrchestrationAssessment | None = None

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "goal_type": self.goal_type,
            "confidence": self.confidence,
            "missing_fields": list(self.missing_fields),
            "ambiguities": list(self.ambiguities),
            "assumptions": list(self.assumptions),
            "can_propose_without_clarification": self.can_propose_without_clarification,
            "requires_clarification": self.requires_clarification,
            "orchestration": self.orchestration.to_payload() if self.orchestration else None,
        }


@dataclass(slots=True)
class ProposalOptionDraft:
    """An in-memory option draft. It is not executable until persisted and confirmed."""

    option_id: str
    title: str
    summary: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    rationale: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "option_id": self.option_id,
            "title": self.title,
            "summary": self.summary,
            "actions": self.actions,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class ProposalDraft:
    """A proposal candidate produced by specialists but not necessarily persisted."""

    proposal_type: str
    summary: str
    options: list[ProposalOptionDraft] = field(default_factory=list)
    recommended_option_id: str | None = None
    priority: int = 1
    is_time_sensitive: bool = False
    related_task_id: int | None = None
    related_event_id: int | None = None
    display_id: str | None = None
    dedup_key: str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = dict(self.payload_json or {})
        payload["options"] = [option.to_payload() for option in self.options]
        return {
            "proposal_type": self.proposal_type,
            "summary": self.summary,
            "recommended_option_id": self.recommended_option_id,
            "priority": self.priority,
            "is_time_sensitive": self.is_time_sensitive,
            "related_task_id": self.related_task_id,
            "related_event_id": self.related_event_id,
            "dedup_key": self.dedup_key,
            "payload_json": payload,
        }


@dataclass(slots=True)
class SpecialistCall:
    """Trace item for conductor observability."""

    name: str
    status: str = "ok"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConductorState:
    """Mutable state shared during one conductor run."""

    understanding: UnderstandingResult | None = None
    clarification_question: str | None = None
    proposals: list[ProposalDraft] = field(default_factory=list)
    reply: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConductorResult:
    """Final output from a passive conductor run."""

    decision: ConductorDecision
    reply: str | None = None
    proposals: list[ProposalDraft] = field(default_factory=list)
    understanding: UnderstandingResult | None = None
    trace: list[SpecialistCall] = field(default_factory=list)
    mode: str = "shadow"
    unsupported_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "decision": self.decision,
            "proposal_count": len(self.proposals),
            "proposal_types": [proposal.proposal_type for proposal in self.proposals],
            "understanding": self.understanding.to_log_payload() if self.understanding else None,
            "trace": [
                {"name": item.name, "status": item.status, "detail": item.detail}
                for item in self.trace
            ],
            "unsupported_reason": self.unsupported_reason,
            "metadata": dict(self.metadata or {}),
        }


class AssistantSpecialist(Protocol):
    """Protocol implemented by all assistant specialists."""

    name: str

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        """Read context/state and return the updated state."""
