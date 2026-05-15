"""Understanding specialist for structured message interpretation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any

from app.assistant_agents.contracts import (
    AssistantAgentContext,
    ConductorState,
    ContinuationSignals,
    OrchestrationAssessment,
    PlanningIntent,
    TargetScope,
    TimePreference,
    UnderstandingResult,
)
from app.services.assistant_runtime_text import AssistantTextRuntime, TIME_TOKEN_PATTERN
from app.schemas.assistant_understanding import validate_message_understanding_payload


class UnderstandingSpecialist:
    name = "understanding"

    def __init__(
        self,
        text_runtime: AssistantTextRuntime | None = None,
        semantic_extractor: Any | None = None,
    ) -> None:
        self.text_runtime = text_runtime or AssistantTextRuntime()
        self.semantic_extractor = semantic_extractor

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        original_message = context.user_message.strip()
        message = original_message
        message = self._merge_event_creation_clarification_reply(message, context=context)
        message = self._merge_medical_location_clarification_reply(message, context=context)
        merged_event_creation_followup = message != original_message and self._looks_like_event_creation_followup(original_message)
        language = "zh" if self.text_runtime._prefers_chinese(message) else "en"
        continuation = self._detect_continuation(message=message, context=context)
        schedule_continuation = self._understand_task_schedule_continuation(
            message=message,
            language=language,
            context=context,
            continuation=continuation,
        )
        if schedule_continuation is not None:
            state.understanding = schedule_continuation
            return state

        protected_intent = self._protected_update_intent(message) or self._protected_answer_intent(message)
        semantic_understanding = await self._extract_message_semantics_with_llm(message=message, context=context)
        intent = protected_intent or self._intent_from_semantic_understanding(semantic_understanding) or self._classify(message)
        if merged_event_creation_followup:
            intent = "create_event"
        if self._should_force_independent_timed_event_creation(message=message, intent=intent, context=context):
            intent = "create_event"
        if self._should_force_timed_reminder_event(message=message, intent=intent, context=context):
            intent = "create_event"
        if self._should_override_generic_task_event_misread(message=message, intent=intent):
            intent = "create_task"

        if intent in {"reschedule_event", "cancel_event", "mark_event_completed", "mark_task_completed"}:
            understanding = self._understand_update(
                message,
                intent=intent,
                language=language,
                context=context,
                continuation=continuation,
            )
        elif intent == "create_event":
            understanding = await self._understand_event(
                message,
                intent=intent,
                language=language,
                context=context,
                continuation=continuation,
                semantic_understanding=semantic_understanding,
            )
        elif intent == "create_task":
            understanding = self._understand_task(
                message,
                intent=intent,
                language=language,
                continuation=continuation,
                semantic_understanding=semantic_understanding,
            )
        elif intent == "schedule_guidance":
            understanding = UnderstandingResult(
                intent=intent,
                goal_type="schedule_guidance",
                confidence=0.62,
                slots={"requested_items": self.text_runtime._extract_requested_items(message)},
                missing_fields=[],
                ambiguities=["schedule_guidance_not_yet_supported_by_phase_3"],
                can_propose_without_clarification=False,
                requires_clarification=False,
                language=language,
                orchestration=OrchestrationAssessment(
                    conversation_mode="answer",
                    user_goal="schedule_guidance",
                    target_scope=TargetScope(kind="none", resolution="missing"),
                    continuation=continuation,
                    planning_intent=PlanningIntent(),
                    missing_information=[],
                    notes=["phase9a_schedule_guidance"],
                ),
            )
        elif intent == "progress_followup":
            understanding = UnderstandingResult(
                intent=intent,
                goal_type="progress_followup",
                confidence=0.62,
                slots={},
                missing_fields=[],
                ambiguities=[],
                can_propose_without_clarification=False,
                requires_clarification=False,
                language=language,
                orchestration=OrchestrationAssessment(
                    conversation_mode="answer",
                    user_goal="progress_followup",
                    target_scope=TargetScope(kind="task", resolution="ambiguous"),
                    continuation=continuation,
                    planning_intent=PlanningIntent(),
                    missing_information=[],
                    notes=["phase9a_progress_followup"],
                ),
            )
        elif intent == "event_context_advice":
            start_time, end_time = self.text_runtime._extract_time_range(message, reference=context.now)
            start_time = start_time or self._extract_partial_start_time(message, reference=context.now)
            semantic_slots = self._event_slots_from_message_semantics(semantic_understanding)
            location_name = self._clean_location(semantic_slots.get("location_name"), message) if semantic_slots else None
            label = (
                self._clean_event_title(semantic_slots.get("title"), message=message, location_name=location_name)
                if semantic_slots
                else None
            )
            has_enough_event_context = bool(
                label
                and start_time
                and location_name
            )
            understanding = UnderstandingResult(
                intent=intent,
                goal_type="event_context_advice",
                confidence=0.66,
                slots={
                    "title": label,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "location_name": location_name,
                    "semantic_source": "llm_message_understanding" if semantic_slots else "llm_missing",
                },
                missing_fields=[] if has_enough_event_context else ["event_context"],
                ambiguities=[] if has_enough_event_context else ["event_context_incomplete"],
                can_propose_without_clarification=False,
                requires_clarification=False,
                language=language,
                orchestration=OrchestrationAssessment(
                    conversation_mode="answer",
                    user_goal="event_context_advice",
                    target_scope=TargetScope(
                        kind="event",
                        resolution="resolved" if has_enough_event_context else "ambiguous",
                        label=label,
                    ),
                    continuation=continuation,
                    planning_intent=PlanningIntent(),
                    missing_information=[] if has_enough_event_context else ["event_context"],
                    notes=["phase9a_event_context_advice"],
                ),
            )
        else:
            understanding = UnderstandingResult(
                intent=intent,
                goal_type="unknown",
                confidence=0.3,
                slots={},
                missing_fields=[],
                ambiguities=["task_or_event_unknown"],
                can_propose_without_clarification=False,
                requires_clarification=True,
                language=language,
                orchestration=OrchestrationAssessment(
                    conversation_mode="clarification",
                    user_goal="unknown",
                    target_scope=TargetScope(kind="none", resolution="missing"),
                    continuation=continuation,
                    planning_intent=PlanningIntent(),
                    missing_information=["goal_type"],
                    notes=["phase9a_unknown"],
                ),
            )

        state.understanding = understanding
        return state

    def _classify(self, message: str) -> str:
        update_intent = self._classify_update_intent(message)
        if update_intent:
            return update_intent
        direct_answer_intent = self.text_runtime._classify_intent(message)
        if direct_answer_intent in {"event_context_advice", "progress_followup"}:
            return direct_answer_intent
        if self._looks_like_event(message):
            return "create_event"
        if self._looks_like_incomplete_destination_event(message):
            return "create_event"
        if self._looks_like_task(message):
            return "create_task"
        return direct_answer_intent

    def _protected_answer_intent(self, message: str) -> str | None:
        direct_answer_intent = self.text_runtime._classify_intent(message)
        if direct_answer_intent in {"event_context_advice", "progress_followup"}:
            return direct_answer_intent
        if direct_answer_intent == "schedule_guidance" and not self._looks_like_task(message):
            return direct_answer_intent
        return None

    def _protected_update_intent(self, message: str) -> str | None:
        update_intent = self._classify_update_intent(message)
        if update_intent in {"reschedule_event", "mark_task_completed", "mark_event_completed"}:
            return update_intent
        if update_intent and self._looks_like_batch_event_request(message):
            return update_intent
        return None

    def _classify_update_intent(self, message: str) -> str | None:
        if re.search(r"改到|改成|改为|调整到|挪到|推到|推迟到|提前到|延期到|顺延到|延后到|reschedule|move", message, re.I):
            return "reschedule_event"
        if re.search(r"(推迟|延期|后延|延后|顺延|提前)\s*(?:\d+|[一二两三四五六七八九十半])?\s*(天|日|小时|周)", message):
            return "reschedule_event"
        if self._looks_like_batch_event_request(message) and re.search(r"改|调整|挪|移动|推|顺延|延后", message):
            return "reschedule_event"
        if re.search(r"取消|不去了|不用去了|不做了|不做|不弄了|跳过|删掉|删除|cancel|skip", message, re.I):
            return "cancel_event"
        if re.search(r"完成了|做完了|已完成|标记.*完成|打卡|done|completed", message, re.I):
            if self._looks_like_task_completion_message(message):
                return "mark_task_completed"
            return "mark_event_completed"
        return None

    def _looks_like_task_completion_message(self, message: str) -> bool:
        if re.search(r"任务|待办|todo", message, re.I):
            return True
        has_task_subject = bool(re.search(r"论文|写作|复习|整理|作业|报告|材料|毕设", message, re.I))
        has_event_subject = bool(
            re.search(r"日程|会议|开会|组会|课|见面|培训|体检|面试|聚餐|约会|活动|event|meeting", message, re.I)
        )
        return has_task_subject and not has_event_subject

    def _looks_like_task_schedule_continuation(self, message: str, *, context: AssistantAgentContext | None = None) -> bool:
        if self._looks_like_explicit_single_event_request(message) and not self._looks_like_active_task_schedule_request(
            message,
            context=context,
        ):
            return False
        has_schedule_words = bool(
            re.search(r"继续规划|继续安排|继续排|安排下|安排一下|帮我安排|拆成|分成|分几天|排到|排进|分块", message)
        )
        has_time_window = self._message_contains_time_window(message)
        has_duration_hint = self._extract_duration_hint_days(message) is not None
        has_explicit_continuation = bool(re.search(r"继续|刚才|这个任务|那个任务|这一项任务|上一项任务", message))
        return (has_schedule_words and (has_explicit_continuation or has_time_window or has_duration_hint)) or (
            has_time_window and has_duration_hint
        )

    def _looks_like_active_task_schedule_request(self, message: str, *, context: AssistantAgentContext | None) -> bool:
        active_target = (context.external_context or {}).get("active_target") if context is not None else None
        has_active_task = isinstance(active_target, dict) and active_target.get("task_id") is not None
        has_task_name = any(
            str(getattr(task, "content", "") or "") and str(getattr(task, "content", "") or "") in message
            for task in ((context.tasks if context is not None else []) or [])
        )
        has_task_schedule_shape = bool(re.search(r"未来|接下来|预计|大概|差不多|需要|连续|每天|分[几\d一二两三四五六七八九十]+天", message))
        return (has_active_task or has_task_name or re.search(r"任务|待办", message)) and has_task_schedule_shape

    def _looks_like_explicit_single_event_request(self, message: str) -> bool:
        has_time = self.text_runtime._extract_time_range(message)[0] is not None or self._extract_partial_start_time(message) is not None
        if not has_time:
            return False
        if re.search(r"日程|会议|开会|组会|活动|上课|培训|面试|体检|约会|聚餐|见面|碰头", message):
            return True
        return bool(re.search(r"(?:地点|在|去|到)\s*[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,24}", message))

    def _message_contains_time_window(self, message: str) -> bool:
        if self.text_runtime._extract_time_range(message)[0] is not None:
            return True
        return self._extract_partial_start_time(message) is not None and bool(
            re.search(r"到|至|-|~|每天下午|每天上午|每天晚上", message)
        )

    def _detect_continuation(self, *, message: str, context: AssistantAgentContext) -> ContinuationSignals:
        active_target = (context.external_context or {}).get("active_target")
        has_context_reference = self._has_context_reference(message)
        based_on_active_target = isinstance(active_target, dict) and (
            active_target.get("task_id") is not None
            or active_target.get("event_id") is not None
            or active_target.get("proposal_id") is not None
        )
        based_on_pending_proposal = isinstance(active_target, dict) and active_target.get("proposal_id") is not None
        history_text = self._recent_history_text(context.history)
        based_on_history = bool(history_text and self._has_context_reference(message))
        is_following_previous_context = has_context_reference or based_on_active_target or based_on_history
        reason = None
        if based_on_active_target:
            reason = "active_target"
        elif based_on_history:
            reason = "recent_history_reference"
        elif has_context_reference:
            reason = "deictic_reference"
        return ContinuationSignals(
            is_following_previous_context=is_following_previous_context,
            based_on_active_target=based_on_active_target,
            based_on_pending_proposal=based_on_pending_proposal,
            based_on_history=based_on_history,
            reason=reason,
        )

    def _extract_duration_hint_days(self, message: str) -> int | None:
        match = re.search(r"(预计|大概|差不多|需要)?\s*(?P<count>\d+|[一二两三四五六七八九十])\s*天", message)
        if not match:
            return None
        return self._parse_small_int(match.group("count"))

    def _extract_time_preferences(
        self,
        *,
        message: str,
        context: AssistantAgentContext,
    ) -> list[TimePreference]:
        start_time, end_time = self.text_runtime._extract_time_range(message, reference=context.now)
        if start_time is None:
            start_time = self._extract_partial_start_time(message, reference=context.now)
        if start_time is None:
            return []
        if end_time is None:
            end_time = start_time + self._default_block_duration(message)
        has_explicit_date = bool(
            re.search(
                r"(今天|明天|后天|大后天|昨[天日]|前天|本周|这周|下周|下下周|周[一二三四五六日天末]|星期[一二三四五六日天末]|"
                r"\d{4}[年/-]\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2})",
                message,
            )
        )
        reference_now = context.now
        if reference_now.tzinfo is not None:
            reference_now = reference_now.replace(tzinfo=None)
        if not has_explicit_date and start_time <= reference_now:
            start_time += timedelta(days=1)
            end_time += timedelta(days=1)
        return [
            TimePreference(
                date=start_time.date().isoformat(),
                start=start_time.strftime("%H:%M"),
                end=end_time.strftime("%H:%M"),
            )
        ]

    def _expand_time_preferences(self, *, preferences: list[TimePreference], count: int) -> list[TimePreference]:
        if not preferences:
            return []
        seed = preferences[0]
        if count <= 1:
            return [seed]
        base_date = date.fromisoformat(seed.date)
        expanded = [seed]
        for offset in range(1, count):
            expanded.append(
                TimePreference(
                    date=(base_date + timedelta(days=offset)).isoformat(),
                    start=seed.start,
                    end=seed.end,
                )
            )
        return expanded

    def _time_preference_to_slot(self, preference: TimePreference) -> dict[str, Any]:
        return {"date": preference.date, "start": preference.start, "end": preference.end}

    def _default_block_duration(self, message: str):
        if "到" in message or "-" in message or "~" in message:
            return timedelta(hours=1)
        return timedelta(hours=2)

    def _optional_int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _understand_task_schedule_continuation(
        self,
        *,
        message: str,
        language: str,
        context: AssistantAgentContext,
        continuation: ContinuationSignals,
    ) -> UnderstandingResult | None:
        if not self._looks_like_task_schedule_continuation(message, context=context):
            return None

        target = self._resolve_task_target(message, context)
        slots: dict[str, Any] = {
            "action_type": "plan_task_schedule",
            "target_kind": "task",
            "target_id": target.get("target_id"),
            "target_title": target.get("target_title"),
            "candidate_count": target.get("candidate_count"),
            "candidate_titles": target.get("candidate_titles", []),
        }
        missing_fields: list[str] = []
        ambiguities: list[str] = []
        target_scope = TargetScope(kind="task", resolution="missing")
        if target.get("status") == "unique":
            target_scope = TargetScope(
                kind="task",
                resolution="resolved",
                task_id=self._optional_int(target.get("target_id")),
                label=target.get("target_title"),
                candidate_labels=target.get("candidate_titles", []),
            )
        elif target.get("status") == "ambiguous":
            missing_fields.append("target_task")
            ambiguities.append("target_task_ambiguous")
            target_scope = TargetScope(
                kind="task",
                resolution="ambiguous",
                candidate_labels=target.get("candidate_titles", []),
            )
        else:
            missing_fields.append("target_task")
            ambiguities.append("target_task_not_found")

        duration_hint_days = self._extract_duration_hint_days(message)
        time_preferences = self._extract_time_preferences(message=message, context=context)
        schedule_count = duration_hint_days or len(time_preferences) or 1
        if time_preferences:
            expanded_preferences = self._expand_time_preferences(
                preferences=time_preferences,
                count=schedule_count,
            )
            slots["schedule_blocks"] = [self._time_preference_to_slot(item) for item in expanded_preferences]
        else:
            expanded_preferences = []
            slots["schedule_blocks"] = []
            missing_fields.append("time_preferences")
            ambiguities.append("schedule_time_missing")
        slots["duration_hint_days"] = duration_hint_days

        planning_intent = PlanningIntent(
            wants_task_split=schedule_count > 1,
            wants_multi_day_schedule=schedule_count > 1,
            time_preferences=expanded_preferences,
            duration_hint_days=duration_hint_days,
            schedule_count=schedule_count,
        )
        orchestration = OrchestrationAssessment(
            conversation_mode="proposal" if target_scope.resolution == "resolved" and not missing_fields else "clarification",
            user_goal="schedule_blocks",
            target_scope=target_scope,
            continuation=continuation,
            planning_intent=planning_intent,
            missing_information=list(missing_fields),
            proposal_shape="task_schedule_plan",
            notes=["phase9a_task_schedule_continuation"],
        )
        can_propose = target_scope.resolution == "resolved" and bool(expanded_preferences)
        return UnderstandingResult(
            intent="plan_task_schedule",
            goal_type="task",
            confidence=0.82 if can_propose else 0.58,
            slots=slots,
            missing_fields=missing_fields,
            ambiguities=ambiguities,
            assumptions=["focus_blocks_link_to_existing_task"] if can_propose else [],
            can_propose_without_clarification=can_propose,
            requires_clarification=not can_propose,
            language=language,
            orchestration=orchestration,
        )

    def _looks_like_event(self, message: str) -> bool:
        if re.search(r"见面|碰头|集合|约会|聚餐|上课|开会|会议|组会|答辩|面试|体检|看医生|就医|appointment|meeting", message, re.I):
            return True
        if self._extract_partial_start_time(message) is not None and re.search(r"去|到|在|于|at|in|to", message, re.I):
            return True
        if self._message_has_time_details(message) and self._has_date_reference(message) and self._extract_standalone_timed_event_title(message):
            return True
        return False

    def _looks_like_incomplete_destination_event(self, message: str) -> bool:
        if not self._has_date_reference(message):
            return False
        if self._extract_event_location_from_message(message) or self._extract_simple_destination_location(message):
            return True
        return False

    def _merge_event_creation_clarification_reply(self, message: str, *, context: AssistantAgentContext) -> str:
        history = self._history_without_current_user_message(message, context.history)
        if not self._looks_like_event_creation_followup(message):
            return message
        if self._looks_like_independent_timed_event_request(message, context=context):
            return message

        recent_request = self._event_creation_request_from_conversation_state(context) or self._recent_event_creation_request(history)
        if recent_request is None:
            return message

        recent_time_reply = self._event_time_reply_from_conversation_state(context) or self._recent_event_time_reply(history)
        if self._looks_like_event_creation_directive(message) and recent_time_reply is not None:
            merged = self._merge_event_request_and_time(recent_request, recent_time_reply)
            return merged or message

        if self._message_has_time_details(message):
            merged = self._merge_event_request_and_time(recent_request, message)
            return merged or message

        return message

    def _event_creation_request_from_conversation_state(self, context: AssistantAgentContext) -> dict[str, str] | None:
        state = (context.external_context or {}).get("conversation_state")
        if not isinstance(state, dict):
            return None
        active_goal = state.get("active_goal")
        if not isinstance(active_goal, dict) or active_goal.get("type") != "create_event":
            return None
        known_slots = active_goal.get("known_slots")
        if not isinstance(known_slots, dict):
            return None
        title = str(known_slots.get("title") or "").strip()
        location = str(known_slots.get("location_name") or "").strip()
        raw = str(active_goal.get("source_message") or "").strip()
        date_value = str(known_slots.get("date") or "").strip()
        if not title and not location:
            return None
        return {"raw": raw, "title": title, "location": location, "date": date_value}

    def _event_time_reply_from_conversation_state(self, context: AssistantAgentContext) -> str | None:
        state = (context.external_context or {}).get("conversation_state")
        if not isinstance(state, dict):
            return None
        active_goal = state.get("active_goal")
        if not isinstance(active_goal, dict) or active_goal.get("type") != "create_event":
            return None
        known_slots = active_goal.get("known_slots")
        if not isinstance(known_slots, dict):
            return None
        start_time = str(known_slots.get("start_time") or "").strip()
        end_time = str(known_slots.get("end_time") or "").strip()
        if start_time and end_time:
            return f"{start_time}到{end_time}"
        return start_time or None

    def _history_without_current_user_message(self, message: str, history: list[Any]) -> list[Any]:
        items = list(history or [])
        for index in range(len(items) - 1, -1, -1):
            if self._history_role(items[index]) != "user":
                continue
            if self._history_content(items[index]).strip() == message:
                return items[:index]
            break
        return items

    def _looks_like_event_creation_followup(self, message: str) -> bool:
        return self._message_has_time_details(message) or self._looks_like_event_creation_directive(message)

    def _looks_like_independent_timed_event_request(self, message: str, *, context: AssistantAgentContext | None = None) -> bool:
        if not self._message_has_time_details(message):
            return False
        if self._looks_like_active_task_schedule_request(message, context=context):
            return False
        if re.search(r"约会|聚餐|见面|碰头|上课|开会|会议|组会|答辩|面试|体检|接|送", message):
            return True
        location = self._extract_event_location_from_message(message) or self._extract_simple_destination_location(message)
        if location and not re.fullmatch(r"(?:下午|上午|晚上|早上|中午|凌晨)?\s*\d{1,2}\s*(?:点|时).*", message):
            return True
        return bool(self._has_date_reference(message) and self._extract_standalone_timed_event_title(message))

    def _looks_like_event_creation_directive(self, message: str) -> bool:
        return bool(
            re.search(r"(创建|新增|安排|生成|做成|转成).{0,8}(独立|单次|一次性)?日程", message)
            or re.search(r"(独立|单次|一次性)日程", message)
        )

    def _message_has_time_details(self, message: str) -> bool:
        return bool(
            self.text_runtime._extract_time_range(message)[0] is not None
            or self._extract_partial_start_time(message) is not None
            or re.search(r"(开始|起|结束|截止|持续|时长|几点到几点)", message)
        )

    def _extract_standalone_timed_event_title(self, message: str) -> str | None:
        cleaned = message.strip(" \t\r\n，。,；;：:！!?？")
        cleaned = re.sub(
            r"^(?:今天|明天|后天|大后天|今晚|明早|明晚|下个?月(?:的)?(?:\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?|"
            r"下月(?:的)?(?:\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?|"
            r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}|"
            r"(?:下下周|下周|本周|这周|周|星期)[一二三四五六日天末])",
            "",
            cleaned,
            count=1,
        )
        cleaned = TIME_TOKEN_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"\d{1,2}:\d{2}(?:\s*(?:到|至|-|~)\s*\d{1,2}:\d{2})?", "", cleaned)
        cleaned = re.sub(r"(?:上午|下午|晚上|早上|中午|凌晨)?\s*(?:\d{1,2}|[一二两三四五六七八九十两半]+)\s*(?:点|时)(?:半|[一二三四五六七八九十]刻)?(?:\s*(?:到|至|-|~)\s*(?:上午|下午|晚上|早上|中午|凌晨)?\s*(?:\d{1,2}|[一二两三四五六七八九十两半]+)\s*(?:点|时)(?:半|[一二三四五六七八九十]刻)?)?", "", cleaned)
        cleaned = re.sub(r"^(?:我要|我想|帮我|请|麻烦|安排|创建|新增|添加|提醒我|记得)\s*", "", cleaned)
        cleaned = cleaned.strip(" \t\r\n，。,；;：:！!?？")
        if not (2 <= len(cleaned) <= 30):
            return None
        if re.search(r"开始|结束|持续|时长|几点|多久|怎么|要不要|天气", cleaned):
            return None
        if re.fullmatch(r"(?:去|到|在|于)?(?:学校|图书馆|公司|家|宿舍|校医院|医院|教室)", cleaned):
            return None
        if re.search(r"复习|学习|自习|写作|作业|报告|论文|材料|准备|整理|练习|阅读|背单词|运动|跑步|健身|开会|会议|组会|上课|考试|面试", cleaned):
            return cleaned
        return None

    def _recent_event_creation_request(self, history: list[Any]) -> dict[str, str] | None:
        for item in reversed(history[-10:]):
            if self._history_role(item) != "user":
                continue
            content = self._history_content(item).strip()
            if not content or self._message_has_time_details(content) and not re.search(r"去|到|在|于", content):
                continue
            if not (self._looks_like_event(content) or re.search(r"提醒我|去|到|在|于", content)):
                continue
            location = self._extract_event_location_from_message(content) or self._extract_simple_destination_location(content)
            title = self._extract_event_title_from_message(message=content, location_name=location)
            if location or title:
                return {
                    "raw": content,
                    "location": location or "",
                    "title": title or "",
                    "date": self._extract_date_prefix_from_message(content) or "",
                }
        return None

    def _extract_simple_destination_location(self, message: str) -> str | None:
        for match in re.finditer(r"(?:去|到|在|于)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24})(?:$|[，。,；;!！?？])", message):
            location = match.group("location").strip(" \t\r\n，。,；;：:")
            if location in {"约会"}:
                continue
            if not location or re.search(r"(?:\d{1,2}|[一二两三四五六七八九十两半]+)\s*(?:点|时)|开始|结束|截止", location):
                continue
            return location
        return None

    def _recent_event_time_reply(self, history: list[Any]) -> str | None:
        for item in reversed(history[-8:]):
            if self._history_role(item) != "user":
                continue
            content = self._history_content(item).strip()
            if self._message_has_time_details(content):
                return content
        return None

    def _merge_event_request_and_time(self, request: dict[str, str], time_fragment: str) -> str | None:
        normalized_time = time_fragment.strip(" \t\r\n，。,；;：:！!?？")
        date_fragment = request.get("date", "").strip()
        if date_fragment and normalized_time and not self._has_date_reference(normalized_time):
            normalized_time = f"{date_fragment}{normalized_time}"
        pieces: list[str] = [normalized_time] if normalized_time else []

        title = request.get("title", "").strip()
        location = request.get("location", "").strip()
        topic = title or (f"去{location}" if location else "")
        if topic and topic not in normalized_time:
            pieces.append(topic)

        if not pieces:
            raw = request.get("raw", "").strip()
            return raw or None
        return "，".join(dict.fromkeys(pieces))

    def _extract_date_prefix_from_message(self, message: str) -> str | None:
        match = re.search(
            r"(?:大后天|后天|明天|今天|今晚|明早|明晚|下个?月(?:的)?(?:\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?|"
            r"下月(?:的)?(?:\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?|"
            r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}|"
            r"(?:下下周|下周|本周|这周|周|星期)[一二三四五六日天末])",
            message,
        )
        return match.group(0) if match else None

    def _looks_like_task(self, message: str) -> bool:
        return bool(re.search(r"任务|待办|todo|deadline|截止|完成|复习|整理|准备|记得|提醒我", message, re.I))

    def _should_override_generic_task_event_misread(self, *, message: str, intent: str) -> bool:
        if intent != "create_event" or not self._looks_like_task(message):
            return False
        has_time = self.text_runtime._extract_time_range(message)[0] is not None or self._extract_partial_start_time(message) is not None
        has_place = bool(re.search(r"(?:去|到|在|于)\s*[\u4e00-\u9fa5A-Za-z0-9]{2,}", message, re.I))
        has_strong_event_word = bool(
            re.search(r"见面|碰头|集合|约会|聚餐|上课|开会|会议|组会|答辩|面试|体检|看医生|appointment|meeting", message, re.I)
        )
        return not has_time and not has_place and not has_strong_event_word

    def _should_force_timed_reminder_event(
        self,
        *,
        message: str,
        intent: str,
        context: AssistantAgentContext,
    ) -> bool:
        if intent != "create_task" or not re.search(r"提醒我|记得叫我|提醒一下", message):
            return False
        has_time = bool(
            self.text_runtime._extract_time_range(message, reference=context.now)[0] is not None
            or self._extract_partial_start_time(message, reference=context.now) is not None
        )
        if not has_time:
            return False
        has_event_target = bool(
            self._extract_simple_destination_location(message)
            or re.search(r"开会|会议|组会|上课|面试|体检|看医生|聚餐|约会|见面|meeting|appointment", message, re.I)
        )
        return has_event_target

    def _should_force_independent_timed_event_creation(
        self,
        *,
        message: str,
        intent: str,
        context: AssistantAgentContext,
    ) -> bool:
        if intent == "event_context_advice":
            return False
        if re.search(r"几点出发|什么时候出发|多久出发|要不要带伞|带伞|天气|通勤|怎么去", message):
            return False
        if re.search(r"改成|改到|改为|修改|调整|换成|开到|结束到|提前|推迟|延后|缩短|延长", message):
            return False
        if self._looks_like_active_task_schedule_request(message, context=context):
            return False
        has_time = bool(
            self.text_runtime._extract_time_range(message, reference=context.now)[0] is not None
            or self._extract_partial_start_time(message, reference=context.now) is not None
        )
        if not has_time:
            return False
        if self._has_date_reference(message) and self._extract_standalone_timed_event_title(message):
            return True
        return bool(
            re.search(r"约会|聚餐|见面|碰头|上课|开会|会议|组会|答辩|面试|体检|看医生|接|送", message)
            or self._extract_simple_destination_location(message)
        )

    def _merge_medical_location_clarification_reply(
        self,
        message: str,
        *,
        context: AssistantAgentContext,
    ) -> str:
        choice_match = re.fullmatch(r"(?:我)?(?:是)?(?:在|去|到)?(?P<place>校医院|校内医院|学校医院|校外医院)", message.strip())
        if not choice_match:
            return message

        history = list(context.history or [])
        if not self._recent_assistant_asked_medical_location(history):
            return message

        place = choice_match.group("place")
        if place in {"校内医院", "学校医院"}:
            place = "校医院"
        previous_request = self._recent_school_medical_request(history)
        if not previous_request:
            return message

        rewritten = re.sub(
            r"(?P<prefix>去|到|在)?学校(?=(?:体检|看医生|就医|门诊|诊所))",
            lambda match: f"{match.group('prefix') or '去'}{place}",
            previous_request,
            count=1,
        )
        if rewritten == previous_request:
            rewritten = f"{previous_request}，地点在{place}"
        return rewritten

    @staticmethod
    def _history_content(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("content") or "")
        return str(getattr(item, "content", "") or "")

    @staticmethod
    def _history_role(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("role") or "")
        return str(getattr(item, "role", "") or "")

    def _recent_assistant_asked_medical_location(self, history: list[Any]) -> bool:
        for item in reversed(history[-6:]):
            if self._history_role(item) != "assistant":
                continue
            content = self._history_content(item)
            if "校医院" in content and "校外医院" in content:
                return True
        return False

    def _recent_school_medical_request(self, history: list[Any]) -> str | None:
        for item in reversed(history[-8:]):
            if self._history_role(item) != "user":
                continue
            content = self._history_content(item).strip()
            if "学校" in content and re.search(r"体检|看医生|就医|门诊|诊所", content):
                return content
        return None

    async def _understand_event(
        self,
        message: str,
        *,
        intent: str,
        language: str,
        context: AssistantAgentContext,
        continuation: ContinuationSignals,
        semantic_understanding: dict[str, Any] | None = None,
    ) -> UnderstandingResult:
        start_time, end_time = self.text_runtime._extract_time_range(message, reference=context.now)
        start_time = start_time or self._extract_partial_start_time(message, reference=context.now)
        broad_time_period = self._extract_broad_time_period(message)
        semantic_slots = self._event_slots_from_message_semantics(semantic_understanding)
        semantic_source = "llm_message_understanding" if semantic_slots is not None else "llm_missing"
        if semantic_slots is None:
            semantic_slots = await self._extract_event_semantics_with_llm(message=message, context=context)
            semantic_source = "llm_event_semantics" if semantic_slots is not None else "llm_missing"
        if semantic_slots is not None:
            location_name = self._clean_location(semantic_slots.get("location_name"), message)
            title = self._clean_event_title(semantic_slots.get("title"), message=message, location_name=location_name)
        else:
            location_name = None
            title = None
        if not title:
            title = self._extract_explicit_arranged_event_title(message)
        if not location_name:
            location_name = self._extract_event_location_from_message(message) or self._extract_simple_destination_location(message)
        if not title:
            title = self._extract_event_title_from_message(message=message, location_name=location_name)
        if not title:
            title = self._extract_standalone_timed_event_title(message)
        if not title:
            title = self._extract_social_event_title(message)

        slots: dict[str, Any] = {
            "title": title,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "location_name": location_name,
            "semantic_source": semantic_source,
        }
        if broad_time_period:
            slots["broad_time_period"] = broad_time_period
        missing_fields: list[str] = []
        if not title:
            missing_fields.append("title")
        if not start_time:
            missing_fields.append("start_time")
        if not end_time:
            missing_fields.append("end_time_or_duration")

        ambiguities: list[str] = []
        assumptions: list[str] = []
        can_propose = False
        requires_clarification = bool(missing_fields)

        uses_default_duration = bool(end_time and not self._has_explicit_end_or_duration(message))

        if title and start_time and missing_fields == ["end_time_or_duration"]:
            can_propose = True
            assumptions.append("default_event_duration_60_minutes")
        elif title and start_time and not location_name and re.search(r"约会|聚餐|见面|碰头", message):
            can_propose = True
            assumptions.append("default_event_duration_60_minutes")
            assumptions.append("location_not_specified")
        elif title and start_time and end_time:
            can_propose = True
            requires_clarification = False
            if uses_default_duration:
                assumptions.append("default_event_duration_60_minutes")
        elif not start_time:
            ambiguities.append("event_time_window_too_broad")
        elif not location_name and re.search(r"去|到|在", message):
            ambiguities.append("location_unclear")
        if (
            location_name
            and re.search(r"体检|看医生|就医|医院|门诊|诊所", message)
            and re.search(r"学校", location_name)
            and not self._has_confirmed_place_alias(context, location_name)
        ):
            ambiguities.append("medical_location_conflict")
            missing_fields.append("location_detail")
            can_propose = False
            requires_clarification = True

        if not start_time and re.fullmatch(r".{0,6}(我要|想)?去?约会[。！!？?]?", message):
            can_propose = False
            requires_clarification = True
            missing_fields = ["intent_detail", "start_time", "location_name", "end_time_or_duration"]
            ambiguities.append("dating_request_too_vague")
        orchestration = self._build_creation_orchestration(
            goal_type="event",
            title=title,
            target_label=title,
            continuation=continuation,
            missing_fields=missing_fields,
            can_propose=can_propose,
            proposal_shape="event_creation",
            user_goal="create_event",
        )
        orchestration.notes.append(semantic_source)

        return UnderstandingResult(
            intent=intent,
            goal_type="event",
            confidence=0.72 if can_propose else 0.58,
            slots=slots,
            missing_fields=missing_fields,
            ambiguities=ambiguities,
            assumptions=assumptions,
            can_propose_without_clarification=can_propose,
            requires_clarification=requires_clarification,
            language=language,
            orchestration=orchestration,
        )

    def _has_confirmed_place_alias(self, context: AssistantAgentContext, location_name: str | None) -> bool:
        if not location_name:
            return False
        assistant_memory = (context.external_context or {}).get("assistant_memory")
        if not isinstance(assistant_memory, dict):
            return False
        entries = assistant_memory.get("places")
        if not isinstance(entries, list):
            return False
        alias_pattern = re.escape(location_name.strip())
        for raw_entry in entries:
            if not isinstance(raw_entry, str):
                continue
            entry = raw_entry.strip()
            if re.search(rf"(?:^|[:：\s]){alias_pattern}\s*(?:=|＝|是|位于|在)\s*", entry):
                return True
            if re.search(rf"^.*?-\s*{alias_pattern}\s*(?:=|＝|是|位于|在)\s*", entry):
                return True
        return False

    async def _extract_message_semantics_with_llm(
        self,
        *,
        message: str,
        context: AssistantAgentContext,
    ) -> dict[str, Any] | None:
        extractor = self.semantic_extractor
        if extractor is None or not getattr(extractor, "enabled", False):
            return None
        method = getattr(extractor, "extract_message_understanding", None)
        if method is None:
            return None
        try:
            raw = await method(
                user_message=message,
                now=context.now,
                profile=context.profile,
                external_context=context.external_context,
            )
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        try:
            raw = validate_message_understanding_payload(raw)
        except ValueError:
            return None
        confidence = raw.get("confidence")
        if isinstance(confidence, (int, float)) and confidence < 0.5:
            return None
        return raw

    def _intent_from_semantic_understanding(self, semantic_understanding: dict[str, Any] | None) -> str | None:
        if not semantic_understanding:
            return None
        intent = semantic_understanding.get("intent")
        if not isinstance(intent, str):
            return None
        allowed = {
            "create_event",
            "create_task",
            "reschedule_event",
            "cancel_event",
            "mark_event_completed",
            "mark_task_completed",
            "schedule_guidance",
            "progress_followup",
            "event_context_advice",
            "unknown",
        }
        return intent if intent in allowed else None

    def _event_slots_from_message_semantics(self, semantic_understanding: dict[str, Any] | None) -> dict[str, Any] | None:
        if not semantic_understanding:
            return None
        if semantic_understanding.get("intent") != "create_event" and semantic_understanding.get("goal_type") != "event":
            return None
        title = semantic_understanding.get("title")
        location_name = semantic_understanding.get("location_name")
        if not title and not location_name:
            return None
        return {"title": title, "location_name": location_name, "confidence": semantic_understanding.get("confidence")}

    def _task_slots_from_message_semantics(self, semantic_understanding: dict[str, Any] | None) -> dict[str, Any] | None:
        if not semantic_understanding:
            return None
        if semantic_understanding.get("intent") != "create_task" and semantic_understanding.get("goal_type") != "task":
            return None
        content = semantic_understanding.get("task_content") or semantic_understanding.get("content")
        if not isinstance(content, str) or not content.strip():
            return None
        return {"content": content.strip(" \t\r\n，。,；;：:！!?？“”\"'")}

    async def _extract_event_semantics_with_llm(
        self,
        *,
        message: str,
        context: AssistantAgentContext,
    ) -> dict[str, Any] | None:
        extractor = self.semantic_extractor
        if extractor is None or not getattr(extractor, "enabled", False):
            return None
        method = getattr(extractor, "extract_event_creation_semantics", None)
        if method is None:
            return None
        try:
            raw = await method(
                user_message=message,
                now=context.now,
                profile=context.profile,
                external_context=context.external_context,
            )
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        confidence = raw.get("confidence")
        if isinstance(confidence, (int, float)) and confidence < 0.5:
            return None
        title = self._clean_event_title(raw.get("title"), message=message, location_name=raw.get("location_name"))
        location_name = self._clean_location(raw.get("location_name"), message)
        if not title and not location_name:
            return None
        return {
            "title": title,
            "location_name": location_name,
            "confidence": confidence,
        }

    def _understand_task(
        self,
        message: str,
        *,
        intent: str,
        language: str,
        continuation: ContinuationSignals,
        semantic_understanding: dict[str, Any] | None = None,
    ) -> UnderstandingResult:
        semantic_task = self._task_slots_from_message_semantics(semantic_understanding)
        semantic_source = "llm_message_understanding" if semantic_task is not None else "llm_missing"
        payload = {
            "content": semantic_task.get("content") if semantic_task else self.text_runtime._extract_task_content(message),
            "deadline": None,
            "estimated_duration_minutes": self.text_runtime._extract_duration_minutes(message),
            "priority": 3,
            "can_split": bool(re.search(r"拆分|拆成|分成|分两次|分几次|分块", message)),
            "preferred_period": self.text_runtime._extract_period_preference(message),
            "schedule_window": self._extract_task_schedule_window(message),
            "wants_schedule_options": self._looks_like_new_task_schedule_request(message),
        }
        content = payload.get("content")
        generic_review = bool(content and re.fullmatch(r"(复习|学习|准备)", str(content)))
        missing_fields: list[str] = []
        ambiguities: list[str] = []
        if not content:
            missing_fields.append("content")
        if generic_review:
            missing_fields.extend(["subject", "deadline_or_time_window", "rhythm"])
            ambiguities.append("generic_study_task")

        can_propose = bool(content and not generic_review)
        orchestration = self._build_creation_orchestration(
            goal_type="task",
            title=content,
            target_label=content,
            continuation=continuation,
            missing_fields=missing_fields,
            can_propose=can_propose,
            proposal_shape="task_creation",
            user_goal="create_task",
        )
        orchestration.notes.append(semantic_source)
        payload["semantic_source"] = semantic_source
        return UnderstandingResult(
            intent=intent,
            goal_type="task",
            confidence=0.7 if can_propose else 0.55,
            slots=payload,
            missing_fields=missing_fields,
            ambiguities=ambiguities,
            assumptions=["task_can_start_as_pending_schedule"] if can_propose else [],
            can_propose_without_clarification=can_propose,
            requires_clarification=bool(missing_fields),
            language=language,
            orchestration=orchestration,
        )

    def _looks_like_new_task_schedule_request(self, message: str) -> bool:
        has_schedule_word = bool(re.search(r"安排|规划|排一下|排进|排到|拆分|拆成|分成|计划", message))
        has_time_window = self._extract_task_schedule_window(message) is not None
        has_study_or_work_task = bool(re.search(r"复习|学习|准备|整理|论文|作业|报告|材料|背单词|练习", message))
        return has_schedule_word and (has_time_window or has_study_or_work_task)

    def _extract_task_schedule_window(self, message: str) -> str | None:
        if re.search(r"这周|本周", message):
            return "this_week"
        if re.search(r"下周", message):
            return "next_week"
        if re.search(r"今天", message):
            return "today"
        if re.search(r"明天", message):
            return "tomorrow"
        return None

    def _build_creation_orchestration(
        self,
        *,
        goal_type: str,
        title: str | None,
        target_label: str | None,
        continuation: ContinuationSignals,
        missing_fields: list[str],
        can_propose: bool,
        proposal_shape: str,
        user_goal: str,
    ) -> OrchestrationAssessment:
        target_scope = TargetScope(kind="none", resolution="missing")
        if goal_type == "event":
            target_scope = TargetScope(
                kind="event",
                resolution="resolved" if can_propose else "missing",
                label=target_label,
            )
        elif goal_type == "task":
            target_scope = TargetScope(
                kind="task",
                resolution="resolved" if can_propose else "missing",
                label=target_label,
            )
        return OrchestrationAssessment(
            conversation_mode="proposal" if can_propose else "clarification",
            user_goal=user_goal,
            target_scope=target_scope,
            continuation=continuation,
            planning_intent=PlanningIntent(),
            missing_information=list(missing_fields),
            proposal_shape=proposal_shape,
            notes=["phase9a_creation", goal_type, title or ""],
        )

    def _understand_update(
        self,
        message: str,
        *,
        intent: str,
        language: str,
        context: AssistantAgentContext,
        continuation: ContinuationSignals,
    ) -> UnderstandingResult:
        if intent == "mark_task_completed":
            target = self._resolve_task_target(message, context)
            return self._update_understanding_from_target(
                intent=intent,
                goal_type="task",
                target=target,
                language=language,
                continuation=continuation,
            )

        target = self._resolve_batch_event_target(message, context, intent=intent) or self._resolve_event_target(message, context)
        missing_fields: list[str] = []
        ambiguities: list[str] = []
        slots: dict[str, Any] = {
            "action_type": intent,
            "target_kind": "event",
            "target_scope": target.get("target_scope", "single"),
            "target_id": target.get("target_id"),
            "target_title": target.get("target_title"),
            "target_ids": target.get("target_ids", []),
            "target_titles": target.get("target_titles", []),
            "target_date": target.get("target_date"),
            "candidate_count": target.get("candidate_count"),
            "candidate_titles": target.get("candidate_titles", []),
        }

        if target.get("status") == "not_found":
            missing_fields.append("target_event")
            ambiguities.append("target_event_not_found")
        elif target.get("status") == "ambiguous":
            missing_fields.append("target_event")
            ambiguities.extend(target.get("ambiguities") or ["target_event_ambiguous"])

        if intent == "reschedule_event":
            target_reference = context.now
            target_id = self._optional_int(target.get("target_id"))
            if target_id is not None:
                matched_event = next((event for event in context.events if getattr(event, "id", None) == target_id), None)
                if matched_event is not None and getattr(matched_event, "start_time", None) is not None:
                    target_reference = getattr(matched_event, "start_time")
            location_name = self._extract_update_location_from_message(message)
            if location_name:
                slots["location_name"] = location_name
            if target.get("target_scope") == "batch":
                shift_days = self._extract_batch_shift_days(message)
                _source_date, destination_date = self._extract_batch_reschedule_dates(message, context)
                slots["batch_shift_days"] = shift_days
                slots["batch_destination_date"] = destination_date.isoformat() if destination_date else None
                if shift_days is None and destination_date is None:
                    missing_fields.append("batch_shift_days")
                    ambiguities.append("batch_reschedule_shift_missing")
            else:
                date_reference = context.now if self._has_date_reference(message) else target_reference
                start_time, end_time = self.text_runtime._extract_time_range(message, reference=date_reference)
                partial_start_time = self._extract_partial_start_time(
                    message,
                    reference=date_reference,
                    inherited_period_reference=target_reference,
                )
                if partial_start_time is not None and not self._has_explicit_end_or_duration(message):
                    start_time = partial_start_time
                    end_time = None
                if end_time is not None and not self._has_explicit_end_or_duration(message):
                    end_time = None
                    start_time = partial_start_time or start_time
                else:
                    start_time = start_time or partial_start_time
                slots["new_start_time"] = start_time.isoformat() if start_time else None
                slots["new_end_time"] = end_time.isoformat() if end_time else None
                if not start_time:
                    missing_fields.append("new_start_time")
                    ambiguities.append("reschedule_time_missing")

        can_propose = target.get("status") in {"unique", "batch"} and not missing_fields
        orchestration = self._build_event_update_orchestration(
            intent=intent,
            target=target,
            continuation=continuation,
            missing_fields=missing_fields,
            slots=slots,
        )
        return UnderstandingResult(
            intent=intent,
            goal_type="event",
            confidence=0.74 if can_propose else 0.55,
            slots=slots,
            missing_fields=missing_fields,
            ambiguities=ambiguities,
            assumptions=[],
            can_propose_without_clarification=can_propose,
            requires_clarification=not can_propose,
            language=language,
            orchestration=orchestration,
        )

    def _update_understanding_from_target(
        self,
        *,
        intent: str,
        goal_type: str,
        target: dict[str, Any],
        language: str,
        continuation: ContinuationSignals,
    ) -> UnderstandingResult:
        missing_fields: list[str] = []
        ambiguities: list[str] = []
        if target.get("status") == "not_found":
            missing_fields.append(f"target_{goal_type}")
            ambiguities.append(f"target_{goal_type}_not_found")
        elif target.get("status") == "ambiguous":
            missing_fields.append(f"target_{goal_type}")
            ambiguities.append(f"target_{goal_type}_ambiguous")
        can_propose = target.get("status") == "unique"
        target_scope = TargetScope(kind=goal_type if goal_type in {"task", "event"} else "none", resolution="missing")
        if target.get("status") == "unique":
            if goal_type == "task":
                target_scope = TargetScope(
                    kind="task",
                    resolution="resolved",
                    task_id=self._optional_int(target.get("target_id")),
                    label=target.get("target_title"),
                    candidate_labels=target.get("candidate_titles", []),
                )
            elif goal_type == "event":
                target_scope = TargetScope(
                    kind="event",
                    resolution="resolved",
                    event_id=self._optional_int(target.get("target_id")),
                    label=target.get("target_title"),
                    candidate_labels=target.get("candidate_titles", []),
                )
        elif target.get("status") == "ambiguous":
            target_scope = TargetScope(
                kind=goal_type if goal_type in {"task", "event"} else "none",
                resolution="ambiguous",
                candidate_labels=target.get("candidate_titles", []),
            )
        orchestration = OrchestrationAssessment(
            conversation_mode="proposal" if can_propose else "clarification",
            user_goal="complete_task" if intent == "mark_task_completed" else "update_target",
            target_scope=target_scope,
            continuation=continuation,
            planning_intent=PlanningIntent(),
            missing_information=list(missing_fields),
            proposal_shape="task_status_update" if goal_type == "task" else "event_status_update",
            notes=["phase9a_update_target"],
        )
        return UnderstandingResult(
            intent=intent,
            goal_type=goal_type,  # type: ignore[arg-type]
            confidence=0.74 if can_propose else 0.55,
            slots={
                "action_type": intent,
                "target_kind": goal_type,
                "target_id": target.get("target_id"),
                "target_title": target.get("target_title"),
                "candidate_count": target.get("candidate_count"),
                "candidate_titles": target.get("candidate_titles", []),
            },
            missing_fields=missing_fields,
            ambiguities=ambiguities,
            assumptions=[],
            can_propose_without_clarification=can_propose,
            requires_clarification=not can_propose,
            language=language,
            orchestration=orchestration,
        )

    def _build_event_update_orchestration(
        self,
        *,
        intent: str,
        target: dict[str, Any],
        continuation: ContinuationSignals,
        missing_fields: list[str],
        slots: dict[str, Any],
    ) -> OrchestrationAssessment:
        target_scope = TargetScope(kind="event", resolution="missing")
        proposal_shape = "event_status_update"
        user_goal = "update_event"
        if intent == "reschedule_event":
            proposal_shape = "event_batch_reschedule" if target.get("target_scope") == "batch" else "event_reschedule"
            user_goal = "reschedule_events_batch" if target.get("target_scope") == "batch" else "reschedule_event"
        elif intent == "cancel_event":
            proposal_shape = "event_batch_cancel" if target.get("target_scope") == "batch" else "event_cancel"
            user_goal = "cancel_events_batch" if target.get("target_scope") == "batch" else "cancel_event"
        elif intent == "mark_event_completed":
            proposal_shape = "event_status_update"
            user_goal = "complete_event"

        if target.get("status") == "unique":
            target_scope = TargetScope(
                kind="event",
                resolution="resolved",
                event_id=self._optional_int(target.get("target_id")),
                label=target.get("target_title"),
                candidate_labels=target.get("candidate_titles", []),
            )
        elif target.get("status") == "batch":
            target_scope = TargetScope(
                kind="batch_events",
                resolution="resolved",
                event_ids=[int(event_id) for event_id in target.get("target_ids", []) if event_id is not None],
                label=target.get("target_date"),
                candidate_labels=target.get("target_titles", []),
            )
        elif target.get("status") == "ambiguous":
            target_scope = TargetScope(
                kind="batch_events" if target.get("target_scope") == "batch" else "event",
                resolution="ambiguous",
                label=target.get("target_date"),
                candidate_labels=target.get("candidate_titles", []),
            )

        planning_intent = PlanningIntent()
        if target.get("target_scope") == "batch" and intent == "reschedule_event":
            destination = slots.get("batch_destination_date")
            shift_days = slots.get("batch_shift_days")
            planning_intent = PlanningIntent(
                wants_multi_day_schedule=True,
                schedule_count=target.get("candidate_count"),
            )
            if destination:
                planning_intent.time_preferences = [TimePreference(date=str(destination), start="00:00", end="00:00")]
            if isinstance(shift_days, int):
                planning_intent.duration_hint_days = shift_days

        return OrchestrationAssessment(
            conversation_mode="proposal" if target_scope.resolution == "resolved" and not missing_fields else "clarification",
            user_goal=user_goal,
            target_scope=target_scope,
            continuation=continuation,
            planning_intent=planning_intent,
            missing_information=list(missing_fields),
            proposal_shape=proposal_shape,
            notes=["phase9a_event_update"],
        )

    def _resolve_event_target(self, message: str, context: AssistantAgentContext) -> dict[str, Any]:
        events = context.events
        active_events = [event for event in events if (getattr(event, "status", None) or "planned") != "canceled"]
        target_date = None
        target_date_message = self._event_target_source_fragment(message)
        if self._has_date_reference(target_date_message):
            reference_date = (context.now or datetime.now()).date()
            target_date = self.text_runtime._extract_target_date(target_date_message, reference_date)
        scored = []
        for event in active_events:
            score = self._score_event_target(message, event, target_date=target_date)
            if score > 0:
                scored.append((score, event))
        if self._has_context_reference(message):
            contextual = self._resolve_contextual_target(
                context=context,
                candidates=active_events,
                title_attr="title",
            )
            if contextual.get("status") == "unique":
                scored.append((12, contextual["target"]))
            elif not scored and contextual.get("status") == "ambiguous":
                return contextual
        return self._target_result(scored, title_attr="title")

    def _event_target_source_fragment(self, message: str) -> str:
        delimiter = re.search(r"改到|改成|改为|调整到|挪到|推到|推迟到|提前到|延期到|顺延到|延后到", message)
        if delimiter:
            return message[: delimiter.start()]
        return message

    def _resolve_batch_event_target(
        self,
        message: str,
        context: AssistantAgentContext,
        *,
        intent: str,
    ) -> dict[str, Any] | None:
        if intent not in {"cancel_event", "reschedule_event"}:
            return None
        if not self._looks_like_batch_event_request(message):
            return None
        if not self._has_date_reference(message):
            return {
                "status": "ambiguous",
                "target_scope": "batch",
                "candidate_count": 0,
                "candidate_titles": [],
                "ambiguities": ["batch_event_date_missing"],
            }

        reference_date = (context.now or datetime.now()).date()
        source_date, _destination_date = self._extract_batch_reschedule_dates(message, context) if intent == "reschedule_event" else (None, None)
        if intent == "reschedule_event" and _destination_date is not None and source_date is None:
            return {
                "status": "ambiguous",
                "target_scope": "batch",
                "candidate_count": 0,
                "candidate_titles": [],
                "ambiguities": ["batch_event_date_missing"],
            }
        target_date = source_date or self.text_runtime._extract_target_date(message, reference_date)
        active_events = [
            event
            for event in context.events
            if (getattr(event, "status", None) or "planned") != "canceled"
            and getattr(getattr(event, "start_time", None), "date", lambda: None)() == target_date
        ]
        if not active_events:
            return {
                "status": "not_found",
                "target_scope": "batch",
                "target_date": target_date.isoformat(),
                "candidate_count": 0,
                "candidate_titles": [],
            }
        if len(active_events) > 8:
            return {
                "status": "ambiguous",
                "target_scope": "batch",
                "target_date": target_date.isoformat(),
                "candidate_count": len(active_events),
                "candidate_titles": [str(getattr(event, "title", "")) for event in active_events[:3]],
                "ambiguities": ["batch_event_target_too_large"],
            }
        return {
            "status": "batch",
            "target_scope": "batch",
            "target_date": target_date.isoformat(),
            "target_ids": [getattr(event, "id", None) for event in active_events],
            "target_titles": [str(getattr(event, "title", "")) for event in active_events],
            "candidate_count": len(active_events),
            "candidate_titles": [str(getattr(event, "title", "")) for event in active_events[:3]],
        }

    def _looks_like_batch_event_request(self, message: str) -> bool:
        return bool(
            re.search(
                r"(所有|全部|全都|当天|这天|那天).{0,8}(日程|会议|课|安排|活动)|"
                r"(日程|会议|课|安排|活动).{0,8}(所有|全部|全都)",
                message,
            )
        )

    def _has_date_reference(self, message: str) -> bool:
        return bool(
            re.search(
                r"今天|明天|后天|大后天|昨天|前天|本周|这周|下周|周[一二三四五六日天]|"
                r"(?:下个?月|下月)(?:的)?(?:\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?|"
                r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|\d{4}-\d{1,2}-\d{1,2}",
                message,
            )
        )

    def _extract_batch_shift_days(self, message: str) -> int | None:
        match = re.search(r"(?P<direction>推迟|延期|后延|延后|顺延|提前)\s*(?P<amount>\d+|[一二两三四五六七八九十])?\s*(天|日)", message)
        if not match:
            return None
        amount = self._parse_small_int(match.group("amount")) or 1
        if match.group("direction") == "提前":
            return -amount
        return amount

    def _extract_batch_reschedule_dates(
        self,
        message: str,
        context: AssistantAgentContext,
    ) -> tuple[date | None, date | None]:
        delimiter = re.search(r"改到|改成|改为|调整到|挪到|推到|推迟到|提前到|延期到|顺延到|延后到", message)
        if not delimiter:
            return None, None
        source_fragment = message[: delimiter.start()]
        destination_fragment = message[delimiter.end() :]
        reference_date = (context.now or datetime.now()).date()
        source_date = (
            self.text_runtime._extract_target_date(source_fragment, reference_date)
            if self._has_date_reference(source_fragment)
            else None
        )
        destination_date = (
            self.text_runtime._extract_target_date(destination_fragment, reference_date)
            if self._has_date_reference(destination_fragment)
            else None
        )
        return source_date, destination_date

    def _parse_small_int(self, value: str | None) -> int | None:
        if not value:
            return None
        if value.isdigit():
            return int(value)
        digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if value in digits:
            return digits[value]
        if value == "十":
            return 10
        if value.startswith("十"):
            return 10 + digits.get(value[1:], 0)
        if value.endswith("十"):
            return digits.get(value[:1], 0) * 10
        if "十" in value:
            left, right = value.split("十", 1)
            return digits.get(left, 1) * 10 + digits.get(right, 0)
        return None

    def _has_explicit_end_or_duration(self, message: str) -> bool:
        return bool(
            re.search(
                r"(?:从|由).{0,12}到|"
                r"(?:\d{1,2}|[一二两三四五六七八九十])\s*(?:点|时).{0,8}(?:到|至|~|-).{0,8}"
                r"(?:\d{1,2}|[一二两三四五六七八九十])\s*(?:点|时)|"
                r"(?:持续|时长|预计|大概|约)?\s*(?:\d+|[一二两三四五六七八九十半])\s*(?:小时|分钟)",
                message,
            )
        )

    def _resolve_task_target(self, message: str, context: AssistantAgentContext) -> dict[str, Any]:
        tasks = context.tasks
        active_tasks = [task for task in tasks if (getattr(task, "status", None) or "pending") not in {"done", "canceled", "archived"}]
        scored = []
        for task in active_tasks:
            score = self._score_text_target(message, getattr(task, "content", None))
            if score > 0:
                scored.append((score, task))
        if self._has_context_reference(message):
            contextual = self._resolve_contextual_target(
                context=context,
                candidates=active_tasks,
                title_attr="content",
            )
            if contextual.get("status") == "unique":
                scored.append((12, contextual["target"]))
            elif not scored and contextual.get("status") == "ambiguous":
                return contextual
        return self._target_result(scored, title_attr="content")

    def _score_event_target(self, message: str, event: Any, *, target_date: date | None = None) -> int:
        score = self._score_text_target(message, getattr(event, "title", None))
        score += self._score_text_target(message, getattr(event, "location_name", None))
        start_time = getattr(event, "start_time", None)
        if start_time is not None and hasattr(start_time, "hour"):
            hour = int(start_time.hour)
            if re.search(rf"{hour}\s*(点|时)", message):
                score += 4
            if target_date is not None and start_time.date() == target_date:
                score += 6
        return score

    def _score_text_target(self, message: str, value: str | None) -> int:
        if not value:
            return 0
        text = str(value).strip()
        if not text:
            return 0
        if self._is_exact_target_mentioned(message, text):
            return 80
        if self._is_exact_target_alias_mentioned(message, text):
            return 72
        score = 0
        for token in self._target_tokens(text):
            if token in message:
                score += min(len(token), 4)
        return min(score, 24)

    def _target_tokens(self, text: str) -> list[str]:
        tokens = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text)
        if re.search(r"[\u4e00-\u9fa5]", text):
            compact = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
            for size in range(2, min(len(compact), 4) + 1):
                tokens.extend(compact[index : index + size] for index in range(0, len(compact) - size + 1))
        if len(text) >= 2:
            tokens.append(text)
        return list(dict.fromkeys(tokens))

    def _has_context_reference(self, message: str) -> bool:
        return bool(re.search(r"这个|那个|这条|那条|它|刚才|刚刚|上一个|前面那个|刚说的", message))

    def _resolve_contextual_target(
        self,
        *,
        context: AssistantAgentContext,
        candidates: list[Any],
        title_attr: str,
    ) -> dict[str, Any]:
        if not candidates:
            return {"status": "not_found", "candidate_count": 0, "candidate_titles": []}

        active = self._resolve_active_target(context=context, candidates=candidates, title_attr=title_attr)
        if active.get("status") == "unique":
            return active

        recent_text = self._recent_history_text(context.history)
        if recent_text:
            mentioned = [
                candidate
                for candidate in candidates
                if self._is_exact_target_mentioned(recent_text, getattr(candidate, title_attr, None))
            ]
            if len(mentioned) == 1:
                return {"status": "unique", "target": mentioned[0]}
            if len(mentioned) > 1:
                return {
                    "status": "ambiguous",
                    "candidate_count": len(mentioned),
                    "candidate_titles": [str(getattr(candidate, title_attr, "")) for candidate in mentioned[:3]],
                }

        if len(candidates) == 1:
            return {"status": "unique", "target": candidates[0]}
        return {
            "status": "ambiguous",
            "candidate_count": len(candidates),
            "candidate_titles": [str(getattr(candidate, title_attr, "")) for candidate in candidates[:3]],
        }

    def _resolve_active_target(
        self,
        *,
        context: AssistantAgentContext,
        candidates: list[Any],
        title_attr: str,
    ) -> dict[str, Any]:
        active_target = (context.external_context or {}).get("active_target")
        if not isinstance(active_target, dict):
            return {"status": "not_found"}
        target_id = active_target.get("event_id") if title_attr == "title" else active_target.get("task_id")
        if target_id is None:
            return {"status": "not_found"}
        try:
            target_id_int = int(target_id)
        except (TypeError, ValueError):
            return {"status": "not_found"}
        matched = [candidate for candidate in candidates if getattr(candidate, "id", None) == target_id_int]
        if len(matched) != 1:
            return {"status": "not_found"}
        target = matched[0]
        return {
            "status": "unique",
            "target": target,
            "target_id": getattr(target, "id", None),
            "target_title": getattr(target, title_attr, None),
            "candidate_count": 1,
            "candidate_titles": [str(getattr(target, title_attr, ""))],
        }

    def _is_exact_target_mentioned(self, text: str, value: str | None) -> bool:
        if not value:
            return False
        target = str(value).strip()
        if not target:
            return False
        pattern = re.escape(target)
        if target[-1:].isdigit():
            pattern += r"(?!\d)"
        if target[:1].isdigit():
            pattern = r"(?<!\d)" + pattern
        return bool(re.search(pattern, text))

    def _is_exact_target_alias_mentioned(self, text: str, value: str) -> bool:
        compact = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", value)
        if len(compact) < 4:
            return False
        aliases = {compact}
        aliases.add(re.sub(r"^(?:处理|参加|安排|创建|新增|添加|开|做)", "", compact))
        aliases.add(re.sub(r"^去[\u4e00-\u9fa5A-Za-z0-9]{1,24}(?:参加|处理|开|做)", "", compact))
        for match in re.finditer(r"[\u4e00-\u9fa5A-Za-z]+[A-Za-z0-9]*\d+", compact):
            aliases.add(match.group(0))
        for alias in aliases:
            if len(alias) < 4:
                continue
            pattern = re.escape(alias)
            if alias[-1:].isdigit():
                pattern += r"(?!\d)"
            if re.search(pattern, text):
                return True
        return False

    def _extract_update_location_from_message(self, message: str) -> str | None:
        patterns = [
            r"(?:地点|位置|地方)\s*(?:改到|改成|改为|换到|换成|调整到|设为|是|为|到)?\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,24})",
            r"(?:改到|改成|改为|换到|换成|调整到)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,24})(?:上课|开会|见面|培训|办事|聚餐|体检|面试)?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, message):
                location = match.group("location").strip(" \t\r\n，。,；;：:")
                if not location:
                    continue
                if re.search(r"(?:\d{1,2}|[一二两三四五六七八九十两半]+)\s*(?:点|时)", location):
                    continue
                if re.search(r"^\d{1,2}\s*月\s*\d{1,2}\s*[日号]?$", location):
                    continue
                return location
        return None

    def _recent_history_text(self, history: list[Any]) -> str:
        chunks: list[str] = []
        for message in reversed(history[-6:]):
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            if content:
                chunks.append(str(content))
        return "\n".join(chunks)

    def _target_result(self, scored: list[tuple[int, Any]], *, title_attr: str) -> dict[str, Any]:
        if not scored:
            return {"status": "not_found", "candidate_count": 0, "candidate_titles": []}
        scored.sort(key=lambda item: item[0], reverse=True)
        scored = self._dedupe_scored_targets(scored)
        best_score = scored[0][0]
        best = [item for item in scored if item[0] == best_score]
        candidate_titles = [str(getattr(item[1], title_attr, "")) for item in scored[:3]]
        if len(best) != 1:
            return {
                "status": "ambiguous",
                "candidate_count": len(best),
                "candidate_titles": [str(getattr(item[1], title_attr, "")) for item in best[:3]],
            }
        target = best[0][1]
        return {
            "status": "unique",
            "target_id": getattr(target, "id", None),
            "target_title": getattr(target, title_attr, None),
            "candidate_count": len(scored),
            "candidate_titles": candidate_titles,
        }

    def _dedupe_scored_targets(self, scored: list[tuple[int, Any]]) -> list[tuple[int, Any]]:
        deduped: list[tuple[int, Any]] = []
        seen: set[Any] = set()
        for score, target in scored:
            key = getattr(target, "id", id(target))
            if key in seen:
                continue
            seen.add(key)
            deduped.append((score, target))
        return deduped

    def _extract_partial_start_time(
        self,
        message: str,
        *,
        reference: datetime | None = None,
        inherited_period_reference: datetime | None = None,
    ) -> datetime | None:
        reference_dt = reference or datetime.now()
        base_date = self.text_runtime._extract_target_date(message, reference_dt.date())
        inherited_period = "下午" if (inherited_period_reference or reference_dt).hour >= 12 else None
        token_match = TIME_TOKEN_PATTERN.search(message)
        if token_match:
            start_time, _period = self.text_runtime._parse_time_token(token_match.group(0), base_date)
            if start_time:
                if (inherited_period or reference_dt.hour >= 12) and start_time.hour < 12 and not re.search(
                    r"凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚",
                    token_match.group(0),
                ):
                    start_time = start_time.replace(hour=start_time.hour + 12)
                return start_time

        period_only_match = re.search(
            r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)",
            message,
        )
        if period_only_match:
            period = period_only_match.group("period")
            default_hour = {
                "凌晨": 2,
                "早上": 8,
                "上午": 9,
                "中午": 12,
                "下午": 15,
                "傍晚": 18,
                "晚上": 19,
                "今晚": 19,
                "今早": 8,
                "明早": 8,
                "明晚": 19,
            }.get(period)
            if default_hour is not None:
                return datetime.combine(base_date, datetime.min.time()).replace(hour=default_hour, minute=0)

        digit_match = re.search(
            r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)?\s*"
            r"(?P<hour>\d{1,2})\s*(?:点|时)(?P<minute>半|\d{1,2}分?)?",
            message,
        )
        if not digit_match:
            return None
        hour = int(digit_match.group("hour"))
        period = digit_match.group("period")
        minute_raw = digit_match.group("minute") or ""
        minute = 30 if minute_raw == "半" else int(minute_raw.replace("分", "") or 0)
        if period is None and inherited_period and 1 <= hour < 12:
            period = inherited_period
        elif period is None and reference_dt.hour >= 12 and 1 <= hour < 12:
            period = "下午"
        hour = self.text_runtime._apply_period(hour, period)
        return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)

    def _extract_broad_time_period(self, message: str) -> str | None:
        if re.search(r"\d{1,2}\s*(?:点|时)|\d{1,2}:\d{2}|[零〇一二两三四五六七八九十]{1,3}\s*(?:点|时)", message):
            return None
        period_match = re.search(r"凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚", message)
        if not period_match:
            return None
        period = period_match.group(0)
        mapping = {
            "早上": "morning",
            "上午": "morning",
            "今早": "morning",
            "明早": "morning",
            "中午": "noon",
            "下午": "afternoon",
            "傍晚": "evening",
            "晚上": "night",
            "今晚": "night",
            "明晚": "night",
            "凌晨": "late_night",
        }
        return mapping.get(period)

    def _clean_location(self, location_name: Any, message: str) -> str | None:
        if not isinstance(location_name, str):
            return None
        location = location_name.strip(" ，。,")
        if location == message.strip(" ，。,"):
            return None
        return location or None

    def _extract_event_location_from_message(self, message: str) -> str | None:
        patterns = [
            r"(?:在|于)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}?)(?=(?:和|跟|同).{0,8}(?:见面|碰头)|见面|碰头|上课|开会|开组会|会议|组会|培训|办|体检|面试|聚餐|接|送|[，。,；;!！?？])",
            r"(?:去|到|在|于)\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}?)(?=(?:和|跟|同).{0,8}(?:见面|碰头)|见面|碰头|上课|开会|开组会|会议|组会|培训|办|体检|面试|聚餐|接|送|[，。,；;!！?？])",
            r"(?:地点|位置|地方)\s*(?:在|是|为|到)?\s*(?P<location>[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,24})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, message):
                location = match.group("location").strip(" \t\r\n，。,；;：:")
                if re.search(r"(?:\d{1,2}|[一二两三四五六七八九十两半]+)\s*(?:点|时)", location):
                    continue
                if location and location != message.strip(" \t\r\n，。,；;：:"):
                    return location
        return None

    def _extract_event_title_from_message(self, *, message: str, location_name: str | None) -> str | None:
        if not location_name or location_name not in message:
            return None
        after_location = message.split(location_name, 1)[1]
        after_location = after_location.strip(" \t\r\n，。,；;：:！!?？")
        after_location = re.sub(r"^(?:和|跟|同)\s*", "和", after_location)
        if 2 <= len(after_location) <= 30 and re.search(r"见面|碰头|上课|开会|会议|组会|培训|办|体检|面试|聚餐", after_location):
            return after_location
        if 2 <= len(after_location) <= 30 and re.match(r"(?:接|送)[\u4e00-\u9fa5A-Za-z0-9·（）()]{1,24}$", after_location):
            return f"去{location_name}{after_location}"
        return f"去{location_name}"

    def _extract_explicit_arranged_event_title(self, message: str) -> str | None:
        patterns = [
            r"(?:安排|创建|新增|添加)\s*(?P<title>[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,40}?)(?=[，,。；;]\s*(?:时间|地点|位置)|\s*(?:时间|地点|位置)\s*(?:是|在|为)?|$)",
            r"(?:标题|名称)\s*(?:叫|是|为)?\s*(?P<title>[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,40})",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if not match:
                continue
            title = match.group("title").strip(" \t\r\n，。,；;：:")
            title = re.sub(r"^(?:一个|一条|这个|该)?", "", title).strip(" \t\r\n，。,；;：:")
            if title:
                return title[:40]
        return None

    def _extract_social_event_title(self, message: str) -> str | None:
        if re.search(r"约会", message):
            return "约会"
        if re.search(r"聚餐", message):
            return "聚餐"
        if re.search(r"见面|碰头", message):
            return "见面"
        return None

    def _clean_event_title(self, title: Any, *, message: str, location_name: str | None) -> str | None:
        if not isinstance(title, str):
            return None
        cleaned = title.strip(" \t\r\n，。,；;：:！!?？“”\"'")
        if not cleaned:
            return None
        if cleaned == "New event":
            return None
        if location_name and cleaned == location_name:
            return None
        if cleaned == message.strip(" ，。,"):
            return cleaned
        if re.fullmatch(r"(?:\d{1,2}|[一二两三四五六七八九十半])?点?我要", cleaned):
            return None
        if len(cleaned) > 40:
            return None
        return cleaned
