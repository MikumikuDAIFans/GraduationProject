"""Workflow node implementations for the V7 assistant flow."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


class WorkflowNodes:
    """Workflow nodes used by both LangGraph and sequential fallback execution."""

    def __init__(
        self,
        intent_parser=None,
        event_service=None,
        task_service=None,
        habit_retriever=None,
        conflict_detector=None,
        weather_service=None,
        maps_service=None,
        dialog_manager=None,
        response_formatter=None,
    ) -> None:
        self.settings = get_settings()
        self.intent_parser = intent_parser
        self.event_service = event_service
        self.task_service = task_service
        self.habit_retriever = habit_retriever
        self.conflict_detector = conflict_detector
        self.weather_service = weather_service
        self.maps_service = maps_service
        self.dialog_manager = dialog_manager
        self.response_formatter = response_formatter

    @staticmethod
    def _assistant_from_state(state: WorkflowState):
        return state.get("assistant_service")

    @staticmethod
    def _get_runtime_service(state: WorkflowState, attr_name: str):
        value = state.get(attr_name)
        if value is not None:
            return value
        return None

    @staticmethod
    def _needs_weather(intent: str, user_message: str = "") -> bool:
        if intent in {"event_context_advice", "schedule_guidance"}:
            return True
        return bool(re.search(r"天气|气温|温度|冷|热|下雨|下雪|weather", user_message, re.I))

    @staticmethod
    def _needs_traffic(intent: str, user_message: str = "") -> bool:
        if intent in {"event_context_advice", "schedule_guidance", "create_event"}:
            return True
        return bool(re.search(r"通勤|出发|多久到|多远|路程|路线|怎么去|traffic|commute", user_message, re.I))

    @staticmethod
    def _should_use_react(state: WorkflowState) -> bool:
        settings = get_settings()
        if not settings.enable_react_subgraph:
            return False

        intent = state.get("intent", "")
        user_message = state.get("user_message", "")

        if intent == "schedule_guidance" and re.search(r"详细|仔细|全面|compare|plan|安排一下周末", user_message, re.I):
            return True
        if intent == "event_context_advice" and state.get("extracted_slots", {}).get("location"):
            return True
        return False

    @staticmethod
    async def parse_intent(state: WorkflowState) -> WorkflowState:
        assistant = WorkflowNodes._assistant_from_state(state)
        user_message = state.get("user_message", "")
        user_id = state.get("user_id", "")

        try:
            if assistant is not None:
                intent = assistant.text_runtime._classify_intent(user_message)
                extracted_slots: dict[str, Any] = {}

                if intent in {"create_event", "event_context_advice"}:
                    event_payload = assistant.text_runtime._build_rule_based_event_payload(user_message)
                    event_payload = assistant._apply_place_memory_to_event_payload(
                        payload=event_payload,
                        user_message=user_message,
                        external_context=state.get("external_context", {}),
                    )
                    extracted_slots["new_event"] = event_payload
                    extracted_slots["location"] = event_payload.get("location_coords") or event_payload.get("location_name")
                    extracted_slots["activity"] = assistant.text_runtime._extract_event_topic(user_message)
                elif intent == "create_task":
                    extracted_slots["task"] = assistant.text_runtime._build_rule_based_task_payload(user_message)
                    extracted_slots["activity"] = assistant.text_runtime._extract_task_content(user_message)
                elif intent == "schedule_guidance":
                    location_name = assistant.text_runtime._extract_location(user_message)
                    resolved = assistant.memory_service.resolve_place_alias(
                        user_message=user_message,
                        location_name=location_name,
                        memory_context=(state.get("external_context", {}) or {}).get("assistant_memory"),
                    )
                    extracted_slots["location"] = (
                        resolved.get("location_coords")
                        or resolved.get("location_name")
                        if resolved
                        else location_name
                    )
                    extracted_slots["activity"] = (assistant.text_runtime._extract_requested_items(user_message) or [None])[0]
                    extracted_slots["time_range"] = "planning_window"

                # 如果规则引擎识别出了意图，合并结果
                if intent != "unknown":
                    state["intent"] = intent
                    # 合并槽位，优先保留规则引擎提取的
                    if "extracted_slots" not in state: state["extracted_slots"] = {}
                    for k, v in extracted_slots.items():
                        if v: state["extracted_slots"][k] = v
                    state["confidence"] = 0.85
                    return state

            # 规则引擎没识别出来时，再启用增强解析器和 LLM 兜底。
            from app.services.intent_parser import EnhancedIntentParser

            parser = EnhancedIntentParser(
                habit_retriever=getattr(assistant, "habit_retriever", None) if assistant else None,
                llm_client=getattr(assistant, "gemini", None) if assistant else None,
            )
            result = await parser.parse_with_context(user_message, user_id)
            state["intent"] = result.intent
            state["extracted_slots"] = {
                k: v
                for k, v in {
                    "activity": result.activity,
                    "location": result.location,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "time_context": result.time_context,
                }.items()
                if v is not None
            }
            if result.intent in {"create_event", "event_context_advice"} and assistant is not None:
                event_payload = assistant.text_runtime._build_rule_based_event_payload(user_message)
                event_payload = assistant._apply_place_memory_to_event_payload(
                    payload=event_payload,
                    user_message=user_message,
                    external_context=state.get("external_context", {}),
                )
                state["extracted_slots"]["new_event"] = event_payload
                state["extracted_slots"]["location"] = event_payload.get("location_coords") or event_payload.get("location_name")
            state["confidence"] = result.confidence

        except Exception as exc:
            logger.error("Intent parsing failed: %s", exc)
            state["intent"] = "unknown"
            state["extracted_slots"] = {}
            state["confidence"] = 0.0

        return state

    @staticmethod
    async def collect_context(state: WorkflowState) -> WorkflowState:
        assistant = WorkflowNodes._assistant_from_state(state)
        user_id = state.get("user_id", "")
        intent = state.get("intent", "unknown")
        slots = state.get("extracted_slots", {})
        user_message = state.get("user_message", "")
        profile = state.get("profile")
        existing_external_context = dict(state.get("external_context") or {})

        async def _fetch_events():
            if assistant is not None:
                return await assistant.event_service.list_events(user_id=user_id)
            service = WorkflowNodes._get_runtime_service(state, "event_service")
            if service is not None and intent in {"create_event", "schedule_guidance", "query_events", "event_context_advice", "progress_followup"}:
                return await service.get_relevant_events(user_id, slots.get("time_range", "today"))
            return []

        async def _fetch_tasks():
            if assistant is not None:
                return await assistant.task_service.list_tasks(user_id=user_id)
            service = WorkflowNodes._get_runtime_service(state, "task_service")
            if service is not None and intent in {"create_task", "schedule_guidance", "query_tasks", "progress_followup"}:
                return await service.get_active_tasks(user_id)
            return []

        async def _fetch_habits():
            activity = slots.get("activity")
            if not activity:
                return []
            if assistant is not None and getattr(assistant, "habit_retriever", None) is not None:
                return await assistant.habit_retriever.get_relevant_habits(activity=activity, user_id=user_id)
            retriever = WorkflowNodes._get_runtime_service(state, "habit_retriever")
            if retriever is not None:
                return await retriever.get_relevant_habits(activity=activity, user_id=user_id)
            return []

        async def _fetch_weather():
            if not WorkflowNodes._needs_weather(intent, user_message):
                return None
            location = slots.get("location") or getattr(profile, "home_location_coords", None)
            if not location:
                return None
            try:
                if assistant is not None:
                    weather = await assistant.context_service.weather_now(location=location)
                else:
                    service = WorkflowNodes._get_runtime_service(state, "weather_service")
                    if service is None:
                        return None
                    weather = await service.get_weather(location)
                if hasattr(weather, "model_dump"):
                    return weather.model_dump(mode="json")
                return dict(weather) if isinstance(weather, dict) else weather
            except Exception as exc:
                logger.warning("Weather fetch failed: %s", exc)
                return None

        async def _fetch_traffic():
            if not WorkflowNodes._needs_traffic(intent, user_message):
                return None
            location = slots.get("location")
            if not location:
                return None
            try:
                origin = (
                    getattr(profile, "home_location_coords", None)
                    or getattr(profile, "home_location_name", None)
                    or getattr(profile, "work_location_coords", None)
                    or getattr(profile, "work_location_name", None)
                )
                if assistant is not None:
                    if not origin:
                        return None
                    travel = await assistant.context_service.estimate_travel(
                        origin=origin,
                        destination=location,
                        mode=getattr(profile, "transport_preference", None) or "driving",
                    )
                else:
                    service = WorkflowNodes._get_runtime_service(state, "maps_service")
                    if service is None:
                        return None
                    travel = await service.estimate_travel_time(user_id, location)
                if hasattr(travel, "model_dump"):
                    return travel.model_dump(mode="json")
                return dict(travel) if isinstance(travel, dict) else travel
            except Exception as exc:
                logger.warning("Traffic fetch failed: %s", exc)
                return None

        events_result, tasks_result, habits_result, weather_result, traffic_result = await asyncio.gather(
            _fetch_events(),
            _fetch_tasks(),
            _fetch_habits(),
            _fetch_weather(),
            _fetch_traffic(),
        )

        state["existing_events"] = events_result or []
        state["existing_tasks"] = tasks_result or []
        state["habits"] = habits_result or []
        state["weather"] = weather_result
        state["traffic"] = traffic_result
        state["external_context"] = {
            **existing_external_context,
            "weather_now": weather_result,
            "default_commute": traffic_result,
        }
        return state

    @staticmethod
    async def schedule_decision(state: WorkflowState) -> WorkflowState:
        assistant = WorkflowNodes._assistant_from_state(state)
        settings = get_settings()
        intent = state.get("intent", "")
        user_message = state.get("user_message", "")
        user_id = state.get("user_id", "")
        confidence = state.get("confidence", 0.0)
        slots = state.get("extracted_slots", {})
        events = state.get("existing_events", [])
        tasks = state.get("existing_tasks", [])
        profile = state.get("profile")
        external_context = state.get("external_context", {})

        state.setdefault("actions", [])
        state.setdefault("conflicts", [])
        state.setdefault("suggestions", [])
        state["use_react"] = WorkflowNodes._should_use_react(state)

        if confidence < settings.route_confidence_threshold and intent == "unknown":
            state["needs_clarification"] = True
            state["clarification_question"] = "你希望我帮你创建日程、创建任务，还是做安排建议？"
            return state

        if assistant is None:
            if intent == "create_task" and slots.get("task"):
                state["actions"] = [{"type": "create_task", "payload": slots["task"]}]
            elif intent == "create_event" and slots.get("new_event"):
                detector = WorkflowNodes._get_runtime_service(state, "conflict_detector")
                if detector is not None:
                    conflicts = detector.detect_conflicts(events + [slots["new_event"]])
                    state["conflicts"] = conflicts or []
                    if conflicts:
                        state["suggestions"] = detector.suggest_alternatives(slots["new_event"], events) or []
                state["actions"] = [{"type": "create_event", "payload": slots["new_event"]}]
            return state

        if intent in {"schedule_guidance", "event_context_advice", "progress_followup"}:
            plan = await assistant._build_rule_based_plan(
                user_id=user_id,
                user_message=user_message,
                events=events,
                tasks=tasks,
                profile=profile,
                external_context=external_context,
            )
            state["reply"] = plan.get("reply", "")
            state["actions"] = plan.get("actions", [])
            return state

        if intent == "create_task":
            task_payload = slots.get("task") or assistant.text_runtime._build_rule_based_task_payload(user_message)
            if not task_payload.get("content"):
                state["needs_clarification"] = True
                state["clarification_question"] = assistant.formatter.build_clarification_reply(
                    intent="create_task",
                    missing_fields=["content"],
                    prefers_chinese=assistant.text_runtime._prefers_chinese(user_message),
                )
                return state

            state["reply"] = assistant._build_task_preflight_reply(payload=task_payload, user_message=user_message)
            state["actions"] = [{"type": "create_task", "payload": task_payload}]
            return state

        if intent in {"create_event", "event_context_advice"}:
            event_payload = slots.get("new_event") or assistant.text_runtime._build_rule_based_event_payload(user_message)
            event_payload = assistant._apply_place_memory_to_event_payload(
                payload=event_payload,
                user_message=user_message,
                external_context=external_context,
            )
            slots["new_event"] = event_payload
            slots["location"] = event_payload.get("location_coords") or event_payload.get("location_name") or slots.get("location")
            start_time = event_payload.get("start_time")
            end_time = event_payload.get("end_time")

            if not event_payload.get("title") or event_payload.get("title") == "New event" or not start_time or not end_time:
                missing_fields: list[str] = []
                if not event_payload.get("title") or event_payload.get("title") == "New event":
                    missing_fields.append("title")
                if not start_time:
                    missing_fields.append("start_time")
                if not end_time:
                    missing_fields.append("end_time")
                state["needs_clarification"] = True
                state["clarification_question"] = assistant.formatter.build_clarification_reply(
                    intent="create_event",
                    missing_fields=missing_fields or ["start_time", "end_time"],
                    prefers_chinese=assistant.text_runtime._prefers_chinese(user_message),
                )
                return state

            conflict_events = await assistant.event_service.detect_conflicts(
                user_id=user_id,
                start_time=assistant._coerce_datetime(start_time),
                end_time=assistant._coerce_datetime(end_time),
                buffer_before=int(event_payload.get("buffer_before") or 0),
                buffer_after=int(event_payload.get("buffer_after") or 0),
            )
            if conflict_events:
                state["conflicts"] = [
                    {
                        "event_id": item.id,
                        "title": item.title,
                        "start_time": item.start_time.isoformat() if item.start_time else None,
                        "end_time": item.end_time.isoformat() if item.end_time else None,
                    }
                    for item in conflict_events
                ]
                state["suggestions"] = await assistant.event_service.find_alternative_slots(
                    user_id=user_id,
                    duration_minutes=int((assistant._coerce_datetime(end_time) - assistant._coerce_datetime(start_time)).total_seconds() // 60),
                    preferred_date=assistant._coerce_datetime(start_time).date(),
                    buffer_before=int(event_payload.get("buffer_before") or 0),
                    buffer_after=int(event_payload.get("buffer_after") or 0),
                )
                return state

            event_context = await assistant._build_event_specific_context(
                payload=event_payload,
                profile=profile,
                user_message=user_message,
            )
            state["reply"] = assistant._build_event_preflight_reply(
                payload=event_payload,
                user_message=user_message,
                external_context=external_context,
                event_context=event_context,
            )
            state["actions"] = [{"type": "create_event", "payload": event_payload}]
            return state

        state["reply"] = ""
        state["actions"] = []
        return state

    @staticmethod
    async def execute_react_subgraph(state: WorkflowState) -> WorkflowState:
        if not state.get("use_react"):
            return state

        try:
            import app.workflow.react_tools  # noqa: F401
            from app.workflow.react_subgraph import react_subgraph

            return await react_subgraph(state, max_rounds=3)
        except Exception as exc:
            logger.error("ReAct subgraph failed: %s", exc)
            state.setdefault("react_observations", [])
            state.setdefault("react_steps", [])
            return state

    @staticmethod
    async def execute_tools(state: WorkflowState) -> WorkflowState:
        assistant = WorkflowNodes._assistant_from_state(state)
        if assistant is None:
            event_service = WorkflowNodes._get_runtime_service(state, "event_service")
            task_service = WorkflowNodes._get_runtime_service(state, "task_service")
            try:
                for action in state.get("actions", []):
                    action_type = action.get("type", "")
                    payload = action.get("payload", {})
                    if action_type == "create_event" and event_service is not None:
                        await event_service.create_event(payload)
                    elif action_type == "create_task" and task_service is not None:
                        await task_service.create_task(payload)
                    elif action_type == "update_event" and event_service is not None:
                        await event_service.update_event(payload)
                    elif action_type == "delete_event" and event_service is not None:
                        await event_service.delete_event(payload.get("event_id"))
            except Exception as exc:
                state["reply"] = f"执行操作时出错：{exc}"
            return state

        executed = await assistant._execute_actions(
            user_id=state.get("user_id", ""),
            actions=state.get("actions", []),
            user_message=state.get("user_message", ""),
            existing_events=state.get("existing_events", []),
            profile=state.get("profile"),
        )
        state["actions"] = [action.model_dump() if hasattr(action, "model_dump") else action for action in executed]
        return state

    @staticmethod
    async def render_response(state: WorkflowState) -> WorkflowState:
        assistant = WorkflowNodes._assistant_from_state(state)
        user_message = state.get("user_message", "")

        if state.get("needs_clarification"):
            clarification = state.get("clarification_question") or "我还需要一些补充信息。"
            if assistant is not None:
                state["reply"] = assistant._format_reply_text(clarification, user_message=user_message)
            else:
                state["reply"] = clarification
            return state

        if assistant is None:
            if state.get("reply"):
                return state
            reply_parts: list[str] = []
            if state.get("actions"):
                for action in state.get("actions", []):
                    action_type = action.get("type", "")
                    if action_type == "create_event":
                        reply_parts.append(f"已创建事件：{action.get('payload', {}).get('title', '事件')}")
                    elif action_type == "create_task":
                        reply_parts.append(f"已创建任务：{action.get('payload', {}).get('title', action.get('payload', {}).get('content', '任务'))}")
            if state.get("conflicts"):
                reply_parts.append(f"⚠️ 检测到 {len(state.get('conflicts', []))} 个时间冲突")
                if state.get("suggestions"):
                    reply_parts.append(
                        "建议的替代时间：\n" + "\n".join(
                            f"- {item.get('time', item.get('start_time', ''))}: {item.get('reason', '')}".rstrip(": ")
                            for item in state.get("suggestions", [])[:3]
                        )
                    )
            if state.get("habits"):
                reply_parts.append(
                    "💡 根据你的习惯：\n" + "\n".join(
                        f"- {item.get('description', item.get('metadata', {}).get('description', ''))}"
                        for item in state.get("habits", [])[:2]
                    )
                )
            if not reply_parts:
                if state.get("intent") == "query_events":
                    reply_parts.append("已为你查询相关事件。")
                elif state.get("intent") == "create_event":
                    reply_parts.append("事件创建成功！")
                else:
                    reply_parts.append("已完成你的请求。")
            state["reply"] = "\n\n".join(reply_parts)
            return state

        action_models = [
            assistant._ensure_assistant_action(action)
            for action in state.get("actions", [])
        ]
        if state.get("conflicts") and not action_models:
            new_event = state.get("extracted_slots", {}).get("new_event", {})
            if new_event:
                action_models.append(
                    assistant._ensure_assistant_action(
                        {
                            "type": "conflict_warning",
                            "payload": {
                                "title": new_event.get("title"),
                                "event_title": new_event.get("title"),
                                "start_time": new_event.get("start_time"),
                                "end_time": new_event.get("end_time"),
                                "conflicts": state.get("conflicts", []),
                                "suggestions": state.get("suggestions", []),
                            },
                        }
                    )
                )
            if state.get("suggestions"):
                action_models.append(
                    assistant._ensure_assistant_action(
                        {
                            "type": "suggest_reschedule",
                            "payload": {
                                "event_title": new_event.get("title"),
                                "alternatives": state.get("suggestions", []),
                            },
                        }
                    )
                )
        requested_actions = state.get("actions", [])
        reply = state.get("reply", "")

        if not reply or state.get("conflicts"):
            reply = assistant._compose_reply(
                user_message=user_message,
                base_reply=reply,
                actions=action_models,
                requested_actions=requested_actions,
                fallback_message=user_message,
                event_count=len(state.get("existing_events", [])),
                task_count=len(state.get("existing_tasks", [])),
                external_context=state.get("external_context", {}),
            )

        state["reply"] = assistant._format_reply_text(reply, user_message=user_message)
        state["actions"] = [action.model_dump() for action in action_models]
        return state

    @staticmethod
    async def clarify_and_retry(state: WorkflowState) -> WorkflowState:
        if state.get("needs_clarification"):
            state["retry_count"] = state.get("retry_count", 0) + 1
            clarification = state.get("clarification_question")
            if clarification and not state.get("reply"):
                state["reply"] = f"请问{clarification}是什么？"
        return state
