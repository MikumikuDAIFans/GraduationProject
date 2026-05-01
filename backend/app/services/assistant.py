"""Assistant service layer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import re
from typing import Any, AsyncIterator

from fastapi import HTTPException, status
from loguru import logger
from pydantic import ValidationError

from app.assistant_agents import AssistantAgentContext, AssistantConductor
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
    EventCreate,
    EventRead,
    TaskCreate,
)
from app.core.config import get_settings
from app.core.error_handler import AssistantError
from app.db.session import get_sessionmaker
from app.repositories.assistant import AssistantRepository
from app.repositories.events import EventRepository
from app.repositories.profiles import UserProfileRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.tasks import TaskRepository
from app.services.context import ContextService
from app.services.events import EventService
from app.services.assistant_response_formatter import AssistantResponseFormatter
from app.services.assistant_runtime_context import AssistantContextRuntime
from app.services.assistant_runtime_plan import AssistantPlanRuntime
from app.services.assistant_runtime_session import AssistantSessionRuntime
from app.services.assistant_runtime_text import AssistantTextRuntime
from app.services.suggestions import SuggestionService
from app.services.tasks import TaskService
from app.tools.gemini import GeminiClient
from app.workflow.graph import build_assistant_graph, run_workflow
from app.workflow.nodes import WorkflowNodes
from app.workflow.state import WorkflowState

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
        conductor_mode = (self.settings.assistant_conductor_mode or "legacy").lower()
        self.conductor = (
            AssistantConductor.build_default(self.text_runtime)
            if conductor_mode in {"shadow", "proposal"}
            else None
        )
        self.suggestion_service = SuggestionService()
        self.task_service = TaskService()
        self.gemini = GeminiClient()
        self.workflow_nodes = WorkflowNodes()
        self.workflow_graph = build_assistant_graph(self.workflow_nodes) if self.settings.enable_workflow else None

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

            history = await self.repository.list_messages(session.id)
            events = await self.event_repository.list_events(user_id=user_id)
            profile = await self.profile_repository.get_profile(user_id)
            tasks = await self.task_service.list_tasks(user_id=user_id)
            intent = self.text_runtime._classify_intent(payload.message)
            external_context = await self._build_external_context(
                profile=profile, user_message=payload.message, intent=intent,
            )
            session_context = dict(session.context_json or {})
            await self._run_conductor_for_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )

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

            if self.settings.enable_workflow:
                return await self._respond_with_workflow(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    session_context=session_context,
                    user_message=payload.message,
                    history=history,
                    profile=profile,
                )

            plan = await self._build_plan(
                user_id=user_id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
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

            history = await self.repository.list_messages(session.id)
            events = await self.event_repository.list_events(user_id=user_id)
            profile = await self.profile_repository.get_profile(user_id)
            tasks = await self.task_service.list_tasks(user_id=user_id)
            intent = self.text_runtime._classify_intent(payload.message)
            external_context = await self._build_external_context(
                profile=profile, user_message=payload.message, intent=intent,
            )
            session_context = dict(session.context_json or {})
            await self._run_conductor_for_message(
                user_id=user_id,
                session_id=session.id,
                user_message=payload.message,
                history=history,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )

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

            if self.settings.enable_workflow:
                async for item in self._respond_with_workflow_stream(
                    user_id=user_id,
                    session_id=session.id,
                    session_title=session.title,
                    session_context=session_context,
                    user_message=payload.message,
                    history=history,
                    profile=profile,
                ):
                    yield item
                return

            full_reply = ""
            used_streaming = False
            if self.gemini.enabled:
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
        if mode not in {"shadow", "proposal"}:
            logger.bind(component="assistant.conductor").warning(
                "Unknown ASSISTANT_CONDUCTOR_MODE={mode}; falling back to legacy",
                mode=mode,
            )
            return None
        if self.conductor is None:
            self.conductor = AssistantConductor.build_default(self.text_runtime)
        if mode == "proposal":
            logger.bind(component="assistant.conductor").warning(
                "ASSISTANT_CONDUCTOR_MODE=proposal requested before Action Executor is enabled; using shadow"
            )

        context = AssistantAgentContext(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            history=list(history or []),
            events=list(events or []),
            tasks=list(tasks or []),
            profile=profile,
            external_context=external_context,
        )
        try:
            result = await self.conductor.run(context, mode="shadow")
            logger.bind(component="assistant.conductor").info(
                "Assistant conductor shadow result: {result}",
                result=result.to_log_payload(),
            )
            return result
        except Exception as exc:
            logger.bind(component="assistant.conductor").warning(
                "Assistant conductor shadow failed: {error}",
                error=str(exc),
            )
            return None

    async def _run_workflow_for_message(
        self,
        *,
        user_id: str,
        session_id: int,
        user_message: str,
        history,
        profile,
    ) -> WorkflowState:
        initial_state: WorkflowState = {
            "user_message": user_message,
            "user_id": user_id,
            "session_id": str(session_id),
            "history": history,
            "profile": profile,
            "external_context": {},
            "intent": None,
            "extracted_slots": {},
            "confidence": 0.0,
            "existing_events": [],
            "existing_tasks": [],
            "habits": [],
            "weather": None,
            "traffic": None,
            "actions": [],
            "conflicts": [],
            "suggestions": [],
            "reply": "",
            "needs_clarification": False,
            "clarification_question": None,
            "retry_count": 0,
            "use_react": False,
            "react_observations": [],
            "react_steps": [],
            "assistant_service": self,
        }
        return await run_workflow(self.workflow_graph, initial_state)

    async def _respond_with_workflow(
        self,
        *,
        user_id: str,
        session_id: int,
        session_title: str,
        session_context: dict[str, Any],
        user_message: str,
        history,
        profile,
    ) -> AssistantResponse:
        workflow_state = await self._run_workflow_for_message(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            history=history,
            profile=profile,
        )
        actions = [self._ensure_assistant_action(action) for action in workflow_state.get("actions", [])]
        reply = self._format_reply_text(workflow_state.get("reply", ""), user_message=user_message)

        await self._persist_pending_action(
            user_id=user_id,
            session_id=session_id,
            existing_context=session_context,
            actions=actions,
        )
        await self.repository.create_message(
            session_id=session_id,
            role="assistant",
            content=reply,
            tool_calls_json=[action.model_dump() for action in actions] or None,
        )
        await self._maybe_autorename_session(
            user_id=user_id,
            session_id=session_id,
            session_title=session_title,
            user_message=user_message,
        )
        return AssistantResponse(session_id=session_id, reply=reply, actions=actions)

    async def _respond_with_workflow_stream(
        self,
        *,
        user_id: str,
        session_id: int,
        session_title: str,
        session_context: dict[str, Any],
        user_message: str,
        history,
        profile,
    ) -> AsyncIterator[dict[str, Any]]:
        workflow_state = await self._run_workflow_for_message(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            history=history,
            profile=profile,
        )
        actions = [self._ensure_assistant_action(action) for action in workflow_state.get("actions", [])]
        reply = self._format_reply_text(workflow_state.get("reply", ""), user_message=user_message)

        for chunk in self._chunk_text(reply):
            yield {"type": "token", "text": chunk}

        await self._persist_pending_action(
            user_id=user_id,
            session_id=session_id,
            existing_context=session_context,
            actions=actions,
        )
        await self.repository.create_message(
            session_id=session_id,
            role="assistant",
            content=reply,
            tool_calls_json=[action.model_dump() for action in actions] or None,
        )
        await self._maybe_autorename_session(
            user_id=user_id,
            session_id=session_id,
            session_title=session_title,
            user_message=user_message,
        )
        yield {"type": "actions", "actions": [action.model_dump() for action in actions]}
        yield {"type": "done", "session_id": session_id, "full_reply": reply}

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
    ) -> dict[str, Any]:
        return await self.plan_runtime.build_plan(
            user_id=user_id,
            user_message=user_message,
            history=history,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
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
        return self.plan_runtime.compose_reply(
            user_message=user_message,
            base_reply=base_reply,
            actions=actions,
            requested_actions=requested_actions,
            fallback_message=fallback_message,
            event_count=event_count,
            task_count=task_count,
            external_context=external_context,
        )

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
            event_payload = self.text_runtime._build_rule_based_event_payload(user_message)
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
            payload = self.text_runtime._build_rule_based_task_payload(user_message)
            if payload.get("content"):
                return {
                    "reply": self._build_task_preflight_reply(payload=payload, user_message=user_message),
                    "actions": [{"type": "create_task", "payload": payload}],
                }
            return {
                "reply": self.formatter.build_clarification_reply(
                    intent="create_task",
                    missing_fields=["content"],
                    prefers_chinese=self.text_runtime._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        event_payload = self.text_runtime._build_rule_based_event_payload(user_message)
        if event_payload.get("title") and event_payload.get("start_time") and event_payload.get("end_time"):
            event_context = await self._build_event_specific_context(
                payload=event_payload,
                profile=profile,
                user_message=user_message,
            )
            return {
                "reply": self._build_event_preflight_reply(
                    payload=event_payload,
                    user_message=user_message,
                    external_context=external_context,
                    event_context=event_context,
                ),
                "actions": [{"type": "create_event", "payload": event_payload}],
            }

        if intent == "create_event":
            missing_fields = []
            if not event_payload.get("title") or event_payload.get("title") == "New event":
                missing_fields.append("title")
            if not event_payload.get("start_time"):
                missing_fields.append("start_time")
            if not event_payload.get("end_time"):
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
        if event_context.get("weather_summary"):
            parts.append(str(event_context["weather_summary"]))
        if event_context.get("advice_summary"):
            parts.append(str(event_context["advice_summary"]))
        if payload.get("start_time") and payload.get("end_time"):
            parts.append("If this looks good, reply 'confirm this suggestion' and I will create the event.")
        return " ".join(parts)

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
        extracted = self.text_runtime._build_rule_based_event_payload(user_message)
        enriched = dict(payload)
        for key in ("title", "description", "start_time", "end_time", "location_name", "event_type"):
            if enriched.get(key) in (None, "", "event", "new event", "New event") and extracted.get(key):
                enriched[key] = extracted[key]
        enriched["title"] = self.text_runtime._normalize_event_title(
            current_title=enriched.get("title"),
            user_message=user_message,
        )
        return enriched

    def _hydrate_task_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        extracted = self.text_runtime._build_rule_based_task_payload(user_message)
        enriched = dict(payload)
        for key in ("content", "description", "deadline", "estimated_duration_minutes", "priority", "can_split", "preferred_period"):
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
        active_tasks = [task for task in tasks if (task.status or "pending") not in {"done"}]
        active_tasks.sort(
            key=lambda task: (
                -(task.completed_minutes or 0),
                -(task.scheduled_minutes or 0),
                task.id,
            )
        )

        target_task_ids = [task.id for task in active_tasks[:3]]
        schedule_items = await self.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 3)],
            limit=6,
            related_task_ids=target_task_ids or None,
        )

        if not followup_reminders and not schedule_items and not active_tasks:
            return None

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
