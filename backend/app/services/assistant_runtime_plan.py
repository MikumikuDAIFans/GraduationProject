"""Planning and action execution runtime helpers for the assistant service."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.api.schemas import AssistantAction, EventCreate, EventUpdate, TaskCreate
from app.api.schemas import AssistantResponse


class AssistantPlanRuntime:
    """Owns planning, action execution, reply composition, and progress follow-up."""

    def __init__(self, owner) -> None:
        self.owner = owner

    async def build_plan(
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
        intent = self.owner.text_runtime._classify_intent(user_message)
        fallback_plan = await self.build_rule_based_plan(
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
            plan = await self.owner.gemini.generate_plan(
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

    async def execute_actions(
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
                    payload = self.hydrate_event_payload(payload=payload, user_message=user_message)
                    event_payload = EventCreate.model_validate(payload)
                    if event_payload.start_time is None or event_payload.end_time is None:
                        continue
                    conflicts = await self.owner.event_service.detect_conflicts(
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
                        suggestions = await self.owner.event_service.find_alternative_slots(
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
                    created = await self.owner.event_service.create_event(user_id=user_id, payload=event_payload)
                    event_context = await self.owner._build_event_specific_context(
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
                    payload = self.hydrate_task_payload(payload=payload, user_message=user_message)
                    task_payload = TaskCreate.model_validate(payload)
                    created = await self.owner.task_repository.create_task({"user_id": user_id, **task_payload.model_dump()})
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
                    schedule_action = await self.build_task_schedule_action(user_id=user_id, related_task_id=created.id)
                    if schedule_action is not None:
                        executed.append(schedule_action)
                elif action_type == "update_event":
                    event_id = payload.get("event_id")
                    if event_id is None:
                        continue
                    update_fields = {k: v for k, v in payload.items() if k != "event_id"}
                    updated = await self.owner.event_service.update_event(
                        user_id=user_id,
                        event_id=event_id,
                        payload=EventUpdate.model_validate(update_fields),
                    )
                    executed.append(
                        AssistantAction(
                            type="update_event",
                            payload={
                                "event_id": updated.id,
                                "title": updated.title,
                                "start_time": updated.start_time.isoformat() if updated.start_time else None,
                                "end_time": updated.end_time.isoformat() if updated.end_time else None,
                            },
                        )
                    )
                elif action_type == "delete_event":
                    event_id = payload.get("event_id")
                    if event_id is None:
                        continue
                    await self.owner.event_service.delete_event(user_id=user_id, event_id=event_id)
                    executed.append(AssistantAction(type="delete_event", payload={"event_id": event_id, "status": "deleted"}))
                elif action_type == "suggest_schedule":
                    executed.append(AssistantAction(type="suggest_schedule", payload=payload))
                elif action_type == "propose_event":
                    executed.append(AssistantAction(type="propose_event", payload=payload))
            except ValidationError:
                continue

        return executed

    def compose_reply(
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
        prefers_chinese = self.owner.text_runtime._prefers_chinese(user_message)
        if actions:
            return self.compose_action_reply(
                prefers_chinese=prefers_chinese,
                base_reply=base_reply,
                actions=actions,
                requested_actions=requested_actions,
                external_context=external_context,
            )
        if requested_actions:
            if prefers_chinese:
                return "我理解你想让我创建内容，但目前抽取到的时间、地点或任务信息还不够明确。你可以再补一句更具体的话。"
            return "I understood that you wanted me to create something, but I could not safely execute it with the extracted details. Please provide a clearer time or task detail and I will try again."
        if base_reply and base_reply.strip():
            return base_reply.strip()
        if prefers_chinese:
            return f"Gemini 当前暂时不可用，但你的消息已经保存。我看到你当前有 {event_count} 个日程、{task_count} 个任务。你可以继续从这句话接着说：{fallback_message}"
        return f"Gemini is temporarily unavailable, but your message has been saved. I can see {event_count} events and {task_count} tasks in your current context. Please continue from: {fallback_message}"

    def compose_action_reply(
        self,
        *,
        prefers_chinese: bool,
        base_reply: str | None,
        actions: list[AssistantAction],
        requested_actions: list[dict[str, Any]],
        external_context: dict[str, Any],
    ) -> str:
        conflict_actions = [action for action in actions if action.type == "conflict_warning"]
        created_actions = [action for action in actions if action.type not in {"conflict_warning", "suggest_reschedule"}]
        if conflict_actions and not created_actions:
            conflict = conflict_actions[0]
            titles = ", ".join(item["title"] for item in conflict.payload.get("conflicts", []))
            suggestions = conflict.payload.get("suggestions", [])
            if prefers_chinese:
                suggestion_text = ""
                if suggestions:
                    suggestion_text = "；可改约：" + "；".join(f"{item['start_time']} 到 {item['end_time']}" for item in suggestions[:3])
                return f"我发现这个时间段和 {titles} 冲突了，所以先没有创建新日程。{suggestion_text}"
            suggestion_text = ""
            if suggestions:
                suggestion_text = " Suggested slots: " + ", ".join(f"{item['start_time']} -> {item['end_time']}" for item in suggestions[:3])
            return f"I found a scheduling conflict, so I did not create the new event. The requested slot overlaps with: {titles}.{suggestion_text}"

        summaries: list[str] = []
        for action in actions:
            if action.type == "create_event":
                summaries.append(self.format_event_summary(action=action, prefers_chinese=prefers_chinese, external_context=external_context))
            elif action.type == "create_task":
                summaries.append(self.format_task_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "suggest_schedule":
                summaries.append(self.format_schedule_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "apply_schedule":
                summaries.append(self.format_apply_schedule_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "propose_event":
                summaries.append(self.format_proposed_event_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "apply_event_proposal":
                summaries.append(self.format_apply_event_summary(action=action, prefers_chinese=prefers_chinese))
            elif action.type == "conflict_warning":
                summaries.append(f"检测到时间冲突：{action.payload.get('title')}" if prefers_chinese else f"Conflict detected for: {action.payload.get('title')}")

        prefix = (base_reply.strip() if base_reply else "我已经按你的意思处理好了。") if prefers_chinese else (base_reply.strip() if base_reply else "Done.")
        return prefix + ("\n\n" + "\n".join(f"- {item}" for item in summaries) if summaries else "")

    def format_event_summary(self, *, action: AssistantAction, prefers_chinese: bool, external_context: dict[str, Any]) -> str:
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

    def format_task_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        if prefers_chinese:
            summary = f"已创建任务：{action.payload.get('content')}"
            if action.payload.get("deadline"):
                summary += f"，截止时间 {action.payload.get('deadline')}"
            return summary
        return f"Created task: {action.payload.get('content')}"

    def format_schedule_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        items = action.payload.get("items") or []
        if not items:
            return "已生成调度建议。" if prefers_chinese else "Generated schedule suggestions."
        preview = items[:3]
        if prefers_chinese:
            lines = []
            for item in preview:
                label = item.get("title") or item.get("type") or "建议"
                slot = f"{item.get('start_time')} 到 {item.get('end_time')}"
                segment = f"（第 {item.get('segment_index')}/{item.get('segment_total')} 段）" if item.get("segment_index") and item.get("segment_total") else ""
                lines.append(f"{label}{segment}：{slot}")
            return "为你整理了这些可执行空档：" + "；".join(lines)
        lines = [f"{item.get('title') or item.get('type') or 'Suggestion'}: {item.get('start_time')} -> {item.get('end_time')}" for item in preview]
        return "Schedule suggestions: " + "; ".join(lines)

    def format_apply_schedule_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        items = action.payload.get("created_events") or []
        if prefers_chinese:
            if not items:
                return "已确认执行计划。"
            return "已按确认计划创建这些日程：" + "；".join(f"{item.get('title')}：{item.get('start_time')} 到 {item.get('end_time')}" for item in items[:5])
        if not items:
            return "Applied the confirmed schedule."
        return "Created schedule blocks: " + "; ".join(f"{item.get('title')}: {item.get('start_time')} -> {item.get('end_time')}" for item in items[:5])

    def chunk_text(self, text: str, chunk_size: int = 24) -> list[str]:
        if not text:
            return [""]
        return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]

    def format_proposed_event_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        if prefers_chinese:
            summary = f"待确认事件：{action.payload.get('title')}"
            if action.payload.get("start_time") and action.payload.get("end_time"):
                summary += f"（{action.payload.get('start_time')} 到 {action.payload.get('end_time')}）"
            if action.payload.get("location_name"):
                summary += f"，地点：{action.payload.get('location_name')}"
            return summary
        return f"Pending event proposal: {action.payload.get('title')}"

    def format_apply_event_summary(self, *, action: AssistantAction, prefers_chinese: bool) -> str:
        event = action.payload.get("created_event") or {}
        if prefers_chinese:
            return f"已按确认创建事件：{event.get('title')}（{event.get('start_time')} 到 {event.get('end_time')}）"
        return f"Created confirmed event: {event.get('title')}"

    def build_task_preflight_reply(self, *, payload: dict[str, Any], user_message: str) -> str:
        if self.owner.text_runtime._prefers_chinese(user_message):
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

    def build_event_preflight_reply(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        external_context: dict[str, Any],
        event_context: dict[str, Any] | None = None,
    ) -> str:
        event_context = event_context or {}
        prefers_chinese = self.owner.text_runtime._prefers_chinese(user_message)
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

    def build_event_advice_reply(
        self,
        *,
        payload: dict[str, Any],
        user_message: str,
        event_context: dict[str, Any],
        profile,
    ) -> str:
        prefers_chinese = self.owner.text_runtime._prefers_chinese(user_message)
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

    async def build_task_schedule_action(self, *, user_id: str, related_task_id: int) -> AssistantAction | None:
        dates = [datetime.now().date() + timedelta(days=offset) for offset in range(0, 4)]
        items = await self.owner.suggestion_service.build_suggestions_for_dates(
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

    def hydrate_event_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        extracted = self.owner.text_runtime._build_rule_based_event_payload(user_message)
        enriched = dict(payload)
        for key in ("title", "description", "start_time", "end_time", "location_name", "event_type"):
            if enriched.get(key) in (None, "", "event", "new event", "New event") and extracted.get(key):
                enriched[key] = extracted[key]
        enriched["title"] = self.owner.text_runtime._normalize_event_title(
            current_title=enriched.get("title"),
            user_message=user_message,
        )
        return enriched

    def hydrate_task_payload(self, *, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        extracted = self.owner.text_runtime._build_rule_based_task_payload(user_message)
        enriched = dict(payload)
        for key in ("content", "description", "deadline", "estimated_duration_minutes", "priority", "can_split", "preferred_period"):
            if enriched.get(key) in (None, "", False) and extracted.get(key) not in (None, "", False):
                enriched[key] = extracted[key]
        return enriched

    async def build_rule_based_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        events,
        tasks,
        profile,
        external_context: dict[str, Any],
    ) -> dict[str, Any]:
        intent = self.owner.text_runtime._classify_intent(user_message)
        if intent == "schedule_guidance":
            target_dates = self.owner.text_runtime._select_schedule_guidance_dates(user_message)
            schedule_items = await self.owner.suggestion_service.build_suggestions_for_dates(
                user_id=user_id,
                dates=target_dates,
                limit=6,
            )
            return {
                "reply": self.owner.text_runtime._build_schedule_guidance_reply(
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
            followup_plan = await self.build_progress_followup_plan(
                user_id=user_id,
                user_message=user_message,
                tasks=tasks,
            )
            if followup_plan is not None:
                return followup_plan

        if intent == "event_context_advice":
            event_payload = self.owner.text_runtime._build_rule_based_event_payload(user_message)
            event_context = await self.owner._build_event_specific_context(
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
                "reply": self.build_event_advice_reply(
                    payload=event_payload,
                    user_message=user_message,
                    event_context=event_context,
                    profile=profile,
                ),
                "actions": actions,
            }

        if intent == "create_task":
            payload = self.owner.text_runtime._build_rule_based_task_payload(user_message)
            if payload.get("content"):
                return {
                    "reply": self.build_task_preflight_reply(payload=payload, user_message=user_message),
                    "actions": [{"type": "create_task", "payload": payload}],
                }
            return {
                "reply": self.owner.formatter.build_clarification_reply(
                    intent="create_task",
                    missing_fields=["content"],
                    prefers_chinese=self.owner.text_runtime._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        event_payload = self.owner.text_runtime._build_rule_based_event_payload(user_message)
        if event_payload.get("title") and event_payload.get("start_time") and event_payload.get("end_time"):
            event_context = await self.owner._build_event_specific_context(
                payload=event_payload,
                profile=profile,
                user_message=user_message,
            )
            return {
                "reply": self.build_event_preflight_reply(
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
                "reply": self.owner.formatter.build_clarification_reply(
                    intent="create_event",
                    missing_fields=missing_fields or ["start_time", "end_time"],
                    prefers_chinese=self.owner.text_runtime._prefers_chinese(user_message),
                ),
                "actions": [],
            }

        return {"reply": "", "actions": []}

    async def build_progress_followup_plan(
        self,
        *,
        user_id: str,
        user_message: str,
        tasks,
    ) -> dict[str, Any] | None:
        followup_reminders = await self.owner.reminder_repository.list_recent_task_followups(user_id=user_id, limit=6)
        active_tasks = [task for task in tasks if (task.status or "pending") not in {"done"}]
        active_tasks.sort(key=lambda task: (-(task.completed_minutes or 0), -(task.scheduled_minutes or 0), task.id))

        target_task_ids = [task.id for task in active_tasks[:3]]
        schedule_items = await self.owner.suggestion_service.build_suggestions_for_dates(
            user_id=user_id,
            dates=[datetime.now().date() + timedelta(days=offset) for offset in range(0, 3)],
            limit=6,
            related_task_ids=target_task_ids or None,
        )

        if not followup_reminders and not schedule_items and not active_tasks:
            return None

        prefers_chinese = self.owner.text_runtime._prefers_chinese(user_message)
        reply = self.build_progress_followup_reply(
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

    def build_progress_followup_reply(
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

    async def persist_pending_action(
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
                "payload": {"items": pending_schedule.payload.get("items", [])},
                "created_at": datetime.now().isoformat(),
            }
            await self.owner.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)
            return

        if pending_event is not None:
            updated_context["pending_action"] = {
                "type": "event",
                "payload": dict(pending_event.payload),
                "created_at": datetime.now().isoformat(),
            }
            await self.owner.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

    async def maybe_handle_pending_action_decision(
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

        decision = self.classify_confirmation_intent(user_message)
        if decision == "confirm":
            return await self.apply_pending_action(
                user_id=user_id,
                session_id=session_id,
                session_context=session_context,
                pending_action=pending_action,
                profile=profile,
                user_message=user_message,
            )

        if decision == "cancel":
            updated_context = dict(session_context)
            updated_context.pop("pending_action", None)
            await self.owner.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)
            reply = "好的，我已经取消这份待确认内容。" if self.owner.text_runtime._prefers_chinese(user_message) else "Okay, I canceled the pending item."
            return AssistantResponse(session_id=session_id, reply=reply, actions=[])

        return None

    async def apply_pending_action(
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
            return await self.apply_pending_event(
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
            created = await self.owner.event_service.create_event(user_id=user_id, payload=event_payload)
            if item.get("related_task_id"):
                touched_task_ids.add(int(item["related_task_id"]))
            event_context = await self.owner._build_event_specific_context(
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
            task_read = await self.owner.task_service.sync_task_schedule_state(user_id=user_id, task_id=task_id)
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
        await self.owner.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

        action_items.insert(
            0,
            AssistantAction(
                type="apply_schedule",
                payload={
                    "created_events": created_events,
                    "count": len(created_events),
                    "linked_tasks": synced_tasks,
                },
            ),
        )

        if self.owner.text_runtime._prefers_chinese(user_message):
            reply = "好的，我已经按刚才确认的计划落成日程。" if created_events else "我尝试执行待确认计划，但没有找到可创建的日程块。"
        else:
            reply = "Done, I applied the confirmed plan." if created_events else "I tried to apply the pending plan, but no schedule blocks were created."
        return AssistantResponse(session_id=session_id, reply=reply, actions=action_items)

    async def apply_pending_event(
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
        created = await self.owner.event_service.create_event(user_id=user_id, payload=event_payload)
        event_context = await self.owner._build_event_specific_context(
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
        await self.owner.repository.update_session_context(session_id, user_id=user_id, context_json=updated_context)

        actions = [
            AssistantAction(type="apply_event_proposal", payload={"created_event": created_event}),
            AssistantAction(type="create_event", payload=created_event),
        ]
        reply = "好的，我已经按这个建议创建正式日程。" if self.owner.text_runtime._prefers_chinese(user_message) else "Done, I created the event from the confirmed suggestion."
        return AssistantResponse(session_id=session_id, reply=reply, actions=actions)

    def classify_confirmation_intent(self, user_message: str) -> str | None:
        if re.search(r"^(确认|执行|按这个安排|按此执行|就这么定|确定执行|按这个建议创建|按建议创建|创建这个日程|创建吧|apply|confirm|go ahead|do it)", user_message.strip(), re.I):
            return "confirm"
        if re.search(r"^(取消|算了|先不要|不要执行|cancel|skip|not now)", user_message.strip(), re.I):
            return "cancel"
        return None
