"""Session, inbox, and summary runtime helpers for the assistant service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.api.schemas import (
    AssistantCurrentSessionRead,
    AssistantInboxItem,
    AssistantInboxRead,
    AssistantMessageRead,
    AssistantSessionRead,
    AssistantSummaryCard,
    AssistantSummaryRead,
)


class AssistantSessionRuntime:
    """Owns session, inbox, and summary orchestration."""

    ACTIONABLE_SUGGESTION_TYPES = {
        "task_slot",
        "task_split_slot",
        "task_replan_slot",
        "task_resume_slot",
    }

    def __init__(self, owner) -> None:
        self.owner = owner

    async def maybe_autorename_session(
        self,
        *,
        user_id: str,
        session_id: int,
        session_title: str,
        user_message: str,
    ) -> None:
        if session_title != "New chat" and not session_title.startswith("新对话 "):
            return
        title = user_message.strip()
        title = __import__("re").sub(r"\s+", " ", title).strip()[:32]
        if not title:
            return
        await self.owner.repository.rename_session(session_id, user_id=user_id, title=title)

    async def get_session(self, user_id: str, session_id: int) -> AssistantSessionRead:
        session = await self.owner.repository.get_session(session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assistant session not found")

        messages = await self.owner.repository.list_messages(session_id)
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

    async def get_current_session(self, user_id: str, *, include_inbox: bool = True) -> AssistantCurrentSessionRead:
        session = await self.owner.repository.get_latest_session(user_id=user_id, session_type="chat")
        if session is None:
            session = await self.owner.repository.create_session(
                user_id=user_id,
                session_type="chat",
                context_json={"status": "assistant-active"},
            )

        inbox = AssistantInboxRead()
        if include_inbox:
            inbox = await self.owner.get_inbox(user_id=user_id)
            # Only sync inbox to session if there are new unread items not yet surfaced
            context_json = dict(session.context_json or {})
            surfaced_ids = set(context_json.get("surfaced_inbox_ids", []))
            has_new_items = any(item.id not in surfaced_ids and not item.archived for item in inbox.items)
            if has_new_items:
                session = await self.owner._sync_inbox_to_session(user_id=user_id, session=session, inbox=inbox)
        session_read = await self.owner.get_session(user_id=user_id, session_id=session.id)
        return AssistantCurrentSessionRead(session=session_read, inbox=inbox)

    async def get_summary(self, user_id: str) -> AssistantSummaryRead:
        session, inbox_state = await self._prepare_inbox_state(user_id=user_id)
        tasks = await self.owner.task_service.list_tasks(user_id=user_id)
        reminders = await self.owner.reminder_repository.list_reminders(user_id=user_id, limit=20)
        recent_followups = await self.owner.reminder_repository.list_recent_task_followups(user_id=user_id, limit=6)
        suggestion_items = await self.owner.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 4)],
            limit=8,
            core_only=True,
        )
        inbox = self._build_inbox_read(
            tasks=tasks,
            reminders=recent_followups,
            suggestion_items=suggestion_items,
            inbox_state=inbox_state,
        )
        cards = self.build_summary_cards(
            inbox=inbox,
            tasks=tasks,
            reminders=reminders,
            suggestions=suggestion_items,
        )
        return AssistantSummaryRead(
            generated_at=datetime.now(),
            unread_followups=inbox.unread_total,
            cards=cards,
        )

    async def get_inbox(self, user_id: str) -> AssistantInboxRead:
        _session, inbox_state = await self._prepare_inbox_state(user_id=user_id)
        tasks = await self.owner.task_service.list_tasks(user_id=user_id)
        reminders = await self.owner.reminder_repository.list_recent_task_followups(user_id=user_id, limit=6)
        suggestion_items = await self.owner.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 3)],
            limit=6,
            core_only=True,
        )
        return self._build_inbox_read(
            tasks=tasks,
            reminders=reminders,
            suggestion_items=suggestion_items,
            inbox_state=inbox_state,
        )

    async def _prepare_inbox_state(self, *, user_id: str):
        session = await self.owner.repository.get_latest_session(user_id=user_id, session_type="chat")
        session_context = dict(session.context_json or {}) if session is not None else {}
        inbox_state = dict(session_context.get("inbox_item_state", {}))
        cleaned_state = self.cleanup_inbox_state(inbox_state)
        if session is not None and cleaned_state != inbox_state:
            session_context["inbox_item_state"] = cleaned_state
            session = await self.owner.repository.update_session_context(
                session.id,
                user_id=user_id,
                context_json=session_context,
            ) or session
            inbox_state = cleaned_state
        return session, inbox_state

    def _build_inbox_read(
        self,
        *,
        tasks,
        reminders,
        suggestion_items,
        inbox_state: dict[str, Any],
    ) -> AssistantInboxRead:
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
            if not self.is_actionable_suggestion(item):
                continue
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

        grouped_items = self.group_inbox_items(inbox_items)
        visible_items = self.apply_inbox_state(grouped_items, inbox_state)
        visible_items.sort(key=lambda item: (-item.priority, item.id))
        visible_slice = visible_items[:8]
        unread_total = sum(1 for item in visible_slice if not item.read)
        return AssistantInboxRead(items=visible_slice, total=min(len(visible_items), 8), unread_total=unread_total)

    def group_inbox_items(self, items: list[AssistantInboxItem]) -> list[AssistantInboxItem]:
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
                    meta={"entries": [item.model_dump(mode="json") for item in task_items]},
                )
            )

        result.extend(standalone)
        return result

    def apply_inbox_state(self, items: list[AssistantInboxItem], state: dict[str, Any]) -> list[AssistantInboxItem]:
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
                        "updated_at": self.parse_state_datetime(item_state.get("updated_at")),
                    }
                )
            )
        return visible

    def parse_state_datetime(self, raw_value: Any) -> datetime | None:
        if not raw_value or not isinstance(raw_value, str):
            return None
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    def render_inbox_item_as_message(self, item: AssistantInboxItem) -> str:
        if item.kind == "task_followup_group":
            entries = item.meta.get("entries", []) if item.meta else []
            bullet_lines = [f"- {entry.get('title')}：{entry.get('description')}" for entry in entries[:3]]
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

    def is_actionable_suggestion(self, suggestion) -> bool:
        suggestion_type = getattr(suggestion, "type", None)
        if suggestion_type is None and hasattr(suggestion, "model_dump"):
            suggestion_type = suggestion.model_dump(mode="json").get("type")
        return suggestion_type in self.ACTIONABLE_SUGGESTION_TYPES

    async def sync_inbox_to_session(self, *, user_id: str, session, inbox: AssistantInboxRead):
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
            content = self.render_inbox_item_as_message(item)
            created_message = await self.owner.repository.create_message(
                session_id=session.id,
                role="assistant",
                content=content,
                tool_calls_json=[{"type": "inbox_followup", "payload": item.model_dump(mode="json")}],
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
        updated = await self.owner.repository.update_session_context(
            session.id,
            user_id=user_id,
            context_json=context_json,
        )
        return updated or session

    async def mark_inbox_item(self, *, user_id: str, item_id: str, action: str) -> AssistantInboxRead:
        session = await self.owner.repository.get_latest_session(user_id=user_id, session_type="chat")
        if session is None:
            session = await self.owner.repository.create_session(
                user_id=user_id,
                session_type="chat",
                context_json={"status": "assistant-active"},
            )

        inbox = await self.owner.get_inbox(user_id=user_id)
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
        context_json["inbox_item_state"] = self.compact_inbox_state(inbox_state)
        await self.owner.repository.update_session_context(
            session.id,
            user_id=user_id,
            context_json=context_json,
        )
        return await self.owner.get_inbox(user_id=user_id)

    def compact_inbox_state(self, state: dict[str, Any], max_items: int = 100) -> dict[str, Any]:
        if len(state) <= max_items:
            return state
        return {key: state[key] for key in list(state.keys())[-max_items:]}

    def cleanup_inbox_state(self, state: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        cleaned: dict[str, Any] = {}
        for key, value in state.items():
            if not isinstance(value, dict):
                continue
            if not value.get("archived"):
                cleaned[key] = value
                continue
            updated_at = self.parse_state_datetime(value.get("updated_at"))
            if updated_at is not None and updated_at >= now - timedelta(days=self.owner.INBOX_ARCHIVE_RETENTION_DAYS):
                cleaned[key] = value
        return self.compact_inbox_state(cleaned)

    def build_summary_cards(self, *, inbox: AssistantInboxRead, tasks, reminders, suggestions) -> list[AssistantSummaryCard]:
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
        active_tasks.sort(key=lambda task: (-(task.completed_minutes or 0), -(task.scheduled_minutes or 0), task.id))
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
