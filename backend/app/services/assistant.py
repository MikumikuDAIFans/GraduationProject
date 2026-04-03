"""Assistant service layer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import re
from typing import Any, AsyncIterator

from fastapi import HTTPException, status
from loguru import logger
from pydantic import ValidationError

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
    EventCreate,
    EventRead,
    TaskCreate,
)
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
from app.services.suggestions import SuggestionService
from app.services.tasks import TaskService
from app.tools.gemini import GeminiClient


CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
    "末": 5,
}

TIME_TOKEN_RAW = (
    r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)?\s*"
    r"(?:\d{1,2}(?::\d{2})?|[零〇一二两三四五六七八九十]{1,3}(?:点半|点一刻|点三刻|点[零〇一二三四五六七八九十]{1,3}分?|点|时半|时一刻|时三刻|时[零〇一二三四五六七八九十]{1,3}分?|时))"
)
TIME_TOKEN_PATTERN = re.compile(TIME_TOKEN_RAW)


class AssistantService:
    """Assistant session/message orchestration with Gemini-backed planning."""

    INBOX_ARCHIVE_RETENTION_DAYS = 7

    def __init__(self) -> None:
        session_factory = get_sessionmaker()
        self.repository = AssistantRepository(session_factory)
        self.event_repository = EventRepository(session_factory)
        self.profile_repository = UserProfileRepository(session_factory)
        self.reminder_repository = ReminderRepository(session_factory)
        self.task_repository = TaskRepository(session_factory)
        self.context_service = ContextService()
        self.event_service = EventService()
        self.formatter = AssistantResponseFormatter()
        self.suggestion_service = SuggestionService()
        self.task_service = TaskService()
        self.gemini = GeminiClient()

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
            external_context = await self._build_external_context(profile=profile)
            session_context = dict(session.context_json or {})

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
            external_context = await self._build_external_context(profile=profile)
            session_context = dict(session.context_json or {})

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
        items = [await self.get_session(user_id=user_id, session_id=session.id) for session in sessions]
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

    def _format_reply_text(self, reply: str, *, user_message: str) -> str:
        return self.formatter.format_reply(reply, prefers_chinese=self._prefers_chinese(user_message))

    async def _maybe_autorename_session(
        self,
        *,
        user_id: str,
        session_id: int,
        session_title: str,
        user_message: str,
    ) -> None:
        if session_title != "New chat" and not session_title.startswith("新对话 "):
            return
        title = self._extract_event_title(user_message) or self._extract_task_content(user_message) or user_message.strip()
        title = re.sub(r"\s+", " ", title).strip()[:32]
        if not title:
            return
        await self.repository.rename_session(session_id, user_id=user_id, title=title)

    async def get_session(self, user_id: str, session_id: int) -> AssistantSessionRead:
        session = await self.repository.get_session(session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assistant session not found")

        messages = await self.repository.list_messages(session_id)
        hidden_message_ids = set((session.context_json or {}).get("hidden_message_ids", []))
        return AssistantSessionRead(
            id=session.id,
            user_id=session.user_id,
            session_type=session.session_type,
            title=getattr(session, "title", "New chat"),
            is_archived=getattr(session, "is_archived", False),
            context_json=session.context_json,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[
                AssistantMessageRead.model_validate(item)
                for item in messages
                if item.id not in hidden_message_ids
            ],
        )

    async def get_current_session(self, user_id: str) -> AssistantCurrentSessionRead:
        session = await self.repository.get_latest_session(user_id=user_id, session_type="chat")
        if session is None:
            session = await self.repository.create_session(
                user_id=user_id,
                session_type="chat",
                context_json={"status": "assistant-active"},
            )

        inbox = await self.get_inbox(user_id=user_id)
        session = await self._sync_inbox_to_session(user_id=user_id, session=session, inbox=inbox)
        session_read = await self.get_session(user_id=user_id, session_id=session.id)
        return AssistantCurrentSessionRead(session=session_read, inbox=inbox)

    async def get_summary(self, user_id: str) -> AssistantSummaryRead:
        inbox = await self.get_inbox(user_id=user_id)
        tasks = await self.task_service.list_tasks(user_id=user_id)
        reminders = await self.reminder_repository.list_reminders(user_id=user_id, limit=20)
        today = await self.suggestion_service.get_today_suggestions(user_id=user_id)
        next_items = await self.suggestion_service.get_next_suggestions(user_id=user_id)
        cards = self._build_summary_cards(
            inbox=inbox,
            tasks=tasks,
            reminders=reminders,
            suggestions=[*today.items, *next_items.items],
        )
        return AssistantSummaryRead(
            generated_at=datetime.now(),
            unread_followups=inbox.unread_total,
            cards=cards,
        )

    async def get_inbox(self, user_id: str) -> AssistantInboxRead:
        session = await self.repository.get_latest_session(user_id=user_id, session_type="chat")
        session_context = dict(session.context_json or {}) if session is not None else {}
        inbox_state = dict(session_context.get("inbox_item_state", {}))
        cleaned_state = self._cleanup_inbox_state(inbox_state)
        if session is not None and cleaned_state != inbox_state:
            session_context["inbox_item_state"] = cleaned_state
            session = await self.repository.update_session_context(
                session.id,
                user_id=user_id,
                context_json=session_context,
            ) or session
            inbox_state = cleaned_state
        tasks = await self.task_service.list_tasks(user_id=user_id)
        reminders = await self.reminder_repository.list_recent_task_followups(user_id=user_id, limit=6)
        suggestion_items = await self.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 3)],
            limit=6,
        )

        inbox_items: list[AssistantInboxItem] = []

        for reminder in reminders[:3]:
            kind = "task_progress" if reminder.remind_type == "task_progress" else "task_replan"
            inbox_items.append(
                AssistantInboxItem(
                    id=f"reminder-{reminder.id}",
                    kind=kind,
                    title="Task Progress Update" if kind == "task_progress" else "Task Replan Needed",
                    description=reminder.message or reminder.remind_type,
                    priority=3 if kind == "task_replan" else 2,
                    thread_id=f"task-{reminder.target_id}",
                    action_label="Review Plan" if kind == "task_replan" else "Ask Assistant",
                    action_message="现在进展如何，接下来怎么安排",
                    related_task_id=reminder.target_id,
                    meta={"remind_at": reminder.remind_at.isoformat()},
                )
            )

        for task in tasks:
            if (task.status or "pending") in {"done"}:
                continue
            if task.completed_minutes > 0 or task.scheduled_minutes > 0:
                inbox_items.append(
                    AssistantInboxItem(
                        id=f"task-{task.id}",
                        kind="task_status",
                        title=task.content,
                        description=(
                            f"Status {task.status}. "
                            f"Completed {task.completed_minutes} min, remaining {task.remaining_minutes if task.remaining_minutes is not None else 'n/a'} min."
                        ),
                        priority=2,
                        thread_id=f"task-{task.id}",
                        action_label="Continue Planning",
                        action_message=f"继续安排任务 {task.content}",
                        related_task_id=task.id,
                        meta={
                            "scheduled_minutes": task.scheduled_minutes,
                            "completed_minutes": task.completed_minutes,
                            "remaining_minutes": task.remaining_minutes,
                        },
                    )
                )

        grouped_suggestions: dict[int | None, list] = {}
        for item in suggestion_items:
            grouped_suggestions.setdefault(item.related_task_id, []).append(item)

        for task_id, items in list(grouped_suggestions.items())[:3]:
            first = items[0]
            first_payload = first.model_dump(mode="json") if hasattr(first, "model_dump") else {}
            first_type = getattr(first, "type", None) or first_payload.get("type")
            inbox_items.append(
                AssistantInboxItem(
                    id=f"suggestion-{task_id or first.title}",
                    kind="task_replan" if first_type == "task_replan_slot" else "task_resume" if first_type == "task_resume_slot" else "task_schedule",
                    title=first.title,
                    description="；".join(
                        f"{item.start_time.strftime('%m-%d %H:%M')}-{item.end_time.strftime('%H:%M')}"
                        for item in items[:3]
                    ),
                    priority=3 if first_type == "task_replan_slot" else 2,
                    thread_id=f"task-{task_id}" if task_id is not None else None,
                    action_label="Use in Assistant",
                    action_message="现在进展如何，接下来怎么安排",
                    related_task_id=task_id,
                    meta={
                        "items": [item.model_dump(mode="json") for item in items[:3]],
                        "suggestion_type": first_type,
                        "start_time": first.start_time.isoformat(),
                        "end_time": first.end_time.isoformat(),
                    },
                )
            )

        grouped_items = self._group_inbox_items(inbox_items)
        visible_items = self._apply_inbox_state(grouped_items, inbox_state)
        visible_items.sort(key=lambda item: (-item.priority, item.id))
        visible_slice = visible_items[:8]
        unread_total = sum(1 for item in visible_slice if not item.read)
        return AssistantInboxRead(items=visible_slice, total=min(len(visible_items), 8), unread_total=unread_total)

    def _group_inbox_items(self, items: list[AssistantInboxItem]) -> list[AssistantInboxItem]:
        grouped: dict[int, list[AssistantInboxItem]] = {}
        standalone: list[AssistantInboxItem] = []

        for item in items:
            if item.related_task_id is None:
                standalone.append(item)
                continue
            grouped.setdefault(item.related_task_id, []).append(item)

        result: list[AssistantInboxItem] = []
        for task_id, task_items in grouped.items():
            if len(task_items) == 1:
                result.append(task_items[0])
                continue

            task_items.sort(key=lambda item: (-item.priority, item.id))
            primary = task_items[0]
            descriptions = [item.description for item in task_items[:3] if item.description]
            action_message = primary.action_message or "现在进展如何，接下来怎么安排"
            result.append(
                AssistantInboxItem(
                    id=f"group-task-{task_id}",
                    kind="task_followup_group",
                    title=primary.title if primary.kind == "task_status" else f"Task Follow-up · {task_id}",
                    description=" | ".join(descriptions),
                    priority=max(item.priority for item in task_items),
                    thread_id=f"task-{task_id}",
                    entry_count=len(task_items),
                    action_label="Open Follow-up",
                    action_message=action_message,
                    related_task_id=task_id,
                    meta={
                        "entries": [item.model_dump(mode="json") for item in task_items],
                    },
                )
            )

        result.extend(standalone)
        return result

    def _apply_inbox_state(
        self,
        items: list[AssistantInboxItem],
        state: dict[str, Any],
    ) -> list[AssistantInboxItem]:
        visible: list[AssistantInboxItem] = []
        for item in items:
            item_state = state.get(item.id, {}) if isinstance(state, dict) else {}
            if item_state.get("archived"):
                continue
            visible.append(
                item.model_copy(
                    update={
                        "read": bool(item_state.get("read", False)),
                        "archived": bool(item_state.get("archived", False)),
                        "updated_at": self._parse_state_datetime(item_state.get("updated_at")),
                    }
                )
            )
        return visible

    async def _sync_inbox_to_session(self, *, user_id: str, session, inbox: AssistantInboxRead):
        context_json = dict(session.context_json or {})
        surfaced_ids = set(context_json.get("surfaced_inbox_ids", []))
        hidden_message_ids = set(context_json.get("hidden_message_ids", []))
        task_followup_message_ids = {
            str(key): list(value)
            for key, value in (context_json.get("task_followup_message_ids", {}) or {}).items()
        }
        new_items = [item for item in inbox.items if item.id not in surfaced_ids and not item.archived]
        if not new_items:
            return session

        for item in new_items:
            task_key = str(item.related_task_id) if item.related_task_id is not None else None
            if item.kind == "task_followup_group" and task_key is not None:
                hidden_message_ids.update(task_followup_message_ids.get(task_key, []))
            content = self._render_inbox_item_as_message(item)
            created_message = await self.repository.create_message(
                session_id=session.id,
                role="assistant",
                content=content,
                tool_calls_json=[
                    {
                        "type": "inbox_followup",
                        "payload": item.model_dump(mode="json"),
                    }
                ],
            )
            surfaced_ids.add(item.id)
            if task_key is not None and created_message is not None:
                if item.kind == "task_followup_group":
                    task_followup_message_ids[task_key] = [created_message.id]
                else:
                    task_followup_message_ids.setdefault(task_key, []).append(created_message.id)
                    task_followup_message_ids[task_key] = task_followup_message_ids[task_key][-10:]

        context_json["surfaced_inbox_ids"] = list(surfaced_ids)[-30:]
        context_json["hidden_message_ids"] = list(hidden_message_ids)[-50:]
        context_json["task_followup_message_ids"] = task_followup_message_ids
        updated = await self.repository.update_session_context(
            session.id,
            user_id=user_id,
            context_json=context_json,
        )
        return updated or session

    async def mark_inbox_item(
        self,
        *,
        user_id: str,
        item_id: str,
        action: str,
    ) -> AssistantInboxRead:
        session = await self.repository.get_latest_session(user_id=user_id, session_type="chat")
        if session is None:
            session = await self.repository.create_session(
                user_id=user_id,
                session_type="chat",
                context_json={"status": "assistant-active"},
            )

        inbox = await self.get_inbox(user_id=user_id)
        item = next((entry for entry in inbox.items if entry.id == item_id), None)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assistant inbox item not found")

        context_json = dict(session.context_json or {})
        inbox_state = dict(context_json.get("inbox_item_state", {}))
        item_state = dict(inbox_state.get(item_id, {}))

        if action == "read":
            item_state["read"] = True
            item_state["updated_at"] = datetime.now().isoformat()
        elif action == "archive":
            item_state["read"] = True
            item_state["archived"] = True
            item_state["updated_at"] = datetime.now().isoformat()
            hidden_ids = set(context_json.get("hidden_message_ids", []))
            task_followup_message_ids = {
                str(key): list(value)
                for key, value in (context_json.get("task_followup_message_ids", {}) or {}).items()
            }
            if item.related_task_id is not None:
                hidden_ids.update(task_followup_message_ids.get(str(item.related_task_id), []))
            context_json["hidden_message_ids"] = list(hidden_ids)[-80:]
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported inbox action")

        inbox_state[item_id] = item_state
        context_json["inbox_item_state"] = self._compact_inbox_state(inbox_state)
        await self.repository.update_session_context(
            session.id,
            user_id=user_id,
            context_json=context_json,
        )
        return await self.get_inbox(user_id=user_id)

    def _compact_inbox_state(self, state: dict[str, Any], max_items: int = 100) -> dict[str, Any]:
        if len(state) <= max_items:
            return state
        compacted: dict[str, Any] = {}
        for key in list(state.keys())[-max_items:]:
            compacted[key] = state[key]
        return compacted

    def _cleanup_inbox_state(self, state: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        cleaned: dict[str, Any] = {}
        for key, value in state.items():
            if not isinstance(value, dict):
                continue
            if not value.get("archived"):
                cleaned[key] = value
                continue
            updated_at = self._parse_state_datetime(value.get("updated_at"))
            if updated_at is None:
                continue
            if updated_at >= now - timedelta(days=self.INBOX_ARCHIVE_RETENTION_DAYS):
                cleaned[key] = value
        return self._compact_inbox_state(cleaned)

    def _parse_state_datetime(self, raw_value: Any) -> datetime | None:
        if not raw_value or not isinstance(raw_value, str):
            return None
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    def _render_inbox_item_as_message(self, item: AssistantInboxItem) -> str:
        if item.kind == "task_followup_group":
            entries = item.meta.get("entries", []) if item.meta else []
            bullet_lines = []
            for entry in entries[:3]:
                bullet_lines.append(f"- {entry.get('title')}：{entry.get('description')}")
            if bullet_lines:
                return f"{item.title}：\n" + "\n".join(bullet_lines) + "\n你可以直接点操作，或回复“现在进展如何，接下来怎么安排”。"
            return f"{item.title}：{item.description}"
        if item.kind == "task_replan":
            return f"{item.title}：{item.description}\n你可以直接点操作，或回复“现在进展如何，接下来怎么安排”。"
        if item.kind == "task_progress":
            return f"{item.title}：{item.description}"
        if item.kind == "task_status":
            return f"{item.title} 当前状态更新：{item.description}"
        return f"{item.title}：{item.description}"

    def _build_summary_cards(self, *, inbox: AssistantInboxRead, tasks, reminders, suggestions) -> list[AssistantSummaryCard]:
        cards: list[AssistantSummaryCard] = []
        primary_inbox_item = inbox.items[0] if inbox.items else None

        cards.append(
            AssistantSummaryCard(
                id="followups",
                title="Assistant Follow-ups",
                value=str(inbox.unread_total),
                description="Unread proactive assistant threads waiting for review.",
                tone="warning" if inbox.unread_total else "calm",
                action_label="Open Inbox" if inbox.unread_total else None,
                thread_id=primary_inbox_item.thread_id if primary_inbox_item is not None else None,
                related_task_id=primary_inbox_item.related_task_id if primary_inbox_item is not None else None,
                related_event_id=primary_inbox_item.related_event_id if primary_inbox_item is not None else None,
                meta={
                    "unread_total": inbox.unread_total,
                    "primary_inbox_item_id": primary_inbox_item.id if primary_inbox_item is not None else None,
                },
                action_message="现在进展如何，接下来怎么安排" if inbox.unread_total else None,
            )
        )

        active_tasks = [task for task in tasks if (task.status or "pending") not in {"done"}]
        active_tasks.sort(
            key=lambda task: (
                -(task.completed_minutes or 0),
                -(task.scheduled_minutes or 0),
                task.id,
            )
        )
        if active_tasks:
            top_task = active_tasks[0]
            cards.append(
                AssistantSummaryCard(
                    id="top-task",
                    title="Primary Task",
                    value=top_task.content,
                    description=(
                        f"{top_task.status} · completed {top_task.completed_minutes} min · "
                        f"remaining {top_task.remaining_minutes if top_task.remaining_minutes is not None else 'n/a'} min."
                    ),
                    tone="focus",
                    action_label="Continue Planning",
                    thread_id=f"task-{top_task.id}",
                    related_task_id=top_task.id,
                    meta={
                        "task_status": top_task.status,
                        "completed_minutes": top_task.completed_minutes,
                        "remaining_minutes": top_task.remaining_minutes,
                    },
                    action_message=f"继续安排任务 {top_task.content}",
                )
            )

        if suggestions:
            first = suggestions[0]
            cards.append(
                AssistantSummaryCard(
                    id="next-suggestion",
                    title="Next Suggested Move",
                    value=first.title,
                    description=f"{first.start_time.strftime('%m-%d %H:%M')} - {first.end_time.strftime('%H:%M')}",
                    tone="action",
                    action_label="Use in Assistant",
                    thread_id=f"task-{first.related_task_id}" if first.related_task_id is not None else None,
                    related_task_id=first.related_task_id,
                    related_event_id=first.related_event_id,
                    meta={
                        "suggestion_type": first.type,
                        "start_time": first.start_time.isoformat(),
                        "end_time": first.end_time.isoformat(),
                    },
                    action_message="现在进展如何，接下来怎么安排",
                )
            )

        pending_reminders = [item for item in reminders if (item.status or "pending") != "read"]
        pending_reminders.sort(key=lambda reminder: reminder.remind_at)
        if pending_reminders:
            next_reminder = pending_reminders[0]
            cards.append(
                AssistantSummaryCard(
                    id="next-reminder",
                    title="Next Reminder",
                    value=next_reminder.remind_type,
                    description=next_reminder.message or next_reminder.remind_at.isoformat(),
                    tone="info",
                    thread_id=f"{next_reminder.target_type}-{next_reminder.target_id}",
                    related_task_id=next_reminder.target_id if next_reminder.target_type == "task" else None,
                    related_event_id=next_reminder.target_id if next_reminder.target_type == "event" else None,
                    meta={
                        "target_type": next_reminder.target_type,
                        "target_id": next_reminder.target_id,
                        "remind_at": next_reminder.remind_at.isoformat(),
                    },
                )
            )

        return cards[:4]

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
        intent = self._classify_intent(user_message)
        fallback_plan = await self._build_rule_based_plan(
            user_id=user_id,
            user_message=user_message,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
        )

        if intent in {"schedule_guidance", "event_context_advice", "progress_followup"} and (fallback_plan.get("reply") or fallback_plan.get("actions")):
            return fallback_plan

        history_payload = [{"role": item.role, "content": item.content} for item in history]
        event_payload = [
            {
                "title": item.title,
                "start_time": item.start_time.isoformat() if item.start_time else None,
                "end_time": item.end_time.isoformat() if item.end_time else None,
                "location_name": item.location_name,
                "status": item.status,
            }
            for item in events
        ]
        task_payload = [
            {
                "content": item.content,
                "status": item.status,
                "deadline": item.deadline.isoformat() if item.deadline else None,
                "priority": item.priority,
            }
            for item in tasks
        ]

        try:
            plan = await self.gemini.generate_plan(
                user_message=user_message,
                history=history_payload,
                events=event_payload,
                tasks=task_payload,
                profile={
                    "display_name": profile.display_name,
                    "timezone": profile.timezone,
                    "home_location_name": profile.home_location_name,
                    "work_location_name": profile.work_location_name,
                    "transport_preference": profile.transport_preference,
                    "wake_up_time": profile.wake_up_time,
                    "sleep_time": profile.sleep_time,
                },
                external_context=external_context,
            )
        except Exception as exc:
            logger.bind(component="assistant.plan").warning("Gemini plan generation failed: {error}", error=str(exc))
            plan = {"reply": "", "actions": []}

        if fallback_plan.get("actions") and not plan.get("actions"):
            return fallback_plan
        if not plan.get("reply") and fallback_plan.get("reply"):
            plan["reply"] = fallback_plan["reply"]
        if not plan.get("reply") and not plan.get("actions"):
            return fallback_plan
        return plan

    async def _execute_actions(
        self,
        *,
        user_id: str,
        actions: list[dict[str, Any]],
        user_message: str,
        existing_events,
        profile,
    ) -> list[AssistantAction]:
        executed: list[AssistantAction] = []

        for item in actions:
            action_type = item.get("type")
            payload = item.get("payload") or {}

            try:
                if action_type == "create_event":
                    payload = self._hydrate_event_payload(payload=payload, user_message=user_message)
                    event_payload = EventCreate.model_validate(payload)
                    if event_payload.start_time is None or event_payload.end_time is None:
                        continue
                    conflicts = await self.event_service.detect_conflicts(
                        user_id=user_id,
                        start_time=event_payload.start_time,
                        end_time=event_payload.end_time,
                        buffer_before=event_payload.buffer_before or 0,
                        buffer_after=event_payload.buffer_after or 0,
                    )
                    if conflicts:
                        serialized_conflicts = [
                            {
                                "event_id": conflict.id,
                                "title": conflict.title,
                                "start_time": conflict.start_time.isoformat() if conflict.start_time else None,
                                "end_time": conflict.end_time.isoformat() if conflict.end_time else None,
                            }
                            for conflict in conflicts
                        ]
                        suggestions = await self.event_service.find_alternative_slots(
                            user_id=user_id,
                            duration_minutes=int((event_payload.end_time - event_payload.start_time).total_seconds() // 60),
                            preferred_date=event_payload.start_time.date(),
                            buffer_before=event_payload.buffer_before or 0,
                            buffer_after=event_payload.buffer_after or 0,
                        )
                        executed.append(
                            AssistantAction(
                                type="conflict_warning",
                                payload={
                                    "title": event_payload.title,
                                    "event_title": event_payload.title,
                                    "start_time": event_payload.start_time.isoformat(),
                                    "end_time": event_payload.end_time.isoformat(),
                                    "conflicts": serialized_conflicts,
                                    "suggestions": suggestions,
                                },
                            )
                        )
                        if suggestions:
                            executed.append(
                                AssistantAction(
                                    type="suggest_reschedule",
                                    payload={
                                        "event_title": event_payload.title,
                                        "alternatives": suggestions,
                                    },
                                )
                            )
                        continue
                    created = await self.event_service.create_event(user_id=user_id, payload=event_payload)
                    event_context = await self._build_event_specific_context(
                        payload={
                            "location_name": created.location_name,
                            "location_coords": getattr(created, "location_coords", None),
                            "start_time": created.start_time.isoformat() if created.start_time else None,
                            "end_time": created.end_time.isoformat() if created.end_time else None,
                            "title": created.title,
                        },
                        profile=profile,
                        user_message=user_message,
                    )
                    executed.append(
                        AssistantAction(
                            type="create_event",
                            payload={
                                "event_id": created.id,
                                "title": created.title,
                                "start_time": created.start_time.isoformat() if created.start_time else None,
                                "end_time": created.end_time.isoformat() if created.end_time else None,
                                "location_name": created.location_name,
                                "departure_time": created.departure_time.isoformat() if created.departure_time else None,
                                "travel_duration_minutes": created.travel_duration_minutes,
                                "sync_status": created.sync_status,
                                "commute_summary": event_context.get("commute_summary"),
                                "weather_summary": event_context.get("weather_summary"),
                                "advice_summary": event_context.get("advice_summary"),
                            },
                        )
                    )
                elif action_type == "create_task":
                    payload = self._hydrate_task_payload(payload=payload, user_message=user_message)
                    task_payload = TaskCreate.model_validate(payload)
                    created = await self.task_repository.create_task({"user_id": user_id, **task_payload.model_dump()})
                    executed.append(
                        AssistantAction(
                            type="create_task",
                            payload={
                                "task_id": created.id,
                                "content": created.content,
                                "deadline": created.deadline.isoformat() if created.deadline else None,
                                "estimated_duration_minutes": created.estimated_duration_minutes,
                                "preferred_period": created.preferred_period,
                            },
                        )
                    )
                    schedule_action = await self._build_task_schedule_action(
                        user_id=user_id,
                        related_task_id=created.id,
                    )
                    if schedule_action is not None:
                        executed.append(schedule_action)
                elif action_type == "suggest_schedule":
                    executed.append(AssistantAction(type="suggest_schedule", payload=payload))
                elif action_type == "propose_event":
                    executed.append(AssistantAction(type="propose_event", payload=payload))
            except ValidationError:
                continue

        return executed

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
        external_context = external_context or {}
        prefers_chinese = self._prefers_chinese(user_message)
        if actions:
            return self._compose_action_reply(
                prefers_chinese=prefers_chinese,
                base_reply=base_reply,
                actions=actions,
                requested_actions=requested_actions,
                external_context=external_context,
            )

        if requested_actions:
            if prefers_chinese:
                return "我理解你想让我创建内容，但目前抽取到的时间、地点或任务信息还不够明确。你可以再补一句更具体的话。"
            return (
                "I understood that you wanted me to create something, but I could not safely execute it "
                "with the extracted details. Please provide a clearer time or task detail and I will try again."
            )

        if base_reply and base_reply.strip():
            return base_reply.strip()

        if prefers_chinese:
            return (
                "Gemini 当前暂时不可用，但你的消息已经保存。"
                f"我看到你当前有 {event_count} 个日程、{task_count} 个任务。"
                f"你可以继续从这句话接着说：{fallback_message}"
            )
        return (
            "Gemini is temporarily unavailable, but your message has been saved. "
            f"I can see {event_count} events and {task_count} tasks in your current context. "
            f"Please continue from: {fallback_message}"
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
        intent = self._classify_intent(user_message)
        if intent == "schedule_guidance":
            target_dates = self._select_schedule_guidance_dates(user_message)
            schedule_items = await self.suggestion_service.build_suggestions_for_dates(
                user_id=user_id,
                dates=target_dates,
                limit=6,
            )
            return {
                "reply": self._build_schedule_guidance_reply(
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
            event_payload = self._build_rule_based_event_payload(user_message)
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
            payload = self._build_rule_based_task_payload(user_message)
            if payload.get("content"):
                return {
                    "reply": self._build_task_preflight_reply(payload=payload, user_message=user_message),
                    "actions": [{"type": "create_task", "payload": payload}],
                }
            return {
                "reply": self.formatter.build_clarification_reply(
                    intent="create_task",
                    missing_fields=["content"],
                    prefers_chinese=self._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        event_payload = self._build_rule_based_event_payload(user_message)
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
                    prefers_chinese=self._prefers_chinese(user_message),
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
        prefers_chinese = self._prefers_chinese(user_message)
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
        prefers_chinese = self._prefers_chinese(user_message)
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
        if self._prefers_chinese(user_message):
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
        extracted = self._build_rule_based_event_payload(user_message)
        enriched = dict(payload)
        for key in ("title", "description", "start_time", "end_time", "location_name", "event_type"):
            if enriched.get(key) in (None, "", "event", "new event", "New event") and extracted.get(key):
                enriched[key] = extracted[key]
        enriched["title"] = self._normalize_event_title(
            current_title=enriched.get("title"),
            user_message=user_message,
        )
        return enriched

    def _hydrate_task_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        extracted = self._build_rule_based_task_payload(user_message)
        enriched = dict(payload)
        for key in ("content", "description", "deadline", "estimated_duration_minutes", "priority", "can_split", "preferred_period"):
            if enriched.get(key) in (None, "", False) and extracted.get(key) not in (None, "", False):
                enriched[key] = extracted[key]
        return enriched

    def _build_rule_based_event_payload(self, user_message: str) -> dict[str, Any]:
        start_time, end_time = self._extract_time_range(user_message)
        location_name = self._extract_location(user_message)
        title = self._extract_event_title(user_message) or self._extract_event_topic(user_message)
        description = None
        if location_name and ("通勤" in user_message or "天气" in user_message):
            description = "assistant enriched with travel/weather context"
        return {
            "title": title or "New event",
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "location_name": location_name,
            "description": description,
            "event_type": "general",
        }

    def _build_rule_based_task_payload(self, user_message: str) -> dict[str, Any]:
        content = self._extract_task_content(user_message)
        deadline = self._extract_task_deadline(user_message)
        duration = self._extract_duration_minutes(user_message)
        preferred_period = self._extract_period_preference(user_message)
        can_split = bool(re.search(r"拆分|拆成|分成|分两次|分几次|分块", user_message))
        return {
            "content": content,
            "deadline": deadline.isoformat() if deadline else None,
            "estimated_duration_minutes": duration,
            "priority": 3,
            "can_split": can_split,
            "preferred_period": preferred_period,
        }

    def _classify_intent(self, user_message: str) -> str:
        has_time = self._extract_time_range(user_message)[0] is not None
        has_location = self._extract_location(user_message) is not None
        has_event_keyword = bool(
            re.search(r"日程|会议|开会|组会|答辩|面试|约会|聚餐|上课|演示|汇报|看医生|meeting|event|appointment", user_message, re.I)
        )
        has_task_keyword = bool(
            re.search(r"任务|待办|todo|deadline|截止|完成|复习|整理|准备|记得|提醒我", user_message, re.I)
        )
        asks_guidance = bool(
            re.search(r"怎么安排|安排一下|插进去|空档|空闲|看看.*日程|今天.*有什么|明天.*有什么|schedule|plan my", user_message, re.I)
        )
        asks_event_advice = bool(
            re.search(r"几点出发|多久出发|多久到|要不要带伞|合适吗|天气怎么样|路上|通勤|怎么去|要提前多久", user_message, re.I)
        )
        asks_progress_followup = bool(
            re.search(r"现在怎么样|进展如何|接下来怎么安排|继续安排|继续排|还有多少|还剩多少|下一步|接下来呢|继续做什么", user_message, re.I)
        )
        has_schedule_phrase = bool(
            re.search(r"安排进去|插进去|塞进去|排进去|安排到|安排一下|怎么安排|空档|空闲", user_message, re.I)
        ) or bool(self._extract_requested_items(user_message))
        if asks_progress_followup:
            return "progress_followup"
        if asks_guidance:
            return "schedule_guidance"
        if asks_event_advice and (has_time or has_event_keyword or has_location):
            return "event_context_advice"
        if has_schedule_phrase:
            return "schedule_guidance"
        if has_event_keyword or has_time:
            return "create_event"
        if has_task_keyword:
            return "create_task"
        return "unknown"

    def _build_schedule_guidance_reply(
        self,
        *,
        user_message: str,
        events,
        tasks,
        profile,
        external_context: dict[str, Any],
        schedule_items,
    ) -> str:
        target_date = self._extract_target_date(user_message, datetime.now().date())
        day_events = sorted(
            [
                event for event in events
                if event.start_time is not None and event.end_time is not None and event.start_time.date() == target_date
            ],
            key=lambda item: item.start_time,
        )
        free_slots = self._compute_free_slots(day_events=day_events, target_date=target_date)
        preferred_tasks = self._extract_requested_items(user_message)
        if self._prefers_chinese(user_message):
            parts = [f"{target_date.isoformat()} 你当前有 {len(day_events)} 个已安排日程。"]
            if day_events:
                parts.append(
                    "已排好的事项有：" + "；".join(
                        f"{item.title}（{item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')}）"
                        for item in day_events[:4]
                    )
                )
            if free_slots:
                parts.append(
                    "可用空档：" + "；".join(
                        f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" for start, end in free_slots[:3]
                    )
                )
            if preferred_tasks:
                parts.append("你提到的事项可以优先放进这些空档：" + "、".join(preferred_tasks[:3]) + "。")
            elif tasks:
                parts.append(f"当前待办里还有 {len(tasks)} 项，可以优先放入这些空档。")
            if schedule_items:
                preview = []
                for item in schedule_items[:4]:
                    segment = ""
                    if item.segment_index and item.segment_total:
                        segment = f"（第 {item.segment_index}/{item.segment_total} 段）"
                    preview.append(
                        f"{item.title}{segment}：{item.start_time.strftime('%m-%d %H:%M')}-{item.end_time.strftime('%H:%M')}"
                    )
                parts.append("系统建议：" + "；".join(preview) + "。")
            commute = external_context.get("default_commute")
            if profile.work_location_name and commute:
                parts.append(
                    f"按默认通勤方式，从 {profile.home_location_name or '家'} 到 {profile.work_location_name} 约 {int(round(commute.get('duration_minutes', 0)))} 分钟。"
                )
            weather = external_context.get("weather_now")
            if weather:
                parts.append(f"当前天气 {weather.get('text')}，{weather.get('temp')}°C。")
            return " ".join(parts)
        parts = [f"You have {len(day_events)} scheduled events on {target_date.isoformat()}."]
        if free_slots:
            parts.append(
                "Free slots: " + ", ".join(
                    f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" for start, end in free_slots[:3]
                )
            )
        if schedule_items:
            parts.append(
                "Suggested plan: " + ", ".join(
                    f"{item.title} {item.start_time.strftime('%m-%d %H:%M')}-{item.end_time.strftime('%H:%M')}"
                    for item in schedule_items[:4]
                )
            )
        return " ".join(parts)

    def _extract_time_range(
        self,
        user_message: str,
        *,
        reference: datetime | None = None,
    ) -> tuple[datetime | None, datetime | None]:
        now = reference or datetime.now()
        base_date = self._extract_target_date(user_message, now.date())
        lower = user_message.lower()

        english_patterns = [
            r"from\s+(\d{1,2}:\d{2})\s+to\s+(\d{1,2}:\d{2})",
            r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})",
            r"(\d{1,2}:\d{2})\s*到\s*(\d{1,2}:\d{2})",
        ]
        for pattern in english_patterns:
            match = re.search(pattern, lower if "from" in pattern else user_message)
            if not match:
                continue
            start_raw, end_raw = match.groups()
            start_dt = datetime.fromisoformat(f"{base_date.isoformat()}T{start_raw}")
            end_dt = datetime.fromisoformat(f"{base_date.isoformat()}T{end_raw}")
            return start_dt, end_dt

        range_match = re.search(
            rf"({TIME_TOKEN_RAW})\s*(?:到|至|~|～|—|－|-)\s*({TIME_TOKEN_RAW})",
            user_message,
        )
        if range_match:
            start_dt, start_period = self._parse_time_token(range_match.group(1), base_date)
            end_dt, _ = self._parse_time_token(range_match.group(2), base_date, inherited_period=start_period)
            if start_dt and end_dt:
                if end_dt <= start_dt:
                    end_dt += timedelta(hours=12)
                return start_dt, end_dt

        token_match = TIME_TOKEN_PATTERN.search(user_message)
        if token_match:
            start_dt, _ = self._parse_time_token(token_match.group(0), base_date)
            if start_dt and re.search(r"日程|会议|开会|组会|答辩|面试|约会|聚餐|上课|演示|汇报|看医生|meeting|event|appointment", user_message, re.I):
                return start_dt, start_dt + timedelta(minutes=self._extract_duration_minutes(user_message) or 60)

        return None, None

    def _extract_target_date(self, user_message: str, reference_date: date) -> date:
        if "大后天" in user_message:
            return reference_date + timedelta(days=3)
        if "后天" in user_message:
            return reference_date + timedelta(days=2)
        if "明天" in user_message or "明早" in user_message or "明晚" in user_message:
            return reference_date + timedelta(days=1)
        if "今天" in user_message or "今晚" in user_message or "今早" in user_message:
            return reference_date

        explicit = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})月(\d{1,2})日", user_message)
        if explicit:
            year_raw, month_raw, day_raw = explicit.groups()
            year = int(year_raw) if year_raw else reference_date.year
            return date(year, int(month_raw), int(day_raw))

        slash_explicit = re.search(r"(?:(\d{4})[-/])?(\d{1,2})[-/](\d{1,2})", user_message)
        if slash_explicit:
            year_raw, month_raw, day_raw = slash_explicit.groups()
            year = int(year_raw) if year_raw else reference_date.year
            return date(year, int(month_raw), int(day_raw))

        weekday_match = re.search(r"(下下周|下周|本周|这周|周|星期)(一|二|三|四|五|六|日|天|末)", user_message)
        if weekday_match:
            prefix, weekday_raw = weekday_match.groups()
            target_weekday = WEEKDAY_MAP[weekday_raw]
            current_weekday = reference_date.weekday()
            day_delta = (target_weekday - current_weekday) % 7
            if prefix == "下周":
                day_delta = day_delta or 7
            elif prefix == "下下周":
                day_delta = (day_delta or 7) + 7
            elif prefix in {"周", "星期"} and day_delta == 0:
                day_delta = 7
            return reference_date + timedelta(days=day_delta)

        return reference_date

    def _parse_time_token(
        self,
        token: str,
        base_date: date,
        *,
        inherited_period: str | None = None,
    ) -> tuple[datetime | None, str | None]:
        raw = token.strip().replace(" ", "")
        period_match = re.match(r"(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)", raw)
        period = period_match.group(1) if period_match else inherited_period
        core = raw[len(period_match.group(1)):] if period_match else raw

        if ":" in core:
            hour_raw, minute_raw = core.split(":", 1)
            hour = int(hour_raw)
            minute = int(minute_raw)
        else:
            marker = "点" if "点" in core else "时" if "时" in core else None
            if marker is None:
                return None, period
            hour_raw, _, minute_raw = core.partition(marker)
            hour = self._parse_number(hour_raw)
            minute = self._parse_minute_fragment(minute_raw)
            if hour is None:
                return None, period

        hour = self._apply_period(hour, period)
        return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute), period

    def _apply_period(self, hour: int, period: str | None) -> int:
        if period in {"下午", "傍晚", "晚上", "今晚", "明晚"} and 1 <= hour < 12:
            return hour + 12
        if period == "中午" and 1 <= hour < 11:
            return hour + 12
        if period == "凌晨" and hour == 12:
            return 0
        return hour

    def _parse_minute_fragment(self, fragment: str) -> int:
        fragment = fragment.strip()
        if not fragment:
            return 0
        if fragment == "半":
            return 30
        if fragment == "一刻":
            return 15
        if fragment == "三刻":
            return 45
        fragment = fragment.replace("分", "")
        if fragment.isdigit():
            return int(fragment)
        return self._parse_number(fragment) or 0

    def _parse_number(self, raw: str | None) -> int | None:
        if not raw:
            return None
        raw = raw.strip()
        if raw.isdigit():
            return int(raw)
        if raw in CHINESE_DIGITS:
            return CHINESE_DIGITS[raw]
        if "十" in raw:
            left, _, right = raw.partition("十")
            tens = 1 if left == "" else CHINESE_DIGITS.get(left)
            ones = 0 if right == "" else CHINESE_DIGITS.get(right)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones
        total = 0
        for char in raw:
            if char not in CHINESE_DIGITS:
                return None
            total = total * 10 + CHINESE_DIGITS[char]
        return total

    def _extract_duration_minutes(self, user_message: str) -> int | None:
        minute_match = re.search(r"(\d{1,3}|[零〇一二两三四五六七八九十]{1,3})\s*分钟", user_message)
        if minute_match:
            return self._parse_number(minute_match.group(1))
        hour_match = re.search(r"(\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*(?:个)?小时", user_message)
        if hour_match:
            parsed = self._parse_number(hour_match.group(1))
            return parsed * 60 if parsed else None
        if "半小时" in user_message:
            return 30
        return None

    def _extract_location(self, user_message: str) -> str | None:
        patterns = [
            r"在(?P<location>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{2,40}?)(?=开会|见面|碰头|集合|吃饭|讨论|复习|上课|答辩|演示|汇报|参加|$|，|。|,)",
            r"(?:去|到|于)(?P<location>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{2,40}?)(?=开会|见面|碰头|集合|吃饭|讨论|复习|上课|答辩|演示|汇报|参加|$|，|。|,)",
            r"(?:at|in|to)\s+(?P<location>[A-Za-z0-9][A-Za-z0-9\s,\-]{2,40}?)(?:\s+(?:for|from|tomorrow|today|next|at)\b|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, user_message, re.I)
            if match:
                location = match.group("location").strip(" ，。,")
                location = re.sub(r"(开组会|开会|组会|见面|碰头|集合|吃饭|讨论|复习|上课|答辩|演示|汇报|参加)$", "", location).strip()
                if location:
                    return location
        return None

    def _normalize_event_title(self, *, current_title: str | None, user_message: str) -> str:
        if current_title and current_title.lower() not in {"new event", "event"}:
            return current_title
        extracted = self._extract_event_title(user_message) or self._extract_event_topic(user_message)
        return extracted or current_title or "New event"

    def _extract_event_title(self, user_message: str) -> str | None:
        lower = user_message.lower()
        patterns = [
            r"called\s+(.+?)(?:\s+tomorrow|\s+from|\s+at|$)",
            r"named\s+(.+?)(?:\s+tomorrow|\s+from|\s+at|$)",
            r"叫\s*([^\s，。,\.]+)",
            r"名为\s*([^\s，。,\.]+)",
            r"[“\"]([^”\"]{2,30})[”\"]",
        ]
        for pattern in patterns:
            match = re.search(pattern, lower if "called" in pattern or "named" in pattern else user_message)
            if not match:
                continue
            title = match.group(1).strip(" \"'“”")
            if title:
                return title
        return None

    def _extract_event_topic(self, user_message: str) -> str | None:
        keyword_patterns = [
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}组会)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}答辩(?:彩排)?)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}会议)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}开会)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}复习)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}演示)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}汇报)",
            r"([A-Za-z0-9\u4e00-\u9fa5]{0,10}面试)",
        ]
        for pattern in keyword_patterns:
            match = re.search(pattern, user_message)
            if match:
                candidate = match.group(1).strip()
                if candidate:
                    return candidate
        cleaned = re.sub(r"(帮我|请|麻烦|安排|创建|新增|添加|给我|明天|今天|后天|今晚|下午|上午|早上|晚上)", "", user_message)
        cleaned = TIME_TOKEN_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"\d{1,2}:\d{2}", "", cleaned)
        cleaned = re.sub(r"(在|去|到).{0,20}", "", cleaned)
        cleaned = re.sub(r"[，。,!！?？]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:24].strip() or None

    def _extract_task_content(self, user_message: str) -> str | None:
        text = user_message.strip()
        text = re.sub(r"(创建|新增|添加|安排|记得|提醒我|帮我|请)", "", text)
        text = re.sub(r"(明天|后天|今天|今晚|明晚|下周[一二三四五六日天末]?|本周[一二三四五六日天末]?|周[一二三四五六日天末])", "", text)
        text = TIME_TOKEN_PATTERN.sub("", text)
        text = re.sub(r"\d{1,2}:\d{2}", "", text)
        text = re.sub(r"(之前|截止前?|到期前)", "", text)
        text = re.sub(r"预计[^，。,]*", "", text)
        text = re.sub(r"(可以拆分|可拆分|拆分完成|拆成.*|分成.*)", "", text)
        text = re.sub(r"[，。,!！?？]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text.lstrip("把去在到于前")
        return text[:64] if text else None

    def _extract_task_deadline(self, user_message: str) -> datetime | None:
        if not re.search(r"之前|前|截止|deadline|due", user_message, re.I):
            return None
        start_time, end_time = self._extract_time_range(user_message)
        if end_time:
            return end_time
        if start_time:
            return start_time
        target_date = self._extract_target_date(user_message, datetime.now().date())
        return datetime.combine(target_date, datetime.min.time()).replace(hour=23, minute=59)

    def _extract_period_preference(self, user_message: str) -> str | None:
        if re.search(r"早上|上午|morning", user_message, re.I):
            return "morning"
        if re.search(r"下午|中午|afternoon", user_message, re.I):
            return "afternoon"
        if re.search(r"晚上|今晚|evening|night", user_message, re.I):
            return "evening"
        return None

    def _extract_requested_items(self, user_message: str) -> list[str]:
        match = re.search(r"把(.+?)(?:插进去|安排一下|安排到|放进去)", user_message)
        if not match:
            return []
        return [item.strip() for item in re.split(r"[和、,，]", match.group(1)) if item.strip()]

    def _select_schedule_guidance_dates(self, user_message: str) -> list[date]:
        reference = datetime.now().date()
        if re.search(r"这周|本周|下周|周[一二三四五六日天末]|星期[一二三四五六日天末]", user_message):
            start_date = self._extract_target_date(user_message, reference)
            return [start_date + timedelta(days=offset) for offset in range(0, 3)]
        return [self._extract_target_date(user_message, reference)]

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

        prefers_chinese = self._prefers_chinese(user_message)
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
        pending_schedule = next((action for action in actions if action.type == "suggest_schedule"), None)
        pending_event = next((action for action in actions if action.type == "propose_event"), None)
        updated_context = dict(existing_context)

        if pending_schedule is not None:
            updated_context["pending_action"] = {
                "type": "schedule",
                "payload": {
                    "items": pending_schedule.payload.get("items", []),
                },
                "created_at": datetime.now().isoformat(),
            }
            await self.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)
            return

        if pending_event is not None:
            updated_context["pending_action"] = {
                "type": "event",
                "payload": dict(pending_event.payload),
                "created_at": datetime.now().isoformat(),
            }
            await self.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

    async def _maybe_handle_pending_action_decision(
        self,
        *,
        user_id: str,
        session_id: int,
        session_context: dict[str, Any],
        user_message: str,
        profile,
    ) -> AssistantResponse | None:
        pending_action = session_context.get("pending_action")
        if not pending_action:
            return None

        decision = self._classify_confirmation_intent(user_message)
        if decision == "confirm":
            response = await self._apply_pending_action(
                user_id=user_id,
                session_id=session_id,
                session_context=session_context,
                pending_action=pending_action,
                profile=profile,
                user_message=user_message,
            )
            return response

        if decision == "cancel":
            updated_context = dict(session_context)
            updated_context.pop("pending_action", None)
            await self.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)
            reply = "好的，我已经取消这份待确认内容。" if self._prefers_chinese(user_message) else "Okay, I canceled the pending item."
            return AssistantResponse(session_id=session_id, reply=reply, actions=[])

        return None

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
        if pending_action.get("type") == "event":
            return await self._apply_pending_event(
                user_id=user_id,
                session_id=session_id,
                session_context=session_context,
                pending_action=pending_action,
                profile=profile,
                user_message=user_message,
            )

        pending_payload = pending_action.get("payload") or {}
        items = pending_payload.get("items") or []
        created_events: list[dict[str, Any]] = []
        action_items: list[AssistantAction] = []
        touched_task_ids: set[int] = set()

        for item in items:
            start_raw = item.get("start_time")
            end_raw = item.get("end_time")
            if not start_raw or not end_raw:
                continue
            title = str(item.get("title") or "Planned focus block")
            normalized_title = re.sub(r"^Split\s+", "", title).strip() or title
            if item.get("segment_index") and item.get("segment_total"):
                normalized_title = f"{normalized_title} {item.get('segment_index')}/{item.get('segment_total')}"

            description = item.get("description")
            event_payload = EventCreate(
                title=normalized_title,
                description=description,
                start_time=datetime.fromisoformat(str(start_raw)),
                end_time=datetime.fromisoformat(str(end_raw)),
                location_name=None,
                event_type="focus_block",
                source="local",
                is_fixed=False,
                linked_task_id=item.get("related_task_id"),
            )
            created = await self.event_service.create_event(user_id=user_id, payload=event_payload)
            if item.get("related_task_id"):
                touched_task_ids.add(int(item["related_task_id"]))
            event_context = await self._build_event_specific_context(
                payload={
                    "location_name": created.location_name,
                    "location_coords": getattr(created, "location_coords", None),
                    "start_time": created.start_time.isoformat() if created.start_time else None,
                    "end_time": created.end_time.isoformat() if created.end_time else None,
                    "title": created.title,
                },
                profile=profile,
                user_message=user_message,
            )
            created_event = {
                "event_id": created.id,
                "title": created.title,
                "start_time": created.start_time.isoformat() if created.start_time else None,
                "end_time": created.end_time.isoformat() if created.end_time else None,
                "commute_summary": event_context.get("commute_summary"),
                "weather_summary": event_context.get("weather_summary"),
                "advice_summary": event_context.get("advice_summary"),
            }
            created_events.append(created_event)
            action_items.append(AssistantAction(type="create_event", payload=created_event))

        synced_tasks: list[dict[str, Any]] = []
        for task_id in sorted(touched_task_ids):
            task_read = await self.task_service.sync_task_schedule_state(user_id=user_id, task_id=task_id)
            if task_read is not None:
                synced_tasks.append(
                    {
                        "task_id": task_read.id,
                        "content": task_read.content,
                        "status": task_read.status,
                        "scheduled_minutes": task_read.scheduled_minutes,
                        "scheduled_blocks_count": task_read.scheduled_blocks_count,
                        "remaining_minutes": task_read.remaining_minutes,
                    }
                )

        updated_context = dict(session_context)
        updated_context.pop("pending_action", None)
        await self.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

        apply_action = AssistantAction(
            type="apply_schedule",
            payload={
                "created_events": created_events,
                "count": len(created_events),
                "linked_tasks": synced_tasks,
            },
        )
        action_items.insert(0, apply_action)

        if self._prefers_chinese(user_message):
            if created_events:
                reply = "好的，我已经按刚才确认的计划落成日程。"
            else:
                reply = "我尝试执行待确认计划，但没有找到可创建的日程块。"
        else:
            reply = "Done, I applied the confirmed plan." if created_events else "I tried to apply the pending plan, but no schedule blocks were created."

        return AssistantResponse(session_id=session_id, reply=reply, actions=action_items)

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
        payload = dict((pending_action.get("payload") or {}))
        event_payload = EventCreate.model_validate(
            {
                "title": payload.get("title"),
                "description": payload.get("description"),
                "start_time": payload.get("start_time"),
                "end_time": payload.get("end_time"),
                "location_name": payload.get("location_name"),
                "event_type": payload.get("event_type") or "general",
                "source": "local",
                "is_fixed": False,
            }
        )
        created = await self.event_service.create_event(user_id=user_id, payload=event_payload)
        event_context = await self._build_event_specific_context(
            payload={
                "location_name": created.location_name,
                "location_coords": getattr(created, "location_coords", None),
                "start_time": created.start_time.isoformat() if created.start_time else None,
                "end_time": created.end_time.isoformat() if created.end_time else None,
                "title": created.title,
            },
            profile=profile,
            user_message=user_message,
        )
        created_event = {
            "event_id": created.id,
            "title": created.title,
            "start_time": created.start_time.isoformat() if created.start_time else None,
            "end_time": created.end_time.isoformat() if created.end_time else None,
            "location_name": created.location_name,
            "commute_summary": event_context.get("commute_summary"),
            "weather_summary": event_context.get("weather_summary"),
            "advice_summary": event_context.get("advice_summary"),
        }

        updated_context = dict(session_context)
        updated_context.pop("pending_action", None)
        await self.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

        actions = [
            AssistantAction(type="apply_event_proposal", payload={"created_event": created_event}),
            AssistantAction(type="create_event", payload=created_event),
        ]
        reply = "好的，我已经按这个建议创建正式日程。" if self._prefers_chinese(user_message) else "Done, I created the event from the confirmed suggestion."
        return AssistantResponse(session_id=session_id, reply=reply, actions=actions)

    def _classify_confirmation_intent(self, user_message: str) -> str | None:
        if re.search(r"^(确认|执行|按这个安排|按此执行|就这么定|确定执行|按这个建议创建|按建议创建|创建这个日程|创建吧|apply|confirm|go ahead|do it)", user_message.strip(), re.I):
            return "confirm"
        if re.search(r"^(取消|算了|先不要|不要执行|cancel|skip|not now)", user_message.strip(), re.I):
            return "cancel"
        return None

    async def _build_event_specific_context(
        self,
        *,
        payload: dict[str, Any],
        profile,
        user_message: str,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if not location_name and not location_coords:
            return context

        destination = location_coords or location_name
        destination_coords = location_coords
        if location_name and not destination_coords:
            try:
                geocoded = await self.context_service.geocode(location_name)
                destination_coords = geocoded.location
                context["destination_coords"] = geocoded.location
            except Exception:
                destination_coords = None

        origin_name, origin_value = self._select_commute_origin(profile=profile, user_message=user_message)
        if origin_value and destination:
            try:
                travel = await self.context_service.estimate_travel(
                    origin=origin_value,
                    destination=destination_coords or destination,
                    mode=profile.transport_preference or "driving",
                )
                context["commute_minutes"] = int(round(travel.duration_minutes))
                context["distance_km"] = travel.distance_km
                if self._prefers_chinese(user_message):
                    context["commute_summary"] = (
                        f"从{origin_name}到{location_name or '目的地'}预计约 {int(round(travel.duration_minutes))} 分钟，"
                        f"路程约 {travel.distance_km} 公里。"
                    )
                else:
                    context["commute_summary"] = (
                        f"Estimated commute from {origin_name} to {location_name or 'the destination'} "
                        f"is about {int(round(travel.duration_minutes))} minutes for {travel.distance_km} km."
                    )
            except Exception:
                pass

        weather_location = destination_coords or getattr(profile, "home_location_coords", None)
        if weather_location:
            try:
                weather = await self.context_service.weather_now(location=weather_location)
                weather_text = f"{weather.text}, {weather.temp}°C"
                if self._prefers_chinese(user_message):
                    context["weather_summary"] = f"{location_name or '该地点'}当前天气 {weather_text}。"
                else:
                    context["weather_summary"] = f"Current weather near {location_name or 'the destination'} is {weather_text}."
                context["weather_text"] = weather.text
            except Exception:
                pass

        advice_parts: list[str] = []
        if self._is_outdoor_request(user_message, location_name):
            weather_text = str(context.get("weather_text") or "")
            if re.search(r"雨|雪|雷|风|雾", weather_text):
                advice_parts.append("建议带伞或预留天气变化时间。" if self._prefers_chinese(user_message) else "Consider bringing an umbrella or extra buffer for the weather.")
            else:
                advice_parts.append("如果是户外活动，当前天气看起来相对可行。" if self._prefers_chinese(user_message) else "For an outdoor activity, the current weather looks relatively manageable.")
        elif "带伞" in user_message and context.get("weather_text"):
            weather_text = str(context.get("weather_text"))
            if re.search(r"雨|雪|雷", weather_text):
                advice_parts.append("看起来有降水风险，建议带伞。" if self._prefers_chinese(user_message) else "There appears to be precipitation risk, so bringing an umbrella is a good idea.")
            else:
                advice_parts.append("当前天气里没有明显降水信号。" if self._prefers_chinese(user_message) else "Current conditions do not show an obvious sign of rain.")

        if advice_parts:
            context["advice_summary"] = " ".join(advice_parts)

        return context

    def _select_commute_origin(self, *, profile, user_message: str) -> tuple[str, str | None]:
        if re.search(r"从学校|下课后|从办公室|从实验室|下班后", user_message):
            if getattr(profile, "work_location_coords", None):
                return profile.work_location_name or "工作地点", profile.work_location_coords
            if getattr(profile, "work_location_name", None):
                return profile.work_location_name, profile.work_location_name

        if getattr(profile, "home_location_coords", None):
            return profile.home_location_name or "家", profile.home_location_coords
        if getattr(profile, "home_location_name", None):
            return profile.home_location_name, profile.home_location_name
        if getattr(profile, "work_location_coords", None):
            return profile.work_location_name or "工作地点", profile.work_location_coords
        if getattr(profile, "work_location_name", None):
            return profile.work_location_name, profile.work_location_name
        return "当前位置", None

    def _is_outdoor_request(self, user_message: str, location_name: str | None) -> bool:
        if re.search(r"公园|操场|跑步|散步|骑行|户外|露营|打球|外面", user_message):
            return True
        if location_name and re.search(r"公园|操场|广场|校园|户外|球场", location_name):
            return True
        return False

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

    def _compute_free_slots(self, *, day_events, target_date: date) -> list[tuple[datetime, datetime]]:
        cursor = datetime.combine(target_date, datetime.min.time()).replace(hour=8)
        day_end = datetime.combine(target_date, datetime.min.time()).replace(hour=22)
        free_slots: list[tuple[datetime, datetime]] = []
        for event in day_events:
            if event.start_time > cursor:
                free_slots.append((cursor, event.start_time))
            cursor = max(cursor, event.end_time)
        if cursor < day_end:
            free_slots.append((cursor, day_end))
        return [slot for slot in free_slots if (slot[1] - slot[0]) >= timedelta(minutes=30)]

    def _prefers_chinese(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    async def _build_external_context(self, *, profile) -> dict[str, Any]:
        async def _fetch_weather():
            if profile.home_location_coords:
                try:
                    weather = await self.context_service.weather_now(location=profile.home_location_coords)
                    return {"temp": weather.temp, "text": weather.text, "humidity": weather.humidity}
                except Exception:
                    pass
            return None

        async def _fetch_commute():
            origin = profile.home_location_coords or profile.home_location_name
            destination = profile.work_location_coords or profile.work_location_name
            if origin and destination:
                try:
                    travel = await self.context_service.estimate_travel(
                        origin=origin,
                        destination=destination,
                        mode=profile.transport_preference or "driving",
                    )
                    return {
                        "duration_minutes": travel.duration_minutes,
                        "distance_km": travel.distance_km,
                    }
                except Exception:
                    pass
            return None

        weather_result, commute_result = await asyncio.gather(_fetch_weather(), _fetch_commute())

        context: dict[str, Any] = {}
        if weather_result is not None:
            context["weather_now"] = weather_result
        if commute_result is not None:
            context["default_commute"] = commute_result
        return context
