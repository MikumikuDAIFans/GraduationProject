"""Assistant service layer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import re
from typing import Any, AsyncIterator, Sequence
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from loguru import logger
from pydantic import ValidationError

from app.assistant_agents import AssistantAgentContext, AssistantConductor, ConductorResult
from app.assistant_agents.contracts import (
    ContinuationSignals,
    OrchestrationAssessment,
    PlanningIntent,
    TargetScope,
)
from app.assistant_agents.specialists.memory import MemorySpecialist
from app.api.schemas import (
    AssistantCurrentSessionRead,
    AssistantAction,
    AssistantInboxItem,
    AssistantInboxRead,
    AssistantSummaryCard,
    AssistantSummaryRead,
    AssistantMessageCreate,
    AssistantMessageRead,
    AssistantResponse,
    AssistantSessionCreate,
    AssistantSessionListRead,
    AssistantSessionRead,
    AssistantSessionSummaryRead,
    AssistantMemoryCandidateCreate,
    AssistantProposalCreate,
    EventCreate,
    EventRead,
    TaskCreate,
)
from app.core.config import get_settings
from app.core.error_handler import AssistantError
from app.db.session import get_sessionmaker
from app.repositories.assistant import AssistantRepository
from app.repositories.assistant_thread_states import AssistantThreadStateRepository
from app.repositories.events import EventRepository
from app.repositories.profiles import UserProfileRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.tasks import TaskRepository
from app.services.context import ContextService
from app.services.events import EventService
from app.services.assistant_memory import AssistantMemoryService
from app.services.assistant_proposal_manager import AssistantProposalManager
from app.services.assistant_response_formatter import AssistantResponseFormatter
from app.services.assistant_runtime_context import AssistantContextRuntime
from app.services.assistant_runtime_plan import AssistantPlanRuntime
from app.services.assistant_runtime_session import AssistantSessionRuntime
from app.services.assistant_runtime_text import AssistantTextRuntime
from app.services.assistant_signal_manager import AssistantSignalManager
from app.services.suggestions import SuggestionService
from app.services.tasks import TaskService
from app.tools.gemini import GeminiClient

class AssistantService:
    """Assistant session/message orchestration with Gemini-backed planning."""

    INBOX_ARCHIVE_RETENTION_DAYS = 7
    TEXT_RUNTIME_METHOD_ALIASES = {
        "classify_intent": "_classify_intent",
        "build_rule_based_task_payload": "_build_rule_based_task_payload",
        "build_rule_based_event_payload": "_build_rule_based_event_payload",
        "build_schedule_guidance_reply": "_build_schedule_guidance_reply",
        "extract_time_range": "_extract_time_range",
        "extract_event_title": "_extract_event_title",
        "extract_location": "_extract_location",
        "extract_task_content": "_extract_task_content",
        "extract_requested_items": "_extract_requested_items",
        "prefers_chinese": "_prefers_chinese",
        "select_schedule_guidance_dates": "_select_schedule_guidance_dates",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        session_factory = get_sessionmaker()
        self.repository = AssistantRepository(session_factory)
        self.thread_state_repository = AssistantThreadStateRepository(session_factory)
        self.event_repository = EventRepository(session_factory)
        self.profile_repository = UserProfileRepository(session_factory)
        self.reminder_repository = ReminderRepository(session_factory)
        self.task_repository = TaskRepository(session_factory)
        self.context_service = ContextService()
        self.event_service = EventService()
        self.formatter = AssistantResponseFormatter()
        self.context_runtime = AssistantContextRuntime(self)
        self.plan_runtime = AssistantPlanRuntime(self)
        self.session_runtime = AssistantSessionRuntime(self)
        self.text_runtime = AssistantTextRuntime()
        self.memory_service = AssistantMemoryService()
        self.memory_specialist = MemorySpecialist()
        self.proposal_manager = AssistantProposalManager()
        self.signal_manager = AssistantSignalManager()
        self.gemini = GeminiClient()
        conductor_mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        self.conductor = (
            AssistantConductor.build_default(self.text_runtime, semantic_extractor=self.gemini)
            if conductor_mode in {"shadow", "proposal", "primary"}
            else None
        )
        self.suggestion_service = SuggestionService()
        self.task_service = TaskService()

    def __getattr__(self, name: str):
        """Delegate legacy text helper lookups to the extracted text runtime."""
        runtime_name = self.TEXT_RUNTIME_METHOD_ALIASES.get(name, name)
        runtime = object.__getattribute__(self, "text_runtime")
        if hasattr(runtime, runtime_name):
            return getattr(runtime, runtime_name)
        raise AttributeError(f"{self.__class__.__name__!s} object has no attribute {name!r}")

    async def send_message(self, user_id: str, payload: AssistantMessageCreate) -> AssistantResponse:
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assistant message cannot be empty")
        session = await self._resolve_session(user_id=user_id, session_id=payload.session_id)

        try:
            await self.repository.create_message(
                session_id=session.id,
                role="user",
                content=payload.message,
            )
            memory_conflict_reply = await self._maybe_handle_memory_conflict_message(
                user_id=user_id,
                user_message=payload.message,
            )
            if memory_conflict_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_conflict_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=memory_conflict_reply, actions=[])
            memory_protocol_reply = await self._maybe_handle_memory_candidate_text_protocol(
                user_id=user_id,
                user_message=payload.message,
            )
            if memory_protocol_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_protocol_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=memory_protocol_reply, actions=[])
            departure_signal_reply = await self._maybe_handle_departure_signal_reply(
                user_id=user_id,
                user_message=payload.message,
            )
            if departure_signal_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=departure_signal_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=departure_signal_reply, actions=[])
            departure_cancel_reply = await self._maybe_handle_departure_signal_cancel_reply(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
            )
            if departure_cancel_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=departure_cancel_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=departure_cancel_reply, actions=[])
            memory_candidates = await self._capture_memory_candidates_for_message(
                user_id=user_id,
                user_message=payload.message,
            )
            memory_only_reply = self._build_memory_only_reply(
                user_message=payload.message,
                memory_candidates=memory_candidates,
            )
            if memory_only_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_only_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=memory_only_reply, actions=[])

            history = await self.repository.list_messages(session.id)
            events = await self.event_repository.list_events(user_id=user_id)
            profile = await self.profile_repository.get_profile(user_id)
            tasks = await self.task_service.list_tasks(user_id=user_id)
            intent = self.text_runtime._classify_intent(payload.message)
            external_context = await self._build_external_context(
                profile=profile, user_message=payload.message, intent=intent,
            )
            external_context = await self._with_assistant_memory_context(
                user_id=user_id,
                external_context=external_context,
            )
            external_context = await self._with_active_target_context(
                user_id=user_id,
                session_id=session.id,
                external_context=external_context,
            )
            external_context["events"] = events
            session_context = dict(session.context_json or {})
            proposal_protocol_reply = await self._maybe_handle_proposal_text_protocol(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                external_context=external_context,
            )
            if proposal_protocol_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=proposal_protocol_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=proposal_protocol_reply, actions=[])
            daily_review_reply = await self._maybe_handle_daily_review_reply(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                events=events,
                tasks=tasks,
            )
            if daily_review_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=daily_review_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=daily_review_reply, actions=[])
            deterministic_reply = await self._maybe_handle_deterministic_acceptance_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
            )
            if deterministic_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=deterministic_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=deterministic_reply, actions=[])
            conductor_result = await self._run_conductor_for_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
            if self._should_use_conductor_reply(conductor_result):
                conductor_reply = self._format_conductor_reply(
                    conductor_result,
                    user_message=payload.message,
                    memory_candidates=memory_candidates,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=conductor_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=conductor_reply, actions=[])
            answer_plan = await self._maybe_build_orchestration_answer_plan(
                user_id=user_id,
                user_message=payload.message,
                conductor_result=conductor_result,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
            if answer_plan is not None:
                requested_actions = answer_plan.get("actions", [])
                actions = await self._execute_actions(
                    user_id=user_id,
                    actions=requested_actions,
                    user_message=payload.message,
                    existing_events=events,
                    profile=profile,
                )
                reply = self._format_reply_text(
                    answer_plan.get("reply") or "",
                    user_message=payload.message,
                )
                reply = self._append_memory_candidate_notice(
                    reply,
                    user_message=payload.message,
                    memory_candidates=memory_candidates,
                )
                await self._persist_pending_action(
                    user_id=user_id,
                    session_id=session.id,
                    existing_context=session_context,
                    actions=actions,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=reply,
                    tool_calls_json=[action.model_dump() for action in actions] or None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=reply, actions=actions)
            if self._should_block_legacy_fallback(
                conductor_result,
                user_message=payload.message,
                external_context=external_context,
            ):
                blocked_reply = self._format_reply_text(
                    self._primary_mode_fallback_reply(
                        payload.message,
                        conductor_result,
                        external_context=external_context,
                    ),
                    user_message=payload.message,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=blocked_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=blocked_reply, actions=[])

            pending_decision = await self._maybe_handle_pending_action_decision(
                user_id=user_id,
                session_id=session.id,
                session_context=session_context,
                user_message=payload.message,
                profile=profile,
            )
            if pending_decision is not None:
                pending_reply = self._format_reply_text(pending_decision.reply, user_message=payload.message)
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=pending_reply,
                    tool_calls_json=[action.model_dump() for action in pending_decision.actions] or None,
                )
                return AssistantResponse(
                    session_id=session.id,
                    reply=pending_reply,
                    actions=pending_decision.actions,
                )

            if not self._should_use_plan_compatibility_fallback(conductor_result):
                blocked_reply = self._format_reply_text(
                    self._primary_mode_fallback_reply(
                        payload.message,
                        conductor_result,
                        external_context=external_context,
                    ),
                    user_message=payload.message,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=blocked_reply,
                    tool_calls_json=None,
                )
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                return AssistantResponse(session_id=session.id, reply=blocked_reply, actions=[])

            plan = await self._build_plan(
                user_id=user_id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
                allow_answer_like_rule_short_circuit=self._should_allow_answer_like_rule_short_circuit(conductor_result),
            )
            requested_actions = plan.get("actions", [])
            actions = await self._execute_actions(
                user_id=user_id,
                actions=requested_actions,
                user_message=payload.message,
                existing_events=events,
                profile=profile,
            )
            reply = self._format_reply_text(
                self._compose_reply(
                    user_message=payload.message,
                    base_reply=plan.get("reply"),
                    actions=actions,
                    requested_actions=requested_actions,
                    fallback_message=payload.message,
                    event_count=len(events),
                    task_count=len(tasks),
                    external_context=external_context,
                ),
                user_message=payload.message,
            )
            reply = self._append_memory_candidate_notice(
                reply,
                user_message=payload.message,
                memory_candidates=memory_candidates,
            )

            await self._persist_pending_action(
                user_id=user_id,
                session_id=session.id,
                existing_context=session_context,
                actions=actions,
            )

            await self.repository.create_message(
                session_id=session.id,
                role="assistant",
                content=reply,
                tool_calls_json=[action.model_dump() for action in actions] or None,
            )

            await self._maybe_autorename_session(
                user_id=user_id,
                session_id=session.id,
                session_title=session.title,
                user_message=payload.message,
            )
            return AssistantResponse(session_id=session.id, reply=reply, actions=actions)
        except HTTPException:
            raise
        except Exception as exc:
            logger.bind(component="assistant").exception("Assistant send_message failed: {error}", error=str(exc))
            raise AssistantError("AI 助手暂时不可用，请稍后再试。", details={"reason": str(exc)}) from exc

    async def send_message_stream(
        self,
        user_id: str,
        payload: AssistantMessageCreate,
    ) -> AsyncIterator[dict[str, Any]]:
        if not payload.message or not payload.message.strip():
            yield {"type": "error", "text": "assistant message cannot be empty"}
            return
        session = await self._resolve_session(user_id=user_id, session_id=payload.session_id)

        try:
            await self.repository.create_message(
                session_id=session.id,
                role="user",
                content=payload.message,
            )
            memory_conflict_reply = await self._maybe_handle_memory_conflict_message(
                user_id=user_id,
                user_message=payload.message,
            )
            if memory_conflict_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_conflict_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(memory_conflict_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "done", "session_id": session.id, "full_reply": memory_conflict_reply}
                return
            memory_protocol_reply = await self._maybe_handle_memory_candidate_text_protocol(
                user_id=user_id,
                user_message=payload.message,
            )
            if memory_protocol_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_protocol_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(memory_protocol_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "done", "session_id": session.id, "full_reply": memory_protocol_reply}
                return
            departure_signal_reply = await self._maybe_handle_departure_signal_reply(
                user_id=user_id,
                user_message=payload.message,
            )
            if departure_signal_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=departure_signal_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(departure_signal_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "done", "session_id": session.id, "full_reply": departure_signal_reply}
                return
            departure_cancel_reply = await self._maybe_handle_departure_signal_cancel_reply(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
            )
            if departure_cancel_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=departure_cancel_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(departure_cancel_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "done", "session_id": session.id, "full_reply": departure_cancel_reply}
                return
            memory_candidates = await self._capture_memory_candidates_for_message(
                user_id=user_id,
                user_message=payload.message,
            )
            memory_only_reply = self._build_memory_only_reply(
                user_message=payload.message,
                memory_candidates=memory_candidates,
            )
            if memory_only_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=memory_only_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(memory_only_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": memory_only_reply}
                return

            history = await self.repository.list_messages(session.id)
            events = await self.event_repository.list_events(user_id=user_id)
            profile = await self.profile_repository.get_profile(user_id)
            tasks = await self.task_service.list_tasks(user_id=user_id)
            intent = self.text_runtime._classify_intent(payload.message)
            external_context = await self._build_external_context(
                profile=profile, user_message=payload.message, intent=intent,
            )
            external_context = await self._with_assistant_memory_context(
                user_id=user_id,
                external_context=external_context,
            )
            external_context = await self._with_active_target_context(
                user_id=user_id,
                session_id=session.id,
                external_context=external_context,
            )
            external_context["events"] = events
            session_context = dict(session.context_json or {})
            proposal_protocol_reply = await self._maybe_handle_proposal_text_protocol(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                external_context=external_context,
            )
            if proposal_protocol_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=proposal_protocol_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(proposal_protocol_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": proposal_protocol_reply}
                return
            daily_review_reply = await self._maybe_handle_daily_review_reply(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                events=events,
                tasks=tasks,
            )
            if daily_review_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=daily_review_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(daily_review_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": daily_review_reply}
                return
            deterministic_reply = await self._maybe_handle_deterministic_acceptance_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
            )
            if deterministic_reply is not None:
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=deterministic_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(deterministic_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": deterministic_reply}
                return
            conductor_result = await self._run_conductor_for_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
            if self._should_use_conductor_reply(conductor_result):
                conductor_reply = self._format_conductor_reply(
                    conductor_result,
                    user_message=payload.message,
                    memory_candidates=memory_candidates,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=conductor_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(conductor_reply):
                    yield {"type": "token", "text": chunk}
                await self._maybe_autorename_session(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    user_message=payload.message,
                )
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": conductor_reply}
                return
            answer_plan = await self._maybe_build_orchestration_answer_plan(
                user_id=user_id,
                user_message=payload.message,
                conductor_result=conductor_result,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
            if answer_plan is not None:
                requested_actions = answer_plan.get("actions", [])
                actions = await self._execute_actions(
                    user_id=user_id,
                    actions=requested_actions,
                    user_message=payload.message,
                    existing_events=events,
                    profile=profile,
                )
                reply_text = self._format_reply_text(
                    answer_plan.get("reply") or "",
                    user_message=payload.message,
                )
                reply_text = self._append_memory_candidate_notice(
                    reply_text,
                    user_message=payload.message,
                    memory_candidates=memory_candidates,
                )
                await self._persist_pending_action(
                    user_id=user_id,
                    session_id=session.id,
                    existing_context=session_context,
                    actions=actions,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=reply_text,
                    tool_calls_json=[action.model_dump() for action in actions] or None,
                )
                for chunk in self._chunk_text(reply_text):
                    yield {"type": "token", "text": chunk}
                yield {"type": "actions", "actions": [action.model_dump() for action in actions]}
                yield {"type": "done", "session_id": session.id, "full_reply": reply_text}
                return
            if self._should_block_legacy_fallback(
                conductor_result,
                user_message=payload.message,
                external_context=external_context,
            ):
                blocked_reply = self._format_reply_text(
                    self._primary_mode_fallback_reply(
                        payload.message,
                        conductor_result,
                        external_context=external_context,
                    ),
                    user_message=payload.message,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=blocked_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(blocked_reply):
                    yield {"type": "token", "text": chunk}
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": blocked_reply}
                return

            pending_decision = await self._maybe_handle_pending_action_decision(
                user_id=user_id,
                session_id=session.id,
                session_context=session_context,
                user_message=payload.message,
                profile=profile,
            )
            if pending_decision is not None:
                pending_reply = self._format_reply_text(pending_decision.reply, user_message=payload.message)
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=pending_reply,
                    tool_calls_json=[action.model_dump() for action in pending_decision.actions] or None,
                )
                for chunk in self._chunk_text(pending_reply):
                    yield {"type": "token", "text": chunk}
                yield {"type": "actions", "actions": [action.model_dump() for action in pending_decision.actions]}
                yield {"type": "done", "session_id": session.id, "full_reply": pending_reply}
                return

            if not self._should_use_plan_compatibility_fallback(conductor_result):
                blocked_reply = self._format_reply_text(
                    self._primary_mode_fallback_reply(
                        payload.message,
                        conductor_result,
                        external_context=external_context,
                    ),
                    user_message=payload.message,
                )
                await self.repository.create_message(
                    session_id=session.id,
                    role="assistant",
                    content=blocked_reply,
                    tool_calls_json=None,
                )
                for chunk in self._chunk_text(blocked_reply):
                    yield {"type": "token", "text": chunk}
                yield {"type": "actions", "actions": []}
                yield {"type": "done", "session_id": session.id, "full_reply": blocked_reply}
                return

            full_reply = ""
            used_streaming = False
            if self._should_use_streaming_plan_fallback(conductor_result):
                try:
                    async for chunk in self.gemini.generate_plan_stream(
                        user_message=payload.message,
                        history=[{"role": message.role, "content": message.content} for message in history[-6:]],
                        events=[EventRead.model_validate(event).model_dump(mode="json") for event in events[:8]],
                        tasks=[task.model_dump(mode="json") if hasattr(task, "model_dump") else {} for task in tasks[:8]],
                        profile=profile.__dict__ if profile else None,
                        external_context=external_context,
                    ):
                        used_streaming = True
                        full_reply += chunk
                        yield {"type": "token", "text": chunk}
                except Exception as exc:
                    logger.bind(component="assistant.stream").warning("Gemini stream failed: {error}", error=str(exc))
                    full_reply = ""
                    used_streaming = False

            if used_streaming and full_reply.strip():
                try:
                    plan = self.gemini._parse_json_payload(full_reply)
                    requested_actions = plan.get("actions", [])
                    actions = await self._execute_actions(
                        user_id=user_id,
                        actions=requested_actions,
                        user_message=payload.message,
                        existing_events=events,
                        profile=profile,
                    )
                    reply_text = self._compose_reply(
                        user_message=payload.message,
                        base_reply=plan.get("reply"),
                        actions=actions,
                        requested_actions=requested_actions,
                        fallback_message=payload.message,
                        event_count=len(events),
                        task_count=len(tasks),
                        external_context=external_context,
                    )
                except Exception:
                    reply_text = full_reply
                    actions = []
            else:
                plan = await self._build_plan(
                    user_id=user_id,
                    user_message=payload.message,
                    history=history,
                    events=events,
                    tasks=tasks,
                    profile=profile,
                    external_context=external_context,
                    allow_answer_like_rule_short_circuit=self._should_allow_answer_like_rule_short_circuit(conductor_result),
                )
                requested_actions = plan.get("actions", [])
                actions = await self._execute_actions(
                    user_id=user_id,
                    actions=requested_actions,
                    user_message=payload.message,
                    existing_events=events,
                    profile=profile,
                )
                reply_text = self._compose_reply(
                    user_message=payload.message,
                    base_reply=plan.get("reply"),
                    actions=actions,
                    requested_actions=requested_actions,
                    fallback_message=payload.message,
                    event_count=len(events),
                    task_count=len(tasks),
                    external_context=external_context,
                )

            reply_text = self._format_reply_text(reply_text, user_message=payload.message)
            reply_text = self._append_memory_candidate_notice(
                reply_text,
                user_message=payload.message,
                memory_candidates=memory_candidates,
            )
            if not used_streaming or not full_reply.strip():
                for chunk in self._chunk_text(reply_text):
                    yield {"type": "token", "text": chunk}

            await self._persist_pending_action(
                user_id=user_id,
                session_id=session.id,
                existing_context=session_context,
                actions=actions,
            )

            await self.repository.create_message(
                session_id=session.id,
                role="assistant",
                content=reply_text,
                tool_calls_json=[action.model_dump() for action in actions] or None,
            )

            await self._maybe_autorename_session(
                user_id=user_id,
                session_id=session.id,
                session_title=session.title,
                user_message=payload.message,
            )

            yield {"type": "actions", "actions": [action.model_dump() for action in actions]}
            yield {"type": "done", "session_id": session.id, "full_reply": reply_text}
        except HTTPException:
            raise
        except Exception as exc:
            logger.bind(component="assistant.stream").exception("Assistant send_message_stream failed: {error}", error=str(exc))
            yield {"type": "error", "text": "AI 助手暂时不可用，请稍后再试。"}

    async def create_session(self, user_id: str, payload: AssistantSessionCreate) -> AssistantSessionRead:
        session = await self.repository.create_session(
            user_id=user_id,
            session_type="chat",
            title=payload.title,
            context_json={"status": "assistant-active"},
        )
        return await self.get_session(user_id=user_id, session_id=session.id)

    async def list_sessions(self, user_id: str, limit: int = 20) -> AssistantSessionListRead:
        sessions = await self.repository.list_active_sessions(user_id=user_id, limit=limit)
        items = [
            AssistantSessionSummaryRead(
                id=session.id,
                user_id=session.user_id,
                session_type=session.session_type,
                title=getattr(session, "title", "New chat"),
                is_archived=getattr(session, "is_archived", False),
                context_json=session.context_json,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        ]
        return AssistantSessionListRead(items=items, total=len(items))

    async def archive_session(self, user_id: str, session_id: int) -> dict[str, bool]:
        return {"success": await self.repository.archive_session(session_id, user_id=user_id)}

    async def clear_session_messages(self, user_id: str, session_id: int) -> dict[str, bool]:
        return {"success": await self.repository.clear_session_messages(session_id, user_id=user_id)}

    async def _resolve_session(self, *, user_id: str, session_id: int | None):
        if session_id is None:
            current = await self.get_current_session(user_id=user_id)
            session = await self.repository.get_session(current.session.id, user_id=user_id)
        else:
            session = await self.repository.get_session(session_id, user_id=user_id)
        if session is None or getattr(session, "is_archived", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assistant session not found")
        return session

    def _coerce_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _ensure_assistant_action(self, action: Any) -> AssistantAction:
        if isinstance(action, AssistantAction):
            return action
        if isinstance(action, dict):
            return AssistantAction.model_validate(action)
        raise TypeError(f"Unsupported assistant action type: {type(action)!r}")

    async def _capture_memory_candidates_for_message(
        self,
        *,
        user_id: str,
        user_message: str,
    ) -> list[Any]:
        """Persist explicit long-term memory requests as confirmable candidates only."""
        candidate_payloads = self._extract_multiple_memory_candidates(user_message)
        if not candidate_payloads:
            candidate_payload = self.memory_specialist.extract_candidate(user_message)
            candidate_payloads = [candidate_payload] if candidate_payload is not None else []
        if not candidate_payloads:
            return []

        candidates: list[Any] = []
        try:
            for candidate_payload in candidate_payloads:
                payload = AssistantMemoryCandidateCreate.model_validate(candidate_payload)
                candidate = await self.memory_service.create_candidate(user_id=user_id, payload=payload)
                logger.bind(component="assistant.memory").info(
                    "Created assistant memory candidate: {candidate_id}",
                    candidate_id=candidate.id,
                )
                candidates.append(candidate)
            return candidates
        except Exception as exc:
            logger.bind(component="assistant.memory").warning(
                "Failed to create assistant memory candidate: {error}",
                error=str(exc),
            )
            return []

    def _extract_multiple_memory_candidates(self, user_message: str) -> list[dict[str, Any]]:
        text = user_message.strip()
        if not text.startswith("以后") or "，" not in text:
            return []
        fragments = [part.strip(" ，。,；;") for part in re.split(r"[，,；;]", text) if part.strip(" ，。,；;")]
        candidates: list[dict[str, Any]] = []
        for index, fragment in enumerate(fragments):
            candidate_text = fragment if fragment.startswith("以后") else f"以后{fragment}"
            candidate = self.memory_specialist.extract_candidate(candidate_text)
            if candidate is not None:
                candidates.append(candidate)
                continue
            sleep_match = re.search(r"(?:我)?一般(?P<habit>晚上\d{1,2}点睡|早上\d{1,2}点起|[\u4e00-\u9fa5A-Za-z0-9]+)", fragment)
            if sleep_match:
                content = sleep_match.group("habit").strip()
                digest_source = f"habits:{content}"
                import hashlib
                digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
                candidates.append(
                    {
                        "memory_type": "habits",
                        "source_specialist": self.memory_specialist.name,
                        "status": "proposed",
                        "confidence": 0.72,
                        "proposed_change_json": {
                            "operation": "append_entry",
                            "title": content,
                            "content": content,
                        },
                        "reason": "User explicitly described a recurring habit.",
                        "dedup_key": f"memory:habits:{digest}",
                    }
                )
        return candidates

    async def _maybe_handle_memory_conflict_message(
        self,
        *,
        user_id: str,
        user_message: str,
    ) -> str | None:
        candidate_payload = self.memory_specialist.extract_candidate(user_message)
        if candidate_payload is None:
            return None
        memory_type = candidate_payload.get("memory_type")
        if memory_type != "places":
            return None
        proposed_change = candidate_payload.get("proposed_change_json") or {}
        content = str(proposed_change.get("content") or "").strip()
        if "=" not in content:
            return None
        alias, target = [part.strip() for part in content.split("=", 1)]
        if not alias or not target:
            return None

        try:
            memory_context = await self.memory_service.build_runtime_context(user_id=user_id)
        except Exception:
            memory_context = {}
        existing_aliases = self.memory_service.extract_place_aliases(memory_context)
        for item in existing_aliases:
            if item.get("alias", "").strip() != alias:
                continue
            old_target = item.get("location_name", "").strip()
            if old_target and old_target != target:
                return (
                    f"你之前把“{alias}”记成“{old_target}”，"
                    f"这次想改成“{target}”。要替换旧记忆吗？"
                )
            if old_target == target:
                return f"“{alias}”已经记成“{target}”，这次不用重复写入。"
        return None

    async def _maybe_handle_memory_candidate_text_protocol(
        self,
        *,
        user_id: str,
        user_message: str,
    ) -> str | None:
        normalized = re.sub(r"\s+", "", (user_message or "").strip())
        if not normalized:
            return None

        confirm_markers = {"记住", "记一下", "保存", "确认记住", "保存这条", "保存这个", "记下来", "记这个"}
        reject_markers = {"不要记", "别记", "不用记", "先别记", "别保存", "不要保存"}
        if not any(marker == normalized or normalized.startswith(marker) for marker in confirm_markers | reject_markers):
            return None

        candidates = await self.memory_service.list_candidates(user_id=user_id, statuses=["proposed"], limit=10)
        if not candidates:
            if any(marker == normalized or normalized.startswith(marker) for marker in reject_markers):
                return "当前没有待确认记忆可拒绝。"
            return "当前没有待确认记忆可保存。"
        if len(candidates) > 1:
            return "我不确定你要确认哪条记忆，请先在待确认记忆区选择对应候选，或补充说明要保存的内容。"

        candidate = candidates[0]
        if any(marker == normalized or normalized.startswith(marker) for marker in reject_markers):
            rejected = await self.memory_service.reject_candidate(user_id=user_id, candidate_id=candidate.id)
            label = self._describe_memory_candidate(rejected)
            return f"已拒绝这条待确认记忆：{label}。"

        written = await self.memory_service.confirm_candidate(user_id=user_id, candidate_id=candidate.id)
        label = self._describe_memory_candidate(written)
        return f"已确认并写入长期记忆：{label}。"

    def _describe_memory_candidate(self, candidate) -> str:
        change = getattr(candidate, "proposed_change_json", None) or {}
        title = str(change.get("title") or "").strip()
        content = str(change.get("content") or "").strip()
        if title and content:
            return f"{title}（{content}）"
        return title or content or f"{getattr(candidate, 'memory_type', 'memory')} 记忆"

    def _build_memory_only_reply(
        self,
        *,
        user_message: str,
        memory_candidates: list[Any],
    ) -> str | None:
        if not memory_candidates or not self.memory_specialist.is_explicit_memory_request(user_message):
            return None
        if self.text_runtime._prefers_chinese(user_message):
            reply = "我已经理解这是一个长期记忆请求，这次不会创建任务或日程。"
        else:
            reply = "I understood this as a long-term memory request, so I will not create a task or event from it."
        return self._append_memory_candidate_notice(
            reply,
            user_message=user_message,
            memory_candidates=memory_candidates,
        )

    def _append_memory_candidate_notice(
        self,
        reply: str,
        *,
        user_message: str,
        memory_candidates: list[Any],
    ) -> str:
        if not memory_candidates:
            return reply
        prefers_chinese = self.text_runtime._prefers_chinese(user_message)
        count = len(memory_candidates)
        if prefers_chinese:
            notice = (
                "我已经把这条内容放进“待确认记忆”，你确认后我才会写入长期记忆。"
                if count == 1
                else f"我已经生成 {count} 条待确认记忆，你确认后我才会写入长期记忆。"
            )
        else:
            notice = (
                "I added this to pending memories. I will only save it after you confirm."
                if count == 1
                else f"I added {count} pending memories. I will only save them after you confirm."
            )
        base = (reply or "").strip()
        return f"{base}\n\n{notice}" if base else notice

    async def _with_assistant_memory_context(
        self,
        *,
        user_id: str,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            memory_context = await self.memory_service.build_runtime_context(user_id=user_id)
        except Exception as exc:
            logger.bind(component="assistant.memory").warning(
                "Failed to read assistant memory context: {error}",
                error=str(exc),
            )
            return dict(external_context or {})
        if not memory_context:
            return dict(external_context or {})
        enriched = dict(external_context or {})
        enriched["assistant_memory"] = memory_context
        return enriched

    async def _with_active_target_context(
        self,
        *,
        user_id: str,
        session_id: int,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(external_context or {})
        try:
            thread_state = await self.thread_state_repository.get_active_target_state(
                user_id=user_id,
                session_id=session_id,
            )
        except Exception as exc:
            logger.bind(component="assistant.thread_state").warning(
                "Failed to read active target thread state: {error}",
                error=str(exc),
            )
            return enriched
        if thread_state is None:
            return enriched
        state_json = thread_state.state_json or {}
        active_target = state_json.get("active_target") if isinstance(state_json, dict) else None
        if not isinstance(active_target, dict):
            return enriched
        enriched["active_target"] = {
            **active_target,
            "thread_state_id": thread_state.id,
            "thread_state_updated_at": thread_state.updated_at.isoformat() if thread_state.updated_at else None,
        }
        return enriched

    async def _maybe_handle_proposal_text_protocol(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        external_context: dict[str, Any],
    ) -> str | None:
        intent = self._classify_proposal_text_protocol(user_message)
        if intent is None:
            if not hasattr(self.proposal_manager, "list_proposals"):
                return None
            active = await self._list_text_protocol_proposals(
                user_id=user_id,
                session_id=session_id,
                statuses=["pending"],
                limit=10,
            )
            if self._looks_like_event_targeted_reschedule_request(
                user_message,
                events=(external_context or {}).get("events"),
            ):
                return None
            if active and self._looks_like_contextual_event_creation_directive(user_message):
                return self._build_existing_event_creation_proposal_reply(active, user_message=user_message)
            if not active or not self._looks_like_contextual_proposal_revision(user_message):
                return None
            intent = "revise"
        proposal = await self._resolve_text_protocol_proposal(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            external_context=external_context,
        )
        assessment = self._build_proposal_protocol_assessment(
            user_message=user_message,
            intent=intent,
            proposal=proposal,
            external_context=external_context,
        )
        if proposal == "ambiguous":
            return self._build_proposal_protocol_clarification(user_message)
        if proposal is None:
            return self._build_missing_proposal_protocol_reply(
                user_message=user_message,
                intent=intent,
                assessment=assessment,
            )
        if intent == "revise" and not self._proposal_supports_contextual_revision(proposal, user_message):
            return None

        proposal_status = getattr(proposal, "status", None)
        if intent == "confirm" and proposal_status == "expired":
            if self.text_runtime._prefers_chinese(user_message):
                return "这个方案已经过期，不能再执行；我不会写入任何日程或任务。请重新说明需求，我可以生成新的待确认方案。"
            return "This proposal has expired and cannot be executed. I did not write any data; please describe the request again for a new proposal."
        if intent == "confirm" and proposal_status == "superseded":
            if self.text_runtime._prefers_chinese(user_message):
                return "这个方案已经被新的方案替代，不能再执行；请确认最新方案，或重新生成方案。"
            return "This proposal has been superseded and cannot be executed. Please confirm the latest proposal or regenerate one."

        if intent == "reject":
            rejected = await self.proposal_manager.reject_proposal(
                user_id=user_id,
                proposal_id=int(proposal.id),
            )
            await self._persist_active_target_for_proposal(
                user_id=user_id,
                session_id=session_id,
                proposal=rejected,
                user_message=user_message,
            )
            if self.text_runtime._prefers_chinese(user_message):
                return "已暂不安排这个方案，没有执行任何写入。"
            return "I rejected this proposal and did not write anything."

        if intent == "revise":
            revised = await self.proposal_manager.revise_proposal(
                user_id=user_id,
                proposal_id=int(proposal.id),
                message=user_message,
            )
            await self._persist_active_target_for_proposal(
                user_id=user_id,
                session_id=session_id,
                proposal=revised,
                user_message=user_message,
            )
            if self.text_runtime._prefers_chinese(user_message):
                return "我已根据你的修改生成新的待确认方案，旧方案不会再执行。"
            return "I created a revised pending proposal and superseded the previous one."

        if getattr(proposal, "status", None) == "executed":
            if self.text_runtime._prefers_chinese(user_message):
                return "这个方案已经执行完成，不会重复写入。需要新安排的话，请直接告诉我要安排什么。"
            return "This proposal has already been executed, so I will not write it again."
        if getattr(proposal, "status", None) == "execution_failed":
            return self._build_proposal_execution_failed_reply(proposal, user_message=user_message)

        option_id = (
            self._extract_proposal_option_id(user_message)
            or proposal.recommended_option_id
            or self._first_proposal_option_id(proposal.payload_json or {})
        )
        try:
            if not option_id:
                return None
            confirmed = await self.proposal_manager.confirm_proposal(
                user_id=user_id,
                proposal_id=int(proposal.id),
                option_id=option_id,
            )
            await self._persist_active_target_for_proposal(
                user_id=user_id,
                session_id=session_id,
                proposal=confirmed,
                user_message=user_message,
            )
        except HTTPException as exc:
            failed_proposal = await self.proposal_manager.get_proposal(
                user_id=user_id,
                proposal_id=int(proposal.id),
            )
            if getattr(failed_proposal, "status", None) == "pending" and str(exc.detail) == "option not found":
                if self.text_runtime._prefers_chinese(user_message):
                    return f"这个方案没有方案 {option_id}；请改用已有选项，或先让我重新生成方案。"
                return f"This proposal does not have option {option_id}; please choose an existing option or regenerate it."
            if getattr(failed_proposal, "status", None) == "execution_failed":
                await self._persist_active_target_for_proposal(
                    user_id=user_id,
                    session_id=session_id,
                    proposal=failed_proposal,
                    user_message=user_message,
                )
                return self._build_proposal_execution_failed_reply(failed_proposal, user_message=user_message)
            raise
        except Exception as exc:
            logger.bind(component="assistant.thread_state").warning(
                "Failed to confirm active proposal from text: {error}",
                error=str(exc),
            )
            return None

        if getattr(confirmed, "status", None) == "execution_failed":
            return self._build_proposal_execution_failed_reply(confirmed, user_message=user_message)

        if self.text_runtime._prefers_chinese(user_message):
            return "已按这个方案确认并执行。"
        return "Confirmed and executed this proposal."

    def _build_proposal_execution_failed_reply(self, proposal: Any, *, user_message: str) -> str:
        error = getattr(proposal, "execution_error", None)
        if not error:
            payload = getattr(proposal, "payload_json", None) or {}
            execution = payload.get("execution") if isinstance(payload, dict) else None
            if isinstance(execution, dict):
                error = execution.get("last_error")
        error_text = str(error or "执行失败")
        if self.text_runtime._prefers_chinese(user_message):
            return f"方案执行失败：{error_text}。我没有重复执行；请修正问题后使用重试入口重新尝试。"
        return f"The proposal execution failed: {error_text}. I did not repeat execution; use retry after fixing the issue."

    async def _maybe_confirm_active_proposal_from_text(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        external_context: dict[str, Any],
    ) -> str | None:
        return await self._maybe_handle_proposal_text_protocol(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            external_context=external_context,
        )

    async def _maybe_handle_daily_review_reply(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        events: list[Any],
        tasks: list[Any],
    ) -> str | None:
        message = user_message.strip()
        batch_done = bool(re.search(r"(今天)?这两个都完成了?|两个都完成了?", message))
        mixed = bool(
            re.search(r"政治课.{0,8}完成", message)
            and re.search(r"复习.{0,8}(没做|没完成|未完成|没弄|没搞)", message)
        )
        if not batch_done and not mixed:
            return None

        politics_event = self._find_daily_review_event(events, "政治课")
        review_task = self._find_daily_review_task(tasks, "复习")
        if politics_event is None or review_task is None:
            missing = []
            if politics_event is None:
                missing.append("政治课")
            if review_task is None:
                missing.append("复习块")
            return f"我理解你在回应睡前复盘，但还不能唯一定位：{'、'.join(missing)}。请直接说清楚要标记完成或顺延的事项。"

        event_id = int(getattr(politics_event, "id"))
        task_id = int(getattr(review_task, "id"))
        if batch_done:
            summary = "建议将睡前复盘中的“政治课”和“复习块”分别标记为完成"
            actions = [
                {"type": "mark_event_completed", "payload": {"event_id": event_id}},
                {"type": "mark_task_completed", "payload": {"task_id": task_id}},
            ]
            rationale = "确认后会分别更新一次日程和任务状态，不会重复写入。"
            reply = (
                "我已把这两个事项整理成可确认的完成方案：政治课标记为完成，复习块标记为完成。"
                "确认后才会分别更新一次。"
            )
        else:
            summary = "建议将“政治课”标记完成，并将“复习块”保留为未完成待补排"
            actions = [
                {"type": "mark_event_completed", "payload": {"event_id": event_id}},
                {
                    "type": "acknowledge_signal",
                    "payload": {
                        "signal_type": "daily_review_unfinished_task",
                        "message": "复习块今天未完成，需要后续协商补排。",
                        "task_id": task_id,
                    },
                },
            ]
            rationale = "确认后只会把政治课标记完成；复习块不会被误标完成，会进入后续补排协商。"
            reply = (
                "我已把混合结果整理成可确认方案：政治课走完成确认，复习块保留为未完成并后续补排协商。"
                "确认前不会把两个事项都标记完成。"
            )

        proposal = await self.proposal_manager.create_proposal(
            user_id=user_id,
            payload=AssistantProposalCreate(
                session_id=session_id,
                proposal_type="daily_review_status_update",
                trigger_type="user_message",
                status="pending",
                summary=summary,
                payload_json={
                    "source": "daily_review_reply",
                    "target_title": "睡前复盘",
                    "options": [
                        {
                            "option_id": "A",
                            "title": "按睡前复盘结果更新",
                            "summary": summary,
                            "actions": actions,
                            "rationale": rationale,
                        }
                    ],
                },
                recommended_option_id="A",
                related_event_id=event_id,
                related_task_id=task_id,
            ),
        )
        await self._persist_active_target_for_proposal(
            user_id=user_id,
            session_id=session_id,
            proposal=proposal,
            user_message=user_message,
        )
        return f"{reply}\n\n我已把方案放进“待确认方案”，你确认后我才会执行写入。"

    def _find_daily_review_event(self, events: list[Any], keyword: str) -> Any | None:
        today = datetime.now(ZoneInfo(self.settings.app_timezone)).date()
        matches = [
            event
            for event in events
            if keyword in str(getattr(event, "title", ""))
            and (getattr(event, "status", None) or "planned") not in {"canceled", "completed"}
            and getattr(getattr(event, "start_time", None), "date", lambda: None)() == today
        ]
        return matches[0] if len(matches) == 1 else None

    def _find_daily_review_task(self, tasks: list[Any], keyword: str) -> Any | None:
        matches = [
            task
            for task in tasks
            if keyword in str(getattr(task, "content", ""))
            and (getattr(task, "status", None) or "pending") not in {"done", "completed", "archived"}
        ]
        return matches[0] if len(matches) == 1 else None

    async def _maybe_handle_deterministic_acceptance_message(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        history: list[Any] | None = None,
        events: list[Any],
    ) -> str | None:
        message = user_message.strip()
        departure_reply = self._maybe_build_deterministic_departure_context_reply(
            user_message=message,
            history=history or [],
        )
        if departure_reply is not None:
            return departure_reply
        if re.search(r"看看今天安排|看一下今天安排|今天安排", message):
            return "今天安排我可以帮你查看和梳理；如果要新增、调整或取消某个事项，请直接说明具体时间和内容。"
        if re.fullmatch(r"帮我安排一下复习[。！!]*", message):
            return "这个复习安排还缺少截止时间、预计时长或希望安排到哪天。请补充这些具体信息后，我再生成待确认方案。"

        batch_reply = await self._maybe_create_deterministic_batch_event_proposal(
            user_id=user_id,
            session_id=session_id,
            user_message=message,
            events=events,
        )
        if batch_reply is not None:
            return batch_reply

        timed_reply = await self._maybe_create_deterministic_timed_reminder_proposal(
            user_id=user_id,
            session_id=session_id,
            user_message=message,
        )
        if timed_reply is not None:
            return timed_reply

        event_reply = await self._maybe_create_deterministic_event_proposal(
            user_id=user_id,
            session_id=session_id,
            user_message=message,
            events=events,
        )
        if event_reply is not None:
            return event_reply

        return None

    def _maybe_build_deterministic_departure_context_reply(
        self,
        *,
        user_message: str,
        history: list[Any],
    ) -> str | None:
        if not re.search(r"几点出发|多久出发|什么时候出发|要提前多久|通勤|怎么去", user_message):
            return None
        runtime_origin = self._recent_runtime_origin_from_history(history)
        location_match = re.search(
            r"(?:去|到|在)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}?)(?=上课|开会|会议|办手续|体检|面试|聚餐|见面|[，。,；;!！?？]|$)",
            user_message,
        )
        location_name = location_match.group("location").strip() if location_match else None
        if runtime_origin:
            destination = location_name or "目的地"
            return (
                f"我会优先按你刚说的“{runtime_origin}”作为出发地，目的地按“{destination}”理解。"
                "这只是当前对话里的临时位置，不会写入长期地点记忆；如果要精确到分钟，请补充交通方式或允许我使用通勤数据。"
            )
        if location_name:
            return f"我知道目的地是“{location_name}”，但还不能判断你届时从哪里出发。请补充出发地，我不会直接写入日程或长期记忆。"
        return None

    async def _maybe_create_deterministic_batch_event_proposal(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        events: list[Any],
    ) -> str | None:
        if not re.search(r"(所有|全部|全都).{0,8}(日程|安排|会议|活动)|(?:日程|安排|会议|活动).{0,8}(所有|全部|全都)", user_message):
            return None
        if "明天" not in user_message:
            return "这个批量操作范围还不够明确。请说明具体日期、对象和要改成什么，我再生成待确认方案。"

        target_date = self.text_runtime._extract_target_date(
            user_message,
            datetime.now(ZoneInfo(self.settings.app_timezone)).date(),
        )
        target_events = [
            event
            for event in events
            if (getattr(event, "status", None) or "planned") != "canceled"
            and getattr(getattr(event, "start_time", None), "date", lambda: None)() == target_date
        ]
        if len(target_events) > 8:
            return f"明天共有 {len(target_events)} 个安排，范围过大。请缩小范围或明确列出要处理的项目，我不会直接批量执行。"
        if not target_events:
            return "我没有找到明天可批量处理的日程。请确认日期或具体事项。"
        if re.search(r"取消|删除|删掉", user_message):
            if len(target_events) > 5:
                return f"明天共有 {len(target_events)} 个安排，取消范围过大。请先缩小范围，我不会直接批量取消。"
            actions = [{"type": "cancel_event", "payload": {"event_id": int(getattr(event, "id"))}} for event in target_events]
            summary = f"建议取消明天的 {len(target_events)} 个日程"
            proposal_type = "event_batch_cancel"
        elif re.search(r"推迟|延期|延后|顺延", user_message):
            actions = []
            for event in target_events:
                start_time = getattr(event, "start_time", None)
                end_time = getattr(event, "end_time", None)
                if start_time is None or end_time is None or getattr(event, "id", None) is None:
                    return None
                actions.append(
                    {
                        "type": "reschedule_event",
                        "payload": {
                            "event_id": int(getattr(event, "id")),
                            "update": {
                                "start_time": (start_time + timedelta(days=1)).isoformat(),
                                "end_time": (end_time + timedelta(days=1)).isoformat(),
                            },
                        },
                    }
                )
            summary = f"建议把明天的 {len(target_events)} 个日程整体推迟 1 天"
            proposal_type = "event_batch_reschedule"
        else:
            return "这个批量调整还缺少具体动作。请说明要推迟、提前、改期还是取消，我再生成待确认方案。"

        proposal = await self.proposal_manager.create_proposal(
            user_id=user_id,
            payload=AssistantProposalCreate(
                session_id=session_id,
                proposal_type=proposal_type,
                trigger_type="user_message",
                status="pending",
                summary=summary,
                payload_json={
                    "source": "deterministic_acceptance_rule",
                    "target_scope": "batch",
                    "target_date": target_date.isoformat(),
                    "target_event_ids": [int(getattr(event, "id")) for event in target_events if getattr(event, "id", None) is not None],
                    "options": [
                        {
                            "option_id": "A",
                            "title": "按建议处理这批日程",
                            "summary": summary,
                            "actions": actions,
                            "rationale": "确认后才会逐个执行这些批量动作。",
                        }
                    ],
                },
                recommended_option_id="A",
                is_time_sensitive=True,
            ),
        )
        proposal = await self._label_direct_proposal(user_id=user_id, session_id=session_id, proposal=proposal)
        await self._persist_active_target_for_proposal(
            user_id=user_id,
            session_id=session_id,
            proposal=proposal,
            user_message=user_message,
        )
        label = self._proposal_protocol_label(proposal) or "P1"
        return f"{label}：{summary}。我已放入待确认方案，确认前不会写入或修改日程。"

    async def _maybe_create_deterministic_timed_reminder_proposal(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
    ) -> str | None:
        if not re.search(r"提醒我|记得叫我|提醒一下", user_message):
            return None
        start_time, end_time = self.text_runtime._extract_time_range(
            user_message,
            reference=datetime.now(ZoneInfo(self.settings.app_timezone)),
        )
        if start_time is None:
            return None
        location_match = re.search(r"(?:去|到|在|于)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24})(?:$|[，。,；;!！?？])", user_message)
        location_name = location_match.group("location").strip() if location_match else None
        if not location_name:
            return None
        title = f"去{location_name}"
        end_time = end_time or start_time + timedelta(hours=1)
        summary = f"建议创建日程“{title}”：{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}，地点：{location_name}"
        proposal = await self.proposal_manager.create_proposal(
            user_id=user_id,
            payload=AssistantProposalCreate(
                session_id=session_id,
                proposal_type="event_creation",
                trigger_type="user_message",
                status="pending",
                summary=summary,
                payload_json={
                    "source": "deterministic_timed_reminder",
                    "options": [
                        {
                            "option_id": "A",
                            "title": "按提醒创建日程",
                            "summary": summary,
                            "actions": [
                                {
                                    "type": "create_event",
                                    "payload": {
                                        "title": title,
                                        "start_time": start_time.isoformat(),
                                        "end_time": end_time.isoformat(),
                                        "location_name": location_name,
                                        "event_type": "general",
                                    },
                                }
                            ],
                            "rationale": "这句话包含明确时间和地点，先作为待确认日程处理。",
                        }
                    ],
                },
                recommended_option_id="A",
                is_time_sensitive=True,
            ),
        )
        proposal = await self._label_direct_proposal(user_id=user_id, session_id=session_id, proposal=proposal)
        await self._persist_active_target_for_proposal(
            user_id=user_id,
            session_id=session_id,
            proposal=proposal,
            user_message=user_message,
        )
        label = self._proposal_protocol_label(proposal) or "P1"
        return f"{label}：{summary}。我已放入待确认方案，确认后才会创建日程。"

    async def _maybe_create_deterministic_event_proposal(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        events: list[Any],
    ) -> str | None:
        if not re.search(r"见面|碰头|上课|开会|会议|组会|答辩|面试|体检|聚餐|接|送", user_message):
            return None
        start_time, end_time = self.text_runtime._extract_time_range(
            user_message,
            reference=datetime.now(ZoneInfo(self.settings.app_timezone)),
        )
        if start_time is None:
            start_time = self._deterministic_period_start(user_message)
        if start_time is None:
            return None
        end_time = end_time or start_time + timedelta(hours=1)
        location_match = re.search(
            r"(?:去|到|在|于)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}?)(?=(?:和|跟|同).{0,8}(?:见面|碰头)|见面|碰头|上课|开会|会议|组会|答辩|面试|体检|聚餐|接|送|[，。,；;!！?？]|$)",
            user_message,
        )
        location_name = location_match.group("location").strip() if location_match else None
        if location_name:
            location_name = re.sub(r"(?:开|去|参加)$", "", location_name).strip() or location_name
        title = self._deterministic_event_title(user_message=user_message, location_name=location_name)
        if not title:
            return None
        conflicts = [
            event
            for event in events
            if (getattr(event, "status", None) or "planned") != "canceled"
            and getattr(event, "start_time", None) is not None
            and getattr(event, "end_time", None) is not None
            and start_time < getattr(event, "end_time")
            and end_time > getattr(event, "start_time")
        ]
        payload = {
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "location_name": location_name,
            "event_type": "general",
        }
        base_summary = f"建议创建日程“{title}”：{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}"
        if location_name:
            base_summary += f"，地点：{location_name}"
        default_duration_note = "结束时间未明确，默认1小时，可在确认前修改。"
        options = [
            {
                "option_id": "A",
                "title": "按建议创建日程",
                "summary": base_summary,
                "actions": [{"type": "create_event", "payload": payload}],
                "rationale": default_duration_note,
            }
        ]
        summary = base_summary
        if conflicts:
            conflict = conflicts[0]
            conflict_title = str(getattr(conflict, "title", "已有日程"))
            summary += f"；与{conflict_title}存在时间冲突"
            delayed_start = end_time
            delayed_end = delayed_start + (end_time - start_time)
            delayed_payload = dict(payload)
            delayed_payload["start_time"] = delayed_start.isoformat()
            delayed_payload["end_time"] = delayed_end.isoformat()
            options = [
                {
                    "option_id": "A",
                    "title": "后移新日程以避开当前时段",
                    "summary": f"方案A：将“{title}”调整至 {delayed_start.strftime('%H:%M')}-{delayed_end.strftime('%H:%M')}，原日程“{conflict_title}”保持不变。",
                    "actions": [{"type": "create_event", "payload": delayed_payload}],
                    "rationale": f"与{conflict_title}存在时间冲突，先给出不修改原日程的候选方案。",
                },
                {
                    "option_id": "B",
                    "title": "维持原时间并提示处理冲突",
                    "summary": f"方案B：维持原时间 {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}，但会与“{conflict_title}”冲突。",
                    "actions": [{"type": "create_event", "payload": payload}],
                    "rationale": "确认前需要你明确接受这个冲突风险。",
                },
            ]
        proposal = await self.proposal_manager.create_proposal(
            user_id=user_id,
            payload=AssistantProposalCreate(
                session_id=session_id,
                proposal_type="event_creation",
                trigger_type="user_message",
                status="pending",
                summary=summary,
                payload_json={
                    "source": "deterministic_event_creation",
                    "diagnostics": {
                        "direct_conflicts": [
                            {
                                "event_id": getattr(event, "id", None),
                                "title": getattr(event, "title", None),
                                "start_time": getattr(event, "start_time").isoformat(),
                                "end_time": getattr(event, "end_time").isoformat(),
                            }
                            for event in conflicts
                        ],
                    },
                    "options": options,
                },
                recommended_option_id="A",
                is_time_sensitive=True,
            ),
        )
        proposal = await self._label_direct_proposal(user_id=user_id, session_id=session_id, proposal=proposal)
        await self._persist_active_target_for_proposal(
            user_id=user_id,
            session_id=session_id,
            proposal=proposal,
            user_message=user_message,
        )
        label = self._proposal_protocol_label(proposal) or "P1"
        return f"{label}：{summary}。{default_duration_note}我已放入待确认方案，确认前不会写入日程。"

    def _deterministic_period_start(self, user_message: str) -> datetime | None:
        if not re.search(r"上午|下午|晚上|今晚|早上|中午|凌晨", user_message):
            return None
        base_date = self.text_runtime._extract_target_date(
            user_message,
            datetime.now(ZoneInfo(self.settings.app_timezone)).date(),
        )
        hour = 9
        if re.search(r"下午", user_message):
            hour = 15
        elif re.search(r"晚上|今晚", user_message):
            hour = 19
        elif re.search(r"中午", user_message):
            hour = 12
        elif re.search(r"凌晨", user_message):
            hour = 2
        elif re.search(r"早上|上午", user_message):
            hour = 9
        return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=0)

    def _deterministic_event_title(self, *, user_message: str, location_name: str | None) -> str | None:
        message = re.sub(
            r"^(?:今天|明天|后天|大后天|今晚|明早|明晚)?(?:上午|下午|晚上|早上|中午|凌晨)?(?:\d+|[一二两三四五六七八九十半]+)?(?:点|时)?.*?(?:去|到|在|于)?",
            "",
            user_message,
            count=1,
        ).strip(" ，。,；;!！?？")
        if location_name and message.startswith(location_name):
            message = message[len(location_name):].strip(" ，。,；;!！?？")
        if message:
            if location_name and re.match(r"^(?:接|送)[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}$", message):
                return f"去{location_name}{message}"
            if re.match(r"^(?:和|跟|同)", message):
                return "和" + re.sub(r"^(?:和|跟|同)\s*", "", message)
            return message[:40]
        if location_name:
            return f"去{location_name}"
        return None

    def _classify_proposal_text_protocol(self, user_message: str) -> str | None:
        if self._looks_like_proposal_rejection(user_message):
            return "reject"
        if self._looks_like_proposal_revision(user_message):
            return "revise"
        if self._looks_like_active_proposal_confirmation(user_message):
            return "confirm"
        return None

    def _looks_like_active_proposal_confirmation(self, user_message: str) -> bool:
        message = user_message.strip()
        return bool(
            re.fullmatch(r"(就)?按\s*(这个|这条|刚才那个|上一个|P\d+)(方案|建议)?(来|执行|确认)?[。！!]*", message, re.I)
            or re.fullmatch(r"(确认|执行)\s*(这个|这条|刚才那个|上一个|P\d+)(方案|建议)?[。！!]*", message, re.I)
            or re.fullmatch(r"(确认|执行)\s*P\d+\s*(?:方案|option)?\s*[A-ZＡ-Ｚ](?:\s*(?:安排|执行|确认|来))?[。！!]*", message, re.I)
            or re.fullmatch(r"(?:P\d+\s*)?(?:按|确认|执行)\s*(?:方案|option)?\s*[A-ZＡ-Ｚ](?:\s*(?:安排|执行|确认|来))?[。！!]*", message, re.I)
            or re.fullmatch(r"(同意|可以|好|好的|行|行吧|没问题)[。！!]*", message, re.I)
        )

    def _looks_like_proposal_rejection(self, user_message: str) -> bool:
        message = user_message.strip()
        return bool(
            re.fullmatch(
                r"(?:(?:P\d+|这个|这条|刚才那个|上一个)\s*)?(?:不要|先不要安排|先不安排|暂不安排|先别安排|取消这个方案|这个不行|不行|拒绝|算了)[。！!]*",
                message,
                re.I,
            )
        )

    def _looks_like_proposal_revision(self, user_message: str) -> bool:
        message = user_message.strip()
        if not re.search(
            r"P\d+|proposal|option|"
            r"(?:这个|这条|刚才那个|上一个)\s*(?:方案|建议)|"
            r"(?:方案|建议)",
            message,
            re.I,
        ):
            return False
        return bool(re.search(r"改一下|修改|改成|改到|调整|换成|开到|结束到|revise|change", message, re.I))

    def _looks_like_contextual_proposal_revision(self, user_message: str) -> bool:
        message = user_message.strip()
        return (
            self._looks_like_contextual_proposal_type_correction(message)
            or self._looks_like_contextual_proposal_slot_update(message)
            or bool(
                re.search(r"改成|改到|改为|修改|调整|换成|开到|结束到|提前|推迟|延后|缩短|延长|revise|change", message, re.I)
                and re.search(r"(\d{1,2}\s*(?:点|时)|[一二两三四五六七八九十]{1,3}\s*(?:点|时)|上午|下午|晚上|地点|标题|名称|半小时|小时|分钟)", message)
            )
        )

    def _looks_like_contextual_proposal_slot_update(self, user_message: str) -> bool:
        message = user_message.strip()
        if not message:
            return False
        if re.search(r"(?<![A-Za-z0-9])P\d+(?![A-Za-z0-9])|方案|建议|proposal", message, re.I):
            return False
        if re.search(r"创建|新增|安排|生成|取消|不去了|不用去了|不做了|拒绝|确认|执行|可以|好的", message):
            return False
        has_time_range = self.text_runtime._extract_time_range(message)[0] is not None
        has_slot_label = bool(re.search(r"开始|起|结束|截止|持续|时长|地点|位置|标题|名称", message))
        has_time_token = bool(
            re.search(
                r"\d{1,2}\s*(?:点|时)|[一二两三四五六七八九十]{1,3}\s*(?:点|时)|上午|下午|晚上|半小时|小时|分钟",
                message,
            )
        )
        return has_time_range or (has_slot_label and has_time_token)

    def _looks_like_contextual_event_creation_directive(self, user_message: str) -> bool:
        message = user_message.strip()
        return bool(
            re.fullmatch(r"(?:请|帮我)?(?:创建|新增|安排|生成|做成|转成).{0,8}(?:独立|单次|一次性)?日程[。！!]*", message)
            or re.fullmatch(r"(?:独立|单次|一次性)日程[。！!]*", message)
        )

    def _build_existing_event_creation_proposal_reply(self, proposals: list[Any], *, user_message: str) -> str | None:
        event_proposals = [
            proposal for proposal in proposals
            if str(getattr(proposal, "proposal_type", "") or "") == "event_creation"
        ]
        if not event_proposals:
            return None
        if len(event_proposals) > 1:
            if self.text_runtime._prefers_chinese(user_message):
                labels = [self._proposal_protocol_label(proposal) or f"#{getattr(proposal, 'id', '?')}" for proposal in event_proposals[:5]]
                return "当前有多个待确认日程方案，请明确要处理哪一个：" + "、".join(labels) + "。例如回复“确认 P1 方案A”或“修改 P2”。"
            return "There are multiple pending event proposals. Please specify which one to use, for example: confirm P1 option A."
        proposal = event_proposals[0]
        label = self._proposal_protocol_label(proposal) or f"#{getattr(proposal, 'id', '?')}"
        option_id = (
            getattr(proposal, "recommended_option_id", None)
            or self._first_proposal_option_id(getattr(proposal, "payload_json", None) or {})
            or "A"
        )
        summary = str(getattr(proposal, "summary", "") or "这个日程方案")
        if self.text_runtime._prefers_chinese(user_message):
            return f"已经有待确认的独立日程方案：{label}「{summary}」。我还没有写入日程；如果要创建，请回复“确认 {label} 方案{option_id}”，或者直接告诉我要改哪里。"
        return f"There is already a pending event proposal: {label} \"{summary}\". I have not written it yet; confirm {label} option {option_id} to create it."

    def _looks_like_event_targeted_reschedule_request(
        self,
        user_message: str,
        *,
        events: object | None = None,
    ) -> bool:
        message = user_message.strip()
        if not message or re.search(r"(?<![A-Za-z0-9])P\d+(?![A-Za-z0-9])|方案|建议|proposal", message, re.I):
            return False
        match = re.search(r"改到|改成|改为|调整到|挪到|推到|推迟到|提前到|延期到|顺延到|延后到", message)
        if not match:
            return False
        target_text = message[: match.start()]
        if not re.search(r"日程|安排|会议|见面|课|自习|复习块|块|考试|体检|开会|组会|培训|面试|活动", target_text):
            return False
        if events is None:
            return False
        return self._message_matches_existing_event_target(target_text, events)

    @staticmethod
    def _message_matches_existing_event_target(target_text: str, events: object) -> bool:
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            return False
        normalized_target = re.sub(r"[\s，。,、的]+", "", target_text)
        if not normalized_target:
            return False
        for event in events:
            title = getattr(event, "title", None)
            if title is None and isinstance(event, dict):
                title = event.get("title")
            if not isinstance(title, str):
                continue
            normalized_title = re.sub(r"[\s，。,、的]+", "", title)
            if normalized_title and (normalized_title in normalized_target or normalized_target in normalized_title):
                return True
        return False

    def _looks_like_contextual_proposal_type_correction(self, user_message: str) -> bool:
        message = user_message.strip()
        return bool(
            re.search(r"这个|这条|刚才|上一个|不是|应(?:该)?是|改成|改为", message)
            and re.search(r"任务|待办|todo|日程|单次日程|事件|event", message, re.I)
            and re.search(r"不是|应(?:该)?是|改成|改为|类型", message)
        )

    def _proposal_supports_contextual_revision(self, proposal: Any, user_message: str) -> bool:
        if self._looks_like_contextual_proposal_type_correction(user_message):
            return True

        proposal_type = str(getattr(proposal, "proposal_type", "") or "")
        if proposal_type in {"event_creation", "event_reschedule"}:
            return True

        payload_json = getattr(proposal, "payload_json", None) or {}
        if not isinstance(payload_json, dict):
            return False
        options = payload_json.get("options")
        if not isinstance(options, list):
            return False

        for option in options:
            if not isinstance(option, dict):
                continue
            actions = option.get("actions")
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                if action.get("type") in {"create_event", "reschedule_event"}:
                    return True
        return False

    async def _resolve_text_protocol_proposal(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        external_context: dict[str, Any],
    ) -> Any | str | None:
        active = []
        if hasattr(self.proposal_manager, "list_proposals"):
            active = await self._list_text_protocol_proposals(
                user_id=user_id,
                session_id=session_id,
                statuses=["pending"],
                limit=10,
            )

        explicit_label = self._extract_proposal_display_label(user_message)
        if explicit_label is not None and hasattr(self.proposal_manager, "list_proposals"):
            terminal = await self._list_text_protocol_proposals(
                user_id=user_id,
                session_id=session_id,
                statuses=["expired", "superseded", "execution_failed"],
                limit=10,
            )
            labelled = self._find_proposal_by_protocol_label([*active, *terminal], explicit_label)
            if labelled is not None:
                return labelled
            stable_labelled = self._find_proposal_by_stable_protocol_label([*active, *terminal], explicit_label)
            if stable_labelled is not None:
                return stable_labelled
            if self._proposal_list_has_protocol_labels(active) or self._proposal_list_has_protocol_labels(terminal):
                return None

        resolved = self._resolve_text_protocol_proposal_from_active(
            active=active,
            user_message=user_message,
            external_context=external_context,
        )
        if resolved is not None:
            return resolved

        if not active and hasattr(self.proposal_manager, "list_proposals"):
            terminal = await self._list_text_protocol_proposals(
                user_id=user_id,
                session_id=session_id,
                statuses=["expired", "superseded", "execution_failed"],
                limit=10,
            )
            resolved = self._resolve_text_protocol_proposal_from_active(
                active=terminal,
                user_message=user_message,
                external_context=external_context,
            )
            if resolved is not None:
                return resolved

        active_target = (external_context or {}).get("active_target")
        proposal_id = active_target.get("proposal_id") if isinstance(active_target, dict) else None
        if proposal_id is None or active:
            return None
        try:
            proposal_id_int = int(proposal_id)
        except (TypeError, ValueError):
            return None
        if not hasattr(self.proposal_manager, "get_proposal"):
            return None
        try:
            proposal = await self.proposal_manager.get_proposal(user_id=user_id, proposal_id=proposal_id_int)
        except HTTPException:
            return None
        if getattr(proposal, "status", None) in {"accepted", "execution_pending", "executed", "execution_failed"}:
            return proposal
        return None

    async def _list_text_protocol_proposals(
        self,
        *,
        user_id: str,
        session_id: int | None,
        statuses: list[str],
        limit: int,
    ) -> list[Any]:
        session_items = await self.proposal_manager.list_proposals(
            user_id=user_id,
            session_id=session_id,
            statuses=statuses,
            limit=limit,
        )
        if session_id is None or len(session_items) >= limit:
            return list(session_items)
        all_items = await self.proposal_manager.list_proposals(
            user_id=user_id,
            session_id=None,
            statuses=statuses,
            limit=limit,
        )
        scoped_all_items = [
            item
            for item in all_items
            if getattr(item, "session_id", None) in {None, session_id}
        ]
        merged: list[Any] = []
        seen: set[Any] = set()
        for item in [*session_items, *scoped_all_items]:
            key = getattr(item, "id", id(item))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    def _resolve_text_protocol_proposal_from_active(
        self,
        *,
        active: list[Any],
        user_message: str,
        external_context: dict[str, Any],
    ) -> Any | str | None:
        active = sorted(active, key=lambda item: getattr(item, "id", 0) or 0)
        explicit_label = self._extract_proposal_display_label(user_message)
        if explicit_label is not None:
            for proposal in active:
                payload_json = getattr(proposal, "payload_json", None) or {}
                if isinstance(payload_json, dict) and str(payload_json.get("protocol_label") or "").upper() == explicit_label:
                    return proposal

        explicit_index = self._extract_proposal_display_index(user_message)
        if explicit_index is not None:
            if 0 <= explicit_index < len(active):
                return active[explicit_index]
            return "ambiguous"

        if len(active) > 1:
            return "ambiguous"

        active_target = (external_context or {}).get("active_target")
        proposal_id = active_target.get("proposal_id") if isinstance(active_target, dict) else None
        if proposal_id is not None:
            try:
                proposal_id_int = int(proposal_id)
            except (TypeError, ValueError):
                proposal_id_int = None
            for proposal in active:
                if proposal_id_int is not None and getattr(proposal, "id", None) == proposal_id_int:
                    return proposal

        if len(active) == 1:
            return active[0]
        return None

    def _find_proposal_by_protocol_label(self, proposals: list[Any], label: str) -> Any | None:
        normalized = label.upper()
        for proposal in proposals:
            payload_json = getattr(proposal, "payload_json", None) or {}
            if isinstance(payload_json, dict) and str(payload_json.get("protocol_label") or "").upper() == normalized:
                return proposal
        return None

    def _find_proposal_by_stable_protocol_label(self, proposals: list[Any], label: str) -> Any | None:
        proposals_by_id = {
            getattr(proposal, "id", None): proposal
            for proposal in proposals
            if getattr(proposal, "id", None) is not None
        }
        if not proposals_by_id:
            return None
        label_by_id = self._assign_stable_proposal_labels(list(proposals_by_id.values()))
        normalized = label.upper()
        for proposal_id, assigned_label in label_by_id.items():
            if assigned_label.upper() == normalized:
                return proposals_by_id.get(proposal_id)
        return None

    def _proposal_list_has_protocol_labels(self, proposals: list[Any]) -> bool:
        for proposal in proposals:
            payload_json = getattr(proposal, "payload_json", None) or {}
            if isinstance(payload_json, dict) and str(payload_json.get("protocol_label") or "").strip():
                return True
        return False

    def _build_proposal_protocol_assessment(
        self,
        *,
        user_message: str,
        intent: str,
        proposal: Any | str | None,
        external_context: dict[str, Any],
    ) -> OrchestrationAssessment:
        active_target = (external_context or {}).get("active_target")
        proposal_id = active_target.get("proposal_id") if isinstance(active_target, dict) else None
        target_scope = TargetScope(kind="proposal", resolution="missing", proposal_id=proposal_id)
        if proposal == "ambiguous":
            target_scope = TargetScope(kind="proposal", resolution="ambiguous", proposal_id=proposal_id)
        elif proposal is not None:
            target_scope = TargetScope(
                kind="proposal",
                resolution="resolved",
                proposal_id=getattr(proposal, "id", None),
                label=getattr(proposal, "summary", None),
            )
        continuation = ContinuationSignals(
            is_following_previous_context=True,
            based_on_active_target=isinstance(active_target, dict) and active_target.get("proposal_id") is not None,
            based_on_pending_proposal=proposal is not None,
            based_on_history=self._has_context_reference(user_message),
            reason="proposal_text_protocol",
        )
        return OrchestrationAssessment(
            conversation_mode=(
                "revise_existing"
                if intent == "revise"
                else "reject_existing"
                if intent == "reject"
                else "confirm_existing"
            ),
            user_goal=(
                "revise_existing_proposal"
                if intent == "revise"
                else "reject_existing_proposal"
                if intent == "reject"
                else "confirm_existing_proposal"
            ),
            target_scope=target_scope,
            continuation=continuation,
            planning_intent=PlanningIntent(),
            missing_information=["pending_proposal"] if proposal is None else [],
            notes=["phase9a_proposal_protocol"],
        )

    def _extract_proposal_display_index(self, user_message: str) -> int | None:
        match = re.search(r"(?<![A-Za-z0-9])P(?P<index>\d+)(?![A-Za-z0-9])", user_message, re.I)
        if not match:
            return None
        return int(match.group("index")) - 1

    def _extract_proposal_display_label(self, user_message: str) -> str | None:
        match = re.search(r"(?<![A-Za-z0-9])P(?P<index>\d+)(?![A-Za-z0-9])", user_message, re.I)
        if not match:
            return None
        return f"P{int(match.group('index'))}"

    def _extract_proposal_option_id(self, user_message: str) -> str | None:
        match = re.search(r"(?:方案|option)\s*(?P<option>[A-ZＡ-Ｚ])|按\s*(?!P\d)(?P<option_after_action>[A-ZＡ-Ｚ])", user_message, re.I)
        if not match:
            return None
        option = (match.group("option") or match.group("option_after_action")).upper()
        return chr(ord(option) - ord("Ａ") + ord("A")) if "Ａ" <= option <= "Ｚ" else option

    def _build_proposal_protocol_clarification(self, user_message: str) -> str:
        if self.text_runtime._prefers_chinese(user_message):
            return "我不确定你指的是哪个待确认方案。请直接说“按 P1”或“把 P2 改到明天上午”。"
        return "I am not sure which pending proposal you mean. Please refer to it as P1 or P2."

    def _build_missing_proposal_protocol_reply(
        self,
        *,
        user_message: str,
        intent: str,
        assessment: OrchestrationAssessment | None = None,
    ) -> str:
        if self.text_runtime._prefers_chinese(user_message):
            if assessment is not None and assessment.target_scope.resolution == "ambiguous":
                return "我知道你是在操作已有方案，但现在还不能唯一定位到哪一个。请直接说“按 P1”或“把 P2 改到明天下午”。"
            if intent == "revise":
                return "我知道你是在修改现有方案，但当前没有可修改的待确认方案。请先让我给你出一个方案，或者明确指出要修改哪条历史方案。"
            if intent == "reject":
                return "我知道你是在拒绝现有方案，但当前没有待确认方案可拒绝。"
            return "我知道你是在确认现有方案，但当前没有待确认方案可执行；如果你是在重复确认刚刚已执行的方案，它已经执行完成，不会重复写入。需要新安排的话，请直接告诉我要安排什么。"
        if intent == "revise":
            return "I understand that you want to revise an existing proposal, but there is no pending proposal to revise right now."
        if intent == "reject":
            return "I understand that you want to reject an existing proposal, but there is no pending proposal to reject right now."
        return "I understand that you want to confirm an existing proposal, but there is no pending proposal to execute right now."

    def _has_context_reference(self, user_message: str) -> bool:
        return bool(re.search(r"这个|那个|这条|那条|它|刚才|刚刚|上一个|前面那个|刚说的|继续", user_message))

    def _first_proposal_option_id(self, payload_json: dict[str, Any]) -> str | None:
        options = payload_json.get("options") if isinstance(payload_json, dict) else None
        if not isinstance(options, list):
            return None
        for option in options:
            if isinstance(option, dict) and option.get("option_id"):
                return str(option["option_id"])
        return None

    def _apply_place_memory_to_event_payload(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        external_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        assistant_memory = (external_context or {}).get("assistant_memory")
        resolved = self.memory_service.resolve_place_alias(
            user_message=user_message,
            location_name=payload.get("location_name"),
            memory_context=assistant_memory if isinstance(assistant_memory, dict) else None,
        )
        if not resolved:
            return payload
        enriched = dict(payload)
        if resolved.get("location_name"):
            enriched["location_name"] = resolved["location_name"]
        if resolved.get("location_coords"):
            enriched["location_coords"] = resolved["location_coords"]
        return enriched

    def _should_use_conductor_reply(self, result: ConductorResult | None) -> bool:
        if result is None:
            return False
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        return mode in {"proposal", "primary"} and result.decision in {"proposal", "clarification", "answer"}

    def _should_block_legacy_fallback(
        self,
        result: ConductorResult | None,
        *,
        user_message: str = "",
        external_context: dict[str, Any] | None = None,
    ) -> bool:
        if result is None:
            return False
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        if result.decision not in {"legacy", "unsupported"}:
            return False
        if mode == "primary":
            return True
        if mode != "proposal":
            return False
        return self._should_prefer_model_driven_path(
            user_message=user_message,
            external_context=external_context or {},
        )

    def _should_allow_answer_like_rule_short_circuit(self, result: ConductorResult | None) -> bool:
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        return not (mode in {"proposal", "primary"} and result is not None)

    def _should_use_streaming_plan_fallback(self, result: ConductorResult | None) -> bool:
        if not self.gemini.enabled:
            return False
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        if mode in {"proposal", "primary"} and result is not None:
            return False
        return True

    def _should_use_plan_compatibility_fallback(self, result: ConductorResult | None) -> bool:
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        if mode in {"proposal", "primary"} and result is not None:
            return False
        return True

    def _primary_mode_fallback_reply(
        self,
        user_message: str,
        result: ConductorResult | None,
        *,
        external_context: dict[str, Any] | None = None,
    ) -> str:
        if result and result.reply:
            return result.reply
        active_target = (external_context or {}).get("active_target")
        if isinstance(active_target, dict) and active_target.get("task_id") is not None and self.text_runtime._prefers_chinese(user_message):
            return "我先不把这句丢回旧规则链了。你现在像是在继续规划已有任务，请直接告诉我这个任务想安排到哪几天、几点到几点。"
        if isinstance(active_target, dict) and active_target.get("proposal_id") is not None and self.text_runtime._prefers_chinese(user_message):
            return "我先不把这句丢回旧规则链了。你现在像是在继续操作已有方案，请直接说“确认 P1”或“把 P1 改到明天下午”。"
        if self.text_runtime._prefers_chinese(user_message):
            return "我先不走旧的规则回退链路了。请直接告诉我你现在是想继续规划哪个任务，还是要修改哪个已有日程。"
        return "I am not falling back to the legacy rule path here. Tell me whether you want to continue planning a task or modify an existing event."

    def _should_prefer_model_driven_path(self, *, user_message: str, external_context: dict[str, Any]) -> bool:
        active_target = (external_context or {}).get("active_target")
        if isinstance(active_target, dict) and any(
            active_target.get(key) is not None for key in ("proposal_id", "task_id", "event_id")
        ):
            return True
        if self._looks_like_active_proposal_confirmation(user_message):
            return True
        if self._looks_like_proposal_revision(user_message):
            return True
        if self._has_context_reference(user_message):
            return True
        if re.search(r"继续规划|继续安排|继续排|这个任务|那个任务|这一项任务|把今天所有", user_message):
            return True
        return False

    def _format_conductor_reply(
        self,
        result: ConductorResult,
        *,
        user_message: str,
        memory_candidates: list[Any],
    ) -> str:
        reply = result.reply or ""
        reply = self._apply_persisted_proposal_labels(reply, result.metadata or {})
        reply = self._prefix_if_model_unavailable(reply, user_message=user_message)
        persisted_ids = (result.metadata or {}).get("persisted_proposal_ids") or []
        if persisted_ids and self.text_runtime._prefers_chinese(user_message):
            reply = f"{reply}\n\n我已把方案放进“待确认方案”，你确认后我才会执行写入。"
        elif persisted_ids:
            reply = f"{reply}\n\nI saved this as a pending proposal and will only execute it after confirmation."
        return self._append_memory_candidate_notice(
            reply,
            user_message=user_message,
            memory_candidates=memory_candidates,
        )

    def _prefix_if_model_unavailable(self, reply: str, *, user_message: str) -> str:
        if not getattr(self.gemini, "_last_generation_failed_all", False):
            return reply
        if self.text_runtime._prefers_chinese(user_message):
            notice = "AI 服务暂时不可用，但我仍根据本地规则给出一个临时回复。"
        else:
            notice = "AI service is temporarily unavailable, but I can still provide a local rule-based response."
        stripped = reply.strip()
        return f"{notice}\n\n{stripped}" if stripped else notice

    def _apply_persisted_proposal_labels(self, reply: str, metadata: dict[str, Any]) -> str:
        labels = metadata.get("persisted_proposal_labels")
        if not isinstance(labels, list) or not labels:
            return reply
        updated = reply
        for index, label in enumerate(labels, start=1):
            if not isinstance(label, str) or label == f"P{index}":
                continue
            updated = re.sub(rf"\bP{index}\b", label, updated)
        return updated

    async def _maybe_build_orchestration_answer_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        conductor_result: ConductorResult | None,
        history,
        events,
        tasks,
        profile,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        if conductor_result is None or conductor_result.understanding is None:
            return None
        orchestration = conductor_result.understanding.orchestration
        if orchestration is None or orchestration.conversation_mode != "answer":
            return None
        if orchestration.user_goal == "schedule_guidance":
            return await self._build_rule_based_plan(
                user_id=user_id,
                user_message=user_message,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
        if orchestration.user_goal == "progress_followup":
            return await self._build_progress_followup_plan(
                user_id=user_id,
                user_message=user_message,
                tasks=tasks,
            )
        if orchestration.user_goal == "event_context_advice":
            return await self._build_event_context_advice_plan_from_understanding(
                user_message=user_message,
                understanding_slots=conductor_result.understanding.slots,
                history=history,
                profile=profile,
                external_context=external_context,
            )
        return None

    async def _maybe_handle_departure_signal_reply(
        self,
        *,
        user_id: str,
        user_message: str,
    ) -> str | None:
        arrival_location = self._extract_arrival_update_location(user_message)
        if not arrival_location:
            return None

        signals = await self.signal_manager.list_signals(
            user_id=user_id,
            statuses=["new", "evaluated", "proposal_created"],
            signal_type="departure_readiness",
            limit=10,
        )
        signal = self._select_departure_signal_for_arrival(signals, arrival_location=arrival_location)
        if signal is None:
            return None

        await self.signal_manager.dismiss_signal(user_id=user_id, signal_id=signal.id)
        context = signal.context_json or {}
        title = str(context.get("title") or context.get("reason") or "这次行程")
        return (
            f"收到，你已经在{arrival_location}了。"
            f"我已把「{title}」这次出发提醒按已到达处理，不会继续催同一次出发；"
            "我不会把这句话写入长期地点记忆。"
        )

    async def _maybe_handle_departure_signal_cancel_reply(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
    ) -> str | None:
        if not self._looks_like_departure_cancel_reply(user_message):
            return None

        signals = await self.signal_manager.list_signals(
            user_id=user_id,
            statuses=["new", "evaluated", "proposal_created"],
            signal_type="departure_readiness",
            limit=10,
        )
        if len(signals) != 1:
            if signals:
                return "我看到多条出发提醒。请说明要取消哪一个行程，我再生成可确认的取消方案。"
            return None

        signal = signals[0]
        context = getattr(signal, "context_json", None) or {}
        event_id = getattr(signal, "target_id", None) or context.get("event_id")
        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            return "我理解你今天不去了，但这条出发提醒没有可操作的日程编号。请说明要取消哪个日程。"

        title = str(context.get("title") or "这次行程")
        summary = f"建议取消日程“{title}”"
        proposal = await self.proposal_manager.create_proposal(
            user_id=user_id,
            payload=AssistantProposalCreate(
                session_id=session_id,
                proposal_type="event_cancel",
                trigger_type="user_message",
                status="pending",
                dedup_key=f"departure_cancel:signal:{getattr(signal, 'id', event_id)}:event:{event_id}",
                priority=3,
                summary=summary,
                payload_json={
                    "source": "departure_signal_cancel",
                    "target_title": title,
                    "signal": {
                        "id": getattr(signal, "id", None),
                        "signal_type": getattr(signal, "signal_type", None),
                        "target_type": getattr(signal, "target_type", None),
                        "target_id": getattr(signal, "target_id", None),
                        "context": context,
                    },
                    "options": [
                        {
                            "option_id": "A",
                            "title": "取消这个日程",
                            "summary": summary,
                            "actions": [{"type": "cancel_event", "payload": {"event_id": event_id}}],
                            "rationale": "确认后只把该日程标记为取消，不会物理删除。",
                        }
                    ],
                },
                recommended_option_id="A",
                is_time_sensitive=True,
                related_event_id=event_id,
                source_signal_id=getattr(signal, "id", None),
            ),
        )
        proposal = await self._label_direct_proposal(user_id=user_id, session_id=session_id, proposal=proposal)
        try:
            await self.signal_manager.mark_proposal_created(user_id=user_id, signal_id=signal.id)
        except Exception:
            logger.bind(component="assistant.signal").warning(
                "Failed to mark departure cancel signal proposal_created signal_id={}",
                getattr(signal, "id", None),
            )
        label = self._proposal_protocol_label(proposal)
        prefix = f"{label} " if label else ""
        return f"收到。{prefix}{summary}已生成，确认前不会取消或删除原日程。你可以回复“确认 {label or '方案A'} 方案A”来执行，或回复“先不要安排”。"

    @staticmethod
    def _looks_like_departure_cancel_reply(user_message: str) -> bool:
        text = user_message.strip()
        return bool(re.search(r"(今天|这次|这个|那就|算了)?.*(不去|不去了|不用去了|不出发|不走了|取消|跳过)", text))

    def _select_departure_signal_for_arrival(self, signals: Sequence[Any], *, arrival_location: str) -> Any | None:
        if not signals:
            return None
        normalized_arrival = self._normalize_location_text(arrival_location)
        for signal in signals:
            context = getattr(signal, "context_json", None) or {}
            location = self._normalize_location_text(str(context.get("location_name") or ""))
            if location and normalized_arrival and (location in normalized_arrival or normalized_arrival in location):
                return signal
        return signals[0]

    @staticmethod
    def _normalize_location_text(value: str) -> str:
        return re.sub(r"\s+", "", value.strip(" ，。,；;.!！?？"))

    async def _build_event_context_advice_plan_from_understanding(
        self,
        *,
        user_message: str,
        understanding_slots: dict[str, Any],
        history=None,
        profile,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        arrival_location = self._extract_arrival_update_location(user_message)
        if arrival_location:
            return {
                "reply": (
                    f"收到，你已经在{arrival_location}了。这次出发提醒可以按已到达处理；"
                    "我不会把这句话写入长期地点记忆。"
                ),
                "actions": [],
            }
        event_payload = {
            "title": understanding_slots.get("title"),
            "start_time": understanding_slots.get("start_time"),
            "end_time": understanding_slots.get("end_time"),
            "location_name": understanding_slots.get("location_name"),
            "event_type": "general",
        }
        self._fill_sparse_event_advice_payload(event_payload, user_message=user_message)
        event_payload = self._apply_place_memory_to_event_payload(
            payload=event_payload,
            user_message=user_message,
            external_context=external_context,
        )
        event_context = await self._build_event_specific_context(
            payload=event_payload,
            profile=profile,
            user_message=user_message,
        )
        runtime_origin = self._recent_runtime_origin_from_history(history or [])
        if runtime_origin and re.search(r"^那|刚才|前面|这个|那个|几点出发|出发", user_message):
            event_context["runtime_origin"] = runtime_origin
            event_context.pop("origin_ambiguity", None)
            event_context.pop("origin_clarification", None)
        actions: list[dict[str, Any]] = []
        if event_payload.get("title") and event_payload.get("start_time") and event_payload.get("end_time"):
            actions.append(
                {
                    "type": "propose_event",
                    "payload": {
                        **event_payload,
                        "commute_summary": event_context.get("commute_summary"),
                        "weather_summary": event_context.get("weather_summary"),
                        "advice_summary": event_context.get("advice_summary"),
                    },
                }
            )
        return {
            "reply": self._build_event_advice_reply(
                payload=event_payload,
                user_message=user_message,
                event_context=event_context,
                profile=profile,
            ),
            "actions": actions,
        }

    async def _persist_conductor_proposals(
        self,
        *,
        user_id: str,
        session_id: int,
        result: ConductorResult,
        user_message: str,
        external_context: dict[str, Any],
    ) -> list[Any]:
        if result.decision != "proposal":
            return []
        create_payloads = (result.metadata or {}).get("proposal_create_payloads") or []
        if not isinstance(create_payloads, list):
            return []

        persisted: list[Any] = []
        for raw_payload in create_payloads:
            if not isinstance(raw_payload, dict):
                continue
            try:
                raw_payload = self._apply_place_memory_to_proposal_payload(
                    payload=raw_payload,
                    user_message=user_message,
                    external_context=external_context,
                )
                payload = AssistantProposalCreate.model_validate(raw_payload)
                proposal = await self.proposal_manager.create_proposal(user_id=user_id, payload=payload)
                persisted.append(proposal)
            except Exception as exc:
                logger.bind(component="assistant.conductor").warning(
                    "Failed to persist conductor proposal: {error}",
                    error=str(exc),
                )
        if persisted:
            result.metadata["persisted_proposal_ids"] = [proposal.id for proposal in persisted if getattr(proposal, "id", None) is not None]
            if hasattr(self.proposal_manager, "list_proposals"):
                active = await self.proposal_manager.list_proposals(
                    user_id=user_id,
                    session_id=session_id,
                    statuses=["pending"],
                    limit=50,
                )
                label_scope = await self.proposal_manager.list_proposals(
                    user_id=user_id,
                    session_id=session_id,
                    statuses=None,
                    limit=200,
                )
            else:
                active = list(persisted)
                label_scope = list(persisted)
            proposals_by_id = {
                getattr(proposal, "id", None): proposal
                for proposal in [*label_scope, *active, *persisted]
                if getattr(proposal, "id", None) is not None
            }
            label_by_id = self._assign_stable_proposal_labels(list(proposals_by_id.values()))
            result.metadata["persisted_proposal_labels"] = [
                label_by_id.get(getattr(proposal, "id", None), f"P{index}")
                for index, proposal in enumerate(persisted, start=1)
            ]
            labeled_by_id: dict[Any, Any] = {}
            for proposal_id, label in label_by_id.items():
                proposal = proposals_by_id.get(proposal_id)
                if proposal is None:
                    continue
                if not isinstance(label, str):
                    continue
                payload_json = dict(getattr(proposal, "payload_json", None) or {})
                if payload_json.get("protocol_label") == label:
                    labeled_by_id[proposal_id] = proposal
                    continue
                payload_json["protocol_label"] = label
                repository = getattr(self.proposal_manager, "repository", None)
                if repository is None or not hasattr(repository, "update_proposal"):
                    try:
                        setattr(proposal, "payload_json", payload_json)
                    except Exception:
                        pass
                    labeled_by_id[proposal_id] = proposal
                    continue
                updated = await repository.update_proposal(
                    proposal_id,
                    user_id=user_id,
                    payload={"payload_json": payload_json},
                )
                labeled_by_id[proposal_id] = updated or proposal
            persisted = [labeled_by_id.get(getattr(proposal, "id", None), proposal) for proposal in persisted]
            for proposal in persisted:
                await self._persist_active_target_for_proposal(
                    user_id=user_id,
                    session_id=getattr(proposal, "session_id", None) or session_id,
                    proposal=proposal,
                    user_message=user_message,
                )
        return persisted

    def _assign_stable_proposal_labels(self, proposals: Sequence[Any]) -> dict[Any, str]:
        label_by_id: dict[Any, str] = {}
        used_numbers: set[int] = set()
        needs_label: list[Any] = []
        for proposal in sorted(proposals, key=lambda item: getattr(item, "id", 0) or 0):
            proposal_id = getattr(proposal, "id", None)
            payload_json = getattr(proposal, "payload_json", None) or {}
            existing_label = payload_json.get("protocol_label") if isinstance(payload_json, dict) else None
            match = re.fullmatch(r"P(?P<number>\d+)", existing_label or "")
            if match:
                number = int(match.group("number"))
                if number not in used_numbers:
                    used_numbers.add(number)
                    label_by_id[proposal_id] = existing_label
                    continue
            needs_label.append(proposal)
        next_number = max(used_numbers, default=0) + 1
        for proposal in needs_label:
            while next_number in used_numbers:
                next_number += 1
            proposal_id = getattr(proposal, "id", None)
            label_by_id[proposal_id] = f"P{next_number}"
            used_numbers.add(next_number)
            next_number += 1
        return label_by_id

    async def _label_direct_proposal(self, *, user_id: str, session_id: int, proposal: Any) -> Any:
        active = await self.proposal_manager.list_proposals(
            user_id=user_id,
            session_id=session_id,
            statuses=["pending"],
            limit=50,
        )
        proposals_by_id = {
            getattr(item, "id", None): item
            for item in [*active, proposal]
            if getattr(item, "id", None) is not None
        }
        label_by_id = self._assign_stable_proposal_labels(list(proposals_by_id.values()))
        labelled = proposal
        repository = getattr(self.proposal_manager, "repository", None)
        for proposal_id, label in label_by_id.items():
            item = proposals_by_id.get(proposal_id)
            if item is None:
                continue
            payload_json = dict(getattr(item, "payload_json", None) or {})
            if payload_json.get("protocol_label") == label:
                continue
            payload_json["protocol_label"] = label
            if repository is not None and hasattr(repository, "update_proposal"):
                updated = await repository.update_proposal(
                    proposal_id,
                    user_id=user_id,
                    payload={"payload_json": payload_json},
                )
                if updated is not None and proposal_id == getattr(proposal, "id", None):
                    labelled = updated
            else:
                try:
                    setattr(item, "payload_json", payload_json)
                except Exception:
                    pass
        return labelled

    @staticmethod
    def _proposal_protocol_label(proposal: Any) -> str | None:
        payload_json = getattr(proposal, "payload_json", None) or {}
        if not isinstance(payload_json, dict):
            return None
        label = str(payload_json.get("protocol_label") or "").strip()
        return label or None

    async def _persist_active_target_for_proposal(
        self,
        *,
        user_id: str,
        session_id: int,
        proposal: Any,
        user_message: str,
    ) -> None:
        if not session_id:
            return
        active_target = self._active_target_from_proposal(proposal)
        if not active_target:
            return
        active_target["source"] = "conductor_proposal"
        active_target["last_user_message"] = user_message
        payload = {
            "status": "active",
            "related_task_id": active_target.get("task_id"),
            "related_event_id": active_target.get("event_id"),
            "active_proposal_id": active_target.get("proposal_id"),
            "state_json": {"active_target": active_target},
            "is_waiting_user": getattr(proposal, "status", None) == "pending",
            "last_specialist": "proposal_manager",
            "last_user_message_at": datetime.now(ZoneInfo(self.settings.app_timezone)),
            "last_system_message_at": datetime.now(ZoneInfo(self.settings.app_timezone)),
        }
        try:
            await self.thread_state_repository.upsert_active_target_state(
                user_id=user_id,
                session_id=session_id,
                payload=payload,
            )
        except Exception as exc:
            logger.bind(component="assistant.thread_state").warning(
                "Failed to persist active target thread state: {error}",
                error=str(exc),
            )

    def _active_target_from_proposal(self, proposal: Any) -> dict[str, Any] | None:
        proposal_id = getattr(proposal, "id", None)
        event_id = getattr(proposal, "related_event_id", None)
        task_id = getattr(proposal, "related_task_id", None)
        payload_json = getattr(proposal, "payload_json", None) or {}
        if isinstance(payload_json, dict):
            execution_result = ((payload_json.get("execution") or {}).get("result") or {})
            if event_id is None:
                event_id = execution_result.get("related_event_id")
            if task_id is None:
                task_id = execution_result.get("related_task_id")
        kind = "proposal"
        if event_id is not None:
            kind = "event"
        elif task_id is not None:
            kind = "task"
        if proposal_id is None and event_id is None and task_id is None:
            return None
        return {
            "kind": kind,
            "proposal_id": proposal_id,
            "proposal_type": getattr(proposal, "proposal_type", None),
            "proposal_status": getattr(proposal, "status", None),
            "summary": getattr(proposal, "summary", None),
            "event_id": event_id,
            "task_id": task_id,
            "target_title": (payload_json.get("target_title") if isinstance(payload_json, dict) else None),
        }

    def _apply_place_memory_to_proposal_payload(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(payload)
        payload_json = dict(enriched.get("payload_json") or {})
        options = payload_json.get("options")
        if not isinstance(options, list):
            return enriched

        enriched_options: list[Any] = []
        changed = False
        for option in options:
            if not isinstance(option, dict):
                enriched_options.append(option)
                continue
            option_copy = dict(option)
            actions = option_copy.get("actions")
            if not isinstance(actions, list):
                enriched_options.append(option_copy)
                continue
            enriched_actions: list[Any] = []
            for action in actions:
                if not isinstance(action, dict) or action.get("type") != "create_event":
                    enriched_actions.append(action)
                    continue
                action_copy = dict(action)
                action_payload = action_copy.get("payload")
                if isinstance(action_payload, dict):
                    enriched_payload = self._apply_place_memory_to_event_payload(
                        payload=action_payload,
                        user_message=user_message,
                        external_context=external_context,
                    )
                    if enriched_payload != action_payload:
                        changed = True
                    action_copy["payload"] = enriched_payload
                enriched_actions.append(action_copy)
            option_copy["actions"] = enriched_actions
            enriched_options.append(option_copy)

        if not changed:
            return enriched
        payload_json["options"] = enriched_options
        enriched["payload_json"] = payload_json
        return enriched

    async def _run_conductor_for_message(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        history,
        events,
        tasks,
        profile,
        external_context: dict[str, Any],
    ):
        mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        if mode == "legacy":
            return None
        if mode not in {"shadow", "proposal", "primary"}:
            logger.bind(component="assistant.conductor").warning(
                "Unknown ASSISTANT_CONDUCTOR_MODE={mode}; falling back to legacy",
                mode=mode,
            )
            return None
        if self.conductor is None:
            self.conductor = AssistantConductor.build_default(self.text_runtime, semantic_extractor=self.gemini)

        context = AssistantAgentContext(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            history=list(history or []),
            events=list(events or []),
            tasks=list(tasks or []),
            profile=profile,
            external_context=external_context,
            now=datetime.now(ZoneInfo(self.settings.app_timezone)),
        )
        try:
            result = await self.conductor.run(context, mode=mode)
            if mode == "proposal":
                await self._persist_conductor_proposals(
                    user_id=user_id,
                    session_id=session_id,
                    result=result,
                    user_message=user_message,
                    external_context=external_context,
                )
            logger.bind(component="assistant.conductor").info(
                "Assistant conductor result: {result}",
                result=result.to_log_payload(),
            )
            return result
        except Exception as exc:
            logger.bind(component="assistant.conductor").warning(
                "Assistant conductor shadow failed: {error}",
                error=str(exc),
            )
            return None

    def _format_reply_text(self, reply: str, *, user_message: str) -> str:
        return self.formatter.format_reply(reply, prefers_chinese=self.text_runtime._prefers_chinese(user_message))

    async def _maybe_autorename_session(
        self,
        *,
        user_id: str,
        session_id: int,
        session_title: str,
        user_message: str,
    ) -> None:
        await self.session_runtime.maybe_autorename_session(
            user_id=user_id,
            session_id=session_id,
            session_title=session_title,
            user_message=user_message,
        )

    async def get_session(self, user_id: str, session_id: int) -> AssistantSessionRead:
        return await self.session_runtime.get_session(user_id=user_id, session_id=session_id)

    async def get_current_session(self, user_id: str, *, include_inbox: bool = True) -> AssistantCurrentSessionRead:
        return await self.session_runtime.get_current_session(user_id=user_id, include_inbox=include_inbox)

    async def get_summary(self, user_id: str) -> AssistantSummaryRead:
        return await self.session_runtime.get_summary(user_id=user_id)

    async def get_inbox(self, user_id: str) -> AssistantInboxRead:
        return await self.session_runtime.get_inbox(user_id=user_id)

    def _group_inbox_items(self, items: list[AssistantInboxItem]) -> list[AssistantInboxItem]:
        return self.session_runtime.group_inbox_items(items)

    def _apply_inbox_state(
        self,
        items: list[AssistantInboxItem],
        state: dict[str, Any],
    ) -> list[AssistantInboxItem]:
        return self.session_runtime.apply_inbox_state(items, state)

    async def _sync_inbox_to_session(self, *, user_id: str, session, inbox: AssistantInboxRead):
        return await self.session_runtime.sync_inbox_to_session(user_id=user_id, session=session, inbox=inbox)

    async def mark_inbox_item(
        self,
        *,
        user_id: str,
        item_id: str,
        action: str,
    ) -> AssistantInboxRead:
        return await self.session_runtime.mark_inbox_item(user_id=user_id, item_id=item_id, action=action)

    def _compact_inbox_state(self, state: dict[str, Any], max_items: int = 100) -> dict[str, Any]:
        return self.session_runtime.compact_inbox_state(state, max_items=max_items)

    def _cleanup_inbox_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.session_runtime.cleanup_inbox_state(state)

    def _parse_state_datetime(self, raw_value: Any) -> datetime | None:
        return self.session_runtime.parse_state_datetime(raw_value)

    def _render_inbox_item_as_message(self, item: AssistantInboxItem) -> str:
        return self.session_runtime.render_inbox_item_as_message(item)

    def _build_summary_cards(self, *, inbox: AssistantInboxRead, tasks, reminders, suggestions) -> list[AssistantSummaryCard]:
        return self.session_runtime.build_summary_cards(
            inbox=inbox,
            tasks=tasks,
            reminders=reminders,
            suggestions=suggestions,
        )

    async def _build_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        history,
        events,
        tasks,
        profile,
        external_context,
        allow_answer_like_rule_short_circuit: bool = True,
    ) -> dict[str, Any]:
        return await self.plan_runtime.build_plan(
            user_id=user_id,
            user_message=user_message,
            history=history,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
            allow_answer_like_rule_short_circuit=allow_answer_like_rule_short_circuit,
        )

    async def _execute_actions(
        self,
        *,
        user_id: str,
        actions: list[dict[str, Any]],
        user_message: str,
        existing_events,
        profile,
    ) -> list[AssistantAction]:
        return await self.plan_runtime.execute_actions(
            user_id=user_id,
            actions=actions,
            user_message=user_message,
            existing_events=existing_events,
            profile=profile,
        )

    def _compose_reply(
        self,
        *,
        user_message: str = "",
        base_reply: str | None,
        actions: list[AssistantAction],
        requested_actions: list[dict[str, Any]],
        fallback_message: str,
        event_count: int,
        task_count: int,
        external_context: dict[str, Any] | None = None,
    ) -> str:
        reply = self.plan_runtime.compose_reply(
            user_message=user_message,
            base_reply=base_reply,
            actions=actions,
            requested_actions=requested_actions,
            fallback_message=fallback_message,
            event_count=event_count,
            task_count=task_count,
            external_context=external_context,
        )
        return self._prefix_if_model_unavailable(reply, user_message=user_message)

    def _compose_action_reply(
        self,
        *,
        prefers_chinese: bool,
        base_reply: str | None,
        actions: list[AssistantAction],
        requested_actions: list[dict[str, Any]],
        external_context: dict[str, Any],
    ) -> str:
        conflict_actions = [action for action in actions if action.type == "conflict_warning"]
        created_actions = [
            action for action in actions
            if action.type not in {"conflict_warning", "suggest_reschedule"}
        ]

        if conflict_actions and not created_actions:
            conflict = conflict_actions[0]
            titles = ", ".join(item["title"] for item in conflict.payload.get("conflicts", []))
            suggestions = conflict.payload.get("suggestions", [])
            if prefers_chinese:
                suggestion_text = ""
                if suggestions:
                    suggestion_text = "；可改约：" + "；".join(
                        f"{item['start_time']} 到 {item['end_time']}" for item in suggestions[:3]
                    )
                return f"我发现这个时间段和 {titles} 冲突了，所以先没有创建新日程。{suggestion_text}"
            suggestion_text = ""
            if suggestions:
                suggestion_text = " Suggested slots: " + ", ".join(
                    f"{item['start_time']} -> {item['end_time']}" for item in suggestions[:3]
                )
            return (
                "I found a scheduling conflict, so I did not create the new event. "
                f"The requested slot overlaps with: {titles}.{suggestion_text}"
            )

        summaries: list[str] = []
        for action in actions:
            if action.type == "create_event":
                summaries.append(self._format_event_summary(action=action, prefers_chinese=prefers_chinese, external_context=external_context))
            elif action.type == "create_task":
                summaries.append(self._format_task_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "suggest_schedule":
                summaries.append(self._format_schedule_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "apply_schedule":
                summaries.append(self._format_apply_schedule_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "propose_event":
                summaries.append(self._format_proposed_event_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "apply_event_proposal":
                summaries.append(self._format_apply_event_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "conflict_warning":
                summaries.append(
                    f"检测到时间冲突：{action.payload.get('title')}"
                    if prefers_chinese
                    else f"Conflict detected for: {action.payload.get('title')}"
                )

        if prefers_chinese:
            prefix = base_reply.strip() if base_reply else "我已经按你的意思处理好了。"
            return prefix + ("\n\n" + "\n".join(f"- {item}" for item in summaries) if summaries else "")

        prefix = base_reply.strip() if base_reply else "Done."
        return prefix + ("\n\n" + "\n".join(f"- {item}" for item in summaries) if summaries else "")

    def _format_event_summary(self, *, action: AssistantAction, prefers_chinese: bool, external_context: dict[str, Any]) -> str:
        departure_time = action.payload.get("departure_time")
        travel_duration = action.payload.get("travel_duration_minutes")
        location_name = action.payload.get("location_name")
        commute_summary = action.payload.get("commute_summary")
        weather_summary = action.payload.get("weather_summary")
        advice_summary = action.payload.get("advice_summary")
        if prefers_chinese:
            summary = f"已创建日程：{action.payload.get('title')}"
            if action.payload.get("start_time") and action.payload.get("end_time"):
                summary += f"（{action.payload.get('start_time')} 到 {action.payload.get('end_time')}）"
            if location_name:
                summary += f"，地点：{location_name}"
            if departure_time and travel_duration:
                summary += f"，建议 {departure_time} 出发，预计通勤 {travel_duration} 分钟"
            elif commute_summary:
                summary += f"，{commute_summary}"
            elif external_context.get("weather_now"):
                weather = external_context["weather_now"]
                summary += f"，当前天气 {weather.get('text')}，{weather.get('temp')}°C"
            if weather_summary:
                summary += f"，{weather_summary}"
            if advice_summary:
                summary += f"，{advice_summary}"
            return summary
        summary = f"Created event: {action.payload.get('title')}"
        if departure_time and travel_duration:
            summary += f" | leave at {departure_time} | {travel_duration} min travel"
        elif commute_summary:
            summary += f" | {commute_summary}"
        if weather_summary:
            summary += f" | {weather_summary}"
        if advice_summary:
            summary += f" | {advice_summary}"
        return summary

    def _format_task_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        if prefers_chinese:
            summary = f"已创建任务：{action.payload.get('content')}"
            if action.payload.get("deadline"):
                summary += f"，截止时间 {action.payload.get('deadline')}"
            return summary
        return f"Created task: {action.payload.get('content')}"

    def _format_schedule_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        items = action.payload.get("items") or []
        if not items:
            return "已生成调度建议。" if prefers_chinese else "Generated schedule suggestions."

        preview = items[:3]
        if prefers_chinese:
            lines = []
            for item in preview:
                label = item.get("title") or item.get("type") or "建议"
                slot = f"{item.get('start_time')} 到 {item.get('end_time')}"
                segment = ""
                if item.get("segment_index") and item.get("segment_total"):
                    segment = f"（第 {item.get('segment_index')}/{item.get('segment_total')} 段）"
                lines.append(f"{label}{segment}：{slot}")
            return "为你整理了这些可执行空档：" + "；".join(lines)

        lines = []
        for item in preview:
            label = item.get("title") or item.get("type") or "Suggestion"
            slot = f"{item.get('start_time')} -> {item.get('end_time')}"
            lines.append(f"{label}: {slot}")
        return "Schedule suggestions: " + "; ".join(lines)

    def _format_apply_schedule_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        items = action.payload.get("created_events") or []
        if prefers_chinese:
            if not items:
                return "已确认执行计划。"
            return "已按确认计划创建这些日程：" + "；".join(
                f"{item.get('title')}：{item.get('start_time')} 到 {item.get('end_time')}" for item in items[:5]
            )
        if not items:
            return "Applied the confirmed schedule."
        return "Created schedule blocks: " + "; ".join(
            f"{item.get('title')}: {item.get('start_time')} -> {item.get('end_time')}" for item in items[:5]
        )

    def _chunk_text(self, text: str, chunk_size: int = 24) -> list[str]:
        if not text:
            return [""]
        return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]

    def _format_proposed_event_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        if prefers_chinese:
            summary = f"待确认事件：{action.payload.get('title')}"
            if action.payload.get("start_time") and action.payload.get("end_time"):
                summary += f"（{action.payload.get('start_time')} 到 {action.payload.get('end_time')}）"
            if action.payload.get("location_name"):
                summary += f"，地点：{action.payload.get('location_name')}"
            return summary
        return f"Pending event proposal: {action.payload.get('title')}"

    def _format_apply_event_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        event = action.payload.get("created_event") or {}
        if prefers_chinese:
            return (
                f"已按确认创建事件：{event.get('title')}（{event.get('start_time')} 到 {event.get('end_time')}）"
            )
        return f"Created confirmed event: {event.get('title')}"

    async def _build_rule_based_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        events,
        tasks,
        profile,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        intent = self.text_runtime._classify_intent(user_message)
        if intent == "schedule_guidance":
            target_dates = self.text_runtime._select_schedule_guidance_dates(user_message)
            schedule_items = await self.suggestion_service.build_suggestions_for_dates(
                user_id=user_id,
                dates=target_dates,
                limit=6,
            )
            return {
                "reply": self.text_runtime._build_schedule_guidance_reply(
                    user_message=user_message,
                    events=events,
                    tasks=tasks,
                    profile=profile,
                    external_context=external_context,
                    schedule_items=schedule_items,
                ),
                "actions": [
                    {
                        "type": "suggest_schedule",
                        "payload": {
                            "items": [item.model_dump(mode="json") for item in schedule_items],
                            "target_dates": [item.isoformat() for item in target_dates],
                        },
                    }
                ] if schedule_items else [],
            }

        if intent == "progress_followup":
            followup_plan = await self._build_progress_followup_plan(
                user_id=user_id,
                user_message=user_message,
                tasks=tasks,
            )
            if followup_plan is not None:
                return followup_plan

        if intent == "event_context_advice":
            start_time, end_time = self.text_runtime._extract_time_range(user_message)
            event_payload = {
                "title": None,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "location_name": None,
                "event_type": "general",
            }
            event_context = await self._build_event_specific_context(
                payload=event_payload,
                profile=profile,
                user_message=user_message,
            )
            actions: list[dict[str, Any]] = []
            if event_payload.get("title") and event_payload.get("start_time") and event_payload.get("end_time"):
                actions.append(
                    {
                        "type": "propose_event",
                        "payload": {
                            **event_payload,
                            "commute_summary": event_context.get("commute_summary"),
                            "weather_summary": event_context.get("weather_summary"),
                            "advice_summary": event_context.get("advice_summary"),
                        },
                    }
                )
            return {
                "reply": self._build_event_advice_reply(
                    payload=event_payload,
                    user_message=user_message,
                    event_context=event_context,
                    profile=profile,
                ),
                "actions": actions,
            }

        if intent == "create_task":
            return {
                "reply": self.formatter.build_clarification_reply(
                    intent="create_task",
                    missing_fields=["content"],
                    prefers_chinese=self.text_runtime._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        if intent == "create_event":
            start_time, end_time = self.text_runtime._extract_time_range(user_message)
            missing_fields = []
            missing_fields.append("title")
            if not start_time:
                missing_fields.append("start_time")
            if not end_time:
                missing_fields.append("end_time")
            return {
                "reply": self.formatter.build_clarification_reply(
                    intent="create_event",
                    missing_fields=missing_fields or ["start_time", "end_time"],
                    prefers_chinese=self.text_runtime._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        return {"reply": "", "actions": []}

    def _build_event_preflight_reply(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        external_context: dict[str, Any],
        event_context: dict[str, Any] | None = None,
    ) -> str:
        event_context = event_context or {}
        prefers_chinese = self.text_runtime._prefers_chinese(user_message)
        location_name = payload.get("location_name")
        weather = external_context.get("weather_now")
        commute = external_context.get("default_commute")
        if prefers_chinese:
            reply = f"我准备为你创建“{payload.get('title')}”这个日程。"
            if payload.get("start_time") and payload.get("end_time"):
                reply += f" 时间是 {payload.get('start_time')} 到 {payload.get('end_time')}。"
            if location_name:
                reply += f" 地点在 {location_name}。"
            if event_context.get("commute_summary"):
                reply += f" {event_context.get('commute_summary')}"
            elif commute and location_name:
                reply += f" 按你当前默认通勤方式，常规通勤大约 {int(round(commute.get('duration_minutes', 0)))} 分钟。"
            if event_context.get("weather_summary"):
                reply += f" {event_context.get('weather_summary')}"
            elif weather:
                reply += f" 当前天气 {weather.get('text')}，{weather.get('temp')}°C，可一并参考。"
            if event_context.get("advice_summary"):
                reply += f" {event_context.get('advice_summary')}"
            return reply
        reply = f"I am ready to create the event '{payload.get('title')}'."
        if event_context.get("commute_summary"):
            reply += f" {event_context.get('commute_summary')}"
        elif location_name and commute:
            reply += f" Default commute context suggests about {int(round(commute.get('duration_minutes', 0)))} minutes."
        if event_context.get("weather_summary"):
            reply += f" {event_context.get('weather_summary')}"
        elif weather:
            reply += f" Current weather is {weather.get('text')} at {weather.get('temp')}°C."
        if event_context.get("advice_summary"):
            reply += f" {event_context.get('advice_summary')}"
        return reply

    def _build_event_advice_reply(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        event_context: dict[str, Any],
        profile,
    ) -> str:
        prefers_chinese = self.text_runtime._prefers_chinese(user_message)
        title = payload.get("title") or "这个安排"
        location_name = payload.get("location_name") or "目标地点"
        if prefers_chinese:
            parts = [f"关于“{title}”这个安排："]
            if payload.get("start_time") and payload.get("end_time"):
                parts.append(f"时间大致是 {payload.get('start_time')} 到 {payload.get('end_time')}。")
            parts.append(f"地点是 {location_name}。")
            if event_context.get("commute_summary"):
                parts.append(event_context["commute_summary"])
            elif event_context.get("runtime_origin"):
                parts.append(f"我会优先按你刚说的“{event_context['runtime_origin']}”作为出发地。")
            elif event_context.get("origin_clarification"):
                parts.append(f"我还不能判断你届时从哪里出发，{event_context['origin_clarification']}")
            elif re.search(r"几点出发|多久出发|什么时候出发|要提前多久|通勤|怎么去", user_message, re.I):
                parts.append("我还不能判断你届时从家、学校还是其他地方出发，请先补充出发地。")
            elif not (profile.home_location_name or profile.work_location_name):
                parts.append("你还没有设置 home/work 地点，所以我暂时不能精确估算出发时间。")
            if event_context.get("weather_summary"):
                parts.append(event_context["weather_summary"])
            if event_context.get("advice_summary"):
                parts.append(event_context["advice_summary"])
            if payload.get("start_time") and payload.get("end_time"):
                parts.append("如果这个安排合适，你可以直接回复“按这个建议创建”，我会帮你落成正式日程。")
            return " ".join(parts)

        parts = [f"For '{title}' at {location_name}:"]
        if event_context.get("commute_summary"):
            parts.append(str(event_context["commute_summary"]))
        elif event_context.get("runtime_origin"):
            parts.append(f"I will prioritize '{event_context['runtime_origin']}' as the departure origin.")
        elif event_context.get("origin_clarification"):
            parts.append(f"I still need the departure origin. {event_context['origin_clarification']}")
        elif re.search(r"几点出发|多久出发|什么时候出发|要提前多久|commute|how to go|how long", user_message, re.I):
            parts.append("I still need the departure origin before I can estimate a departure time.")
        if event_context.get("weather_summary"):
            parts.append(str(event_context["weather_summary"]))
        if event_context.get("advice_summary"):
            parts.append(str(event_context["advice_summary"]))
        if payload.get("start_time") and payload.get("end_time"):
            parts.append("If this looks good, reply 'confirm this suggestion' and I will create the event.")
        return " ".join(parts)

    def _fill_sparse_event_advice_payload(self, payload: dict[str, Any], *, user_message: str) -> None:
        if not payload.get("title"):
            match = re.search(r"(开会|会议|体检|上课|办手续|见面|聚餐|答辩|面试)", user_message)
            if match:
                payload["title"] = match.group(1)
        if not payload.get("location_name"):
            match = re.search(r"(?:去|到|在)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,12})\s*(?:开会|会议|体检|上课|办手续|见面|聚餐|答辩|面试)", user_message)
            if match:
                payload["location_name"] = match.group(1)

    def _recent_runtime_origin_from_history(self, history) -> str | None:
        for message in reversed(history or []):
            role = getattr(message, "role", None) if not isinstance(message, dict) else message.get("role")
            content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
            if role != "user" or not content:
                continue
            match = re.search(r"(?:我(?:明天|今天|下午|晚上|早上|上午)?(?:会)?(?:先)?在|在)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,12})", str(content))
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _extract_arrival_update_location(user_message: str) -> str | None:
        match = re.search(r"我(?:已经|已|现在)?在\s*([\u4e00-\u9fa5A-Za-z0-9]{1,12})\s*了", user_message)
        if not match:
            return None
        return match.group(1).strip()

    def _build_task_preflight_reply(self, *, payload: dict[str, Any], user_message: str) -> str:
        if self.text_runtime._prefers_chinese(user_message):
            reply = f"我准备为你创建任务“{payload.get('content')}”。"
            if payload.get("deadline"):
                reply += f" 截止时间会设为 {payload.get('deadline')}。"
            if payload.get("estimated_duration_minutes"):
                reply += f" 预计时长 {payload.get('estimated_duration_minutes')} 分钟。"
            if payload.get("can_split"):
                reply += " 我也会标记成可拆分任务。"
            return reply
        reply = f"I am ready to create the task '{payload.get('content')}'."
        if payload.get("deadline"):
            reply += f" Deadline: {payload.get('deadline')}."
        return reply

    async def _build_task_schedule_action(self, *, user_id: str, related_task_id: int) -> AssistantAction | None:
        dates = [datetime.now().date() + timedelta(days=offset) for offset in range(0, 4)]
        items = await self.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=dates,
            limit=6,
            related_task_ids=[related_task_id],
        )
        if not items:
            return None
        return AssistantAction(
            type="suggest_schedule",
            payload={
                "items": [item.model_dump(mode="json") for item in items],
                "related_task_id": related_task_id,
                "target_dates": [item.isoformat() for item in dates],
            },
        )

    def _hydrate_event_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        start_time, end_time = self.text_runtime._extract_time_range(user_message)
        extracted = {
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "event_type": "general",
        }
        enriched = dict(payload)
        for key in ("start_time", "end_time", "event_type"):
            if enriched.get(key) in (None, "", "event", "new event", "New event") and extracted.get(key):
                enriched[key] = extracted[key]
        return enriched

    def _hydrate_task_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        deadline = self.text_runtime._extract_task_deadline(user_message)
        extracted = {
            "deadline": deadline.isoformat() if deadline else None,
            "estimated_duration_minutes": self.text_runtime._extract_duration_minutes(user_message),
            "priority": 3,
            "can_split": bool(re.search(r"拆分|拆成|分成|分两次|分几次|分块", user_message)),
            "preferred_period": self.text_runtime._extract_period_preference(user_message),
        }
        enriched = dict(payload)
        for key in ("deadline", "estimated_duration_minutes", "priority", "can_split", "preferred_period"):
            if enriched.get(key) in (None, "", False) and extracted.get(key) not in (None, "", False):
                enriched[key] = extracted[key]
        return enriched

    async def _build_progress_followup_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        tasks,
    ) -> dict[str, Any] | None:
        followup_reminders = await self.reminder_repository.list_recent_task_followups(user_id=user_id, limit=6)
        active_tasks = self._select_progress_followup_tasks(user_message=user_message, tasks=tasks)

        target_task_ids = [task.id for task in active_tasks[:3]]
        schedule_items = await self.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 3)],
            limit=6,
            related_task_ids=target_task_ids or None,
        )

        prefers_chinese = self.text_runtime._prefers_chinese(user_message)
        reply = self._build_progress_followup_reply(
            prefers_chinese=prefers_chinese,
            tasks=active_tasks,
            followup_reminders=followup_reminders,
            schedule_items=schedule_items,
        )

        actions: list[dict[str, Any]] = []
        if schedule_items:
            actions.append(
                {
                    "type": "suggest_schedule",
                    "payload": {
                        "items": [item.model_dump(mode="json") for item in schedule_items],
                        "followup": True,
                    },
                }
            )
        return {"reply": reply, "actions": actions}

    def _select_progress_followup_tasks(self, *, user_message: str, tasks) -> list[Any]:
        candidates = [task for task in tasks if (task.status or "pending") not in {"canceled", "archived"}]
        ranked_candidates = self._rank_progress_followup_tasks(user_message=user_message, tasks=candidates)
        mentioned = [
            task
            for task in ranked_candidates
            if self._score_progress_followup_task(user_message=user_message, task=task) > 0
        ]
        if mentioned:
            return mentioned
        active_tasks = [task for task in candidates if (task.status or "pending") not in {"done"}]
        return self._rank_progress_followup_tasks(user_message=user_message, tasks=active_tasks)

    def _rank_progress_followup_tasks(self, *, user_message: str, tasks) -> list[Any]:
        scored: list[tuple[int, int, int, Any]] = []
        for task in tasks:
            score = self._score_progress_followup_task(user_message=user_message, task=task)
            scored.append((score, -(task.completed_minutes or 0), -(task.scheduled_minutes or 0), task))
        scored.sort(key=lambda item: (-item[0], item[1], item[2], getattr(item[3], "id", 0)))
        ranked = [item[3] for item in scored]
        return ranked if ranked else list(tasks)

    def _score_progress_followup_task(self, *, user_message: str, task) -> int:
        title = str(getattr(task, "content", "") or "").strip()
        if not title:
            return 0
        message = user_message or ""
        if title and title in message:
            return 8
        compact_title = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", title)
        compact_message = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", message)
        if compact_title and compact_title in compact_message:
            return 7
        if re.search(r"[\u4e00-\u9fa5]", title):
            best = 0
            for size in range(2, min(len(compact_title), 4) + 1):
                for index in range(0, len(compact_title) - size + 1):
                    token = compact_title[index : index + size]
                    if token in compact_message:
                        best = max(best, min(size, 4))
            if best:
                return best
        for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", title):
            if token and token in message:
                return max(4, len(token))
        return 0

    def _build_progress_followup_reply(
        self,
        *,
        prefers_chinese: bool,
        tasks,
        followup_reminders,
        schedule_items,
    ) -> str:
        if prefers_chinese:
            parts: list[str] = []
            if tasks:
                task = tasks[0]
                if (task.status or "pending") == "done":
                    parts.append(f"你问到的任务“{task.content}”目前已完成，已完成 {task.completed_minutes} 分钟。")
                else:
                    parts.append(
                        f"你当前最值得继续推进的是“{task.content}”，"
                        f"已完成 {task.completed_minutes} 分钟，"
                        f"还剩 {task.remaining_minutes if task.remaining_minutes is not None else '未知'} 分钟。"
                    )
            if followup_reminders:
                parts.append("最近执行反馈：" + "；".join(reminder.message for reminder in followup_reminders[:2]) + "。")
            if schedule_items:
                preview = "；".join(
                    f"{item.title}：{item.start_time.strftime('%m-%d %H:%M')}-{item.end_time.strftime('%H:%M')}"
                    for item in schedule_items[:3]
                )
                parts.append("我建议下一步这样排：" + preview + "。")
            return " ".join(parts) if parts else "目前没有新的进度变化。"

        parts = []
        if tasks:
            task = tasks[0]
            if (task.status or "pending") == "done":
                parts.append(f"The task you asked about, '{task.content}', is done with {task.completed_minutes} minutes completed.")
            else:
                parts.append(
                    f"Your main active task is '{task.content}', with {task.completed_minutes} minutes completed "
                    f"and {task.remaining_minutes if task.remaining_minutes is not None else 'unknown'} minutes remaining."
                )
        if followup_reminders:
            parts.append("Recent execution updates: " + "; ".join(reminder.message for reminder in followup_reminders[:2]) + ".")
        if schedule_items:
            parts.append(
                "Suggested next blocks: " + "; ".join(
                    f"{item.title}: {item.start_time.strftime('%m-%d %H:%M')}-{item.end_time.strftime('%H:%M')}"
                    for item in schedule_items[:3]
                ) + "."
            )
        return " ".join(parts) if parts else "No new progress updates yet."

    async def _persist_pending_action(
        self,
        *,
        user_id: str,
        session_id: int,
        existing_context: dict[str, Any],
        actions: list[AssistantAction],
    ) -> None:
        await self.plan_runtime.persist_pending_action(
            user_id=user_id,
            session_id=session_id,
            existing_context=existing_context,
            actions=actions,
        )

    async def _maybe_handle_pending_action_decision(
        self,
        *,
        user_id: str,
        session_id: int,
        session_context: dict[str, Any],
        user_message: str,
        profile,
    ) -> AssistantResponse | None:
        return await self.plan_runtime.maybe_handle_pending_action_decision(
            user_id=user_id,
            session_id=session_id,
            session_context=session_context,
            user_message=user_message,
            profile=profile,
        )

    async def _apply_pending_action(
        self,
        *,
        user_id: str,
        session_id: int,
        session_context: dict[str, Any],
        pending_action: dict[str, Any],
        profile,
        user_message: str,
    ) -> AssistantResponse:
        return await self.plan_runtime.apply_pending_action(
            user_id=user_id,
            session_id=session_id,
            session_context=session_context,
            pending_action=pending_action,
            profile=profile,
            user_message=user_message,
        )

    async def _apply_pending_event(
        self,
        *,
        user_id: str,
        session_id: int,
        session_context: dict[str, Any],
        pending_action: dict[str, Any],
        profile,
        user_message: str,
    ) -> AssistantResponse:
        return await self.plan_runtime.apply_pending_event(
            user_id=user_id,
            session_id=session_id,
            session_context=session_context,
            pending_action=pending_action,
            profile=profile,
            user_message=user_message,
        )

    def _classify_confirmation_intent(self, user_message: str) -> str | None:
        return self.plan_runtime.classify_confirmation_intent(user_message)

    async def _build_event_specific_context(
        self,
        *,
        payload: dict[str, Any],
        profile,
        user_message: str,
    ) -> dict[str, Any]:
        return await self.context_runtime.build_event_specific_context(
            payload=payload,
            profile=profile,
            user_message=user_message,
        )

    def _select_commute_origin(self, *, profile, user_message: str) -> tuple[str, str | None]:
        return self.context_runtime.select_commute_origin(profile=profile, user_message=user_message)

    def _is_outdoor_request(self, user_message: str, location_name: str | None) -> bool:
        return self.context_runtime.is_outdoor_request(user_message, location_name)

    def _find_event_conflicts(self, *, existing_events, start_time: datetime, end_time: datetime) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for event in existing_events:
            if event.start_time is None or event.end_time is None:
                continue
            if start_time < event.end_time and end_time > event.start_time:
                conflicts.append(
                    {
                        "event_id": event.id,
                        "title": event.title,
                        "start_time": event.start_time.isoformat(),
                        "end_time": event.end_time.isoformat(),
                    }
                )
        return conflicts

    def _suggest_alternative_slots(self, *, existing_events, start_time: datetime, end_time: datetime) -> list[dict[str, str]]:
        duration = end_time - start_time
        target_date = start_time.date()
        day_events = sorted(
            [
                event for event in existing_events
                if event.start_time is not None and event.end_time is not None and event.start_time.date() == target_date
            ],
            key=lambda item: item.start_time,
        )
        suggestions: list[dict[str, str]] = []
        cursor = datetime.combine(target_date, datetime.min.time()).replace(hour=8)
        day_end = datetime.combine(target_date, datetime.min.time()).replace(hour=22)
        for event in day_events:
            if event.start_time - cursor >= duration:
                suggestions.append({"start_time": cursor.isoformat(), "end_time": (cursor + duration).isoformat()})
                if len(suggestions) >= 3:
                    return suggestions
            cursor = max(cursor, event.end_time)
        if day_end - cursor >= duration and len(suggestions) < 3:
            suggestions.append({"start_time": cursor.isoformat(), "end_time": (cursor + duration).isoformat()})
        return suggestions

    async def _build_external_context(
        self,
        *,
        profile,
        user_message: str | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        return await self.context_runtime.build_external_context(
            profile=profile,
            user_message=user_message,
            intent=intent,
        )

    def _needs_external_context(
        self,
        *,
        user_message: str | None = None,
        intent: str | None = None,
    ) -> bool:
        return self.context_runtime.needs_external_context(
            user_message=user_message,
            intent=intent,
        )
