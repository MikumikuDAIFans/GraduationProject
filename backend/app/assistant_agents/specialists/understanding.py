"""Understanding specialist for structured message interpretation."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState, UnderstandingResult
from app.services.assistant_runtime_text import AssistantTextRuntime, TIME_TOKEN_PATTERN


class UnderstandingSpecialist:
    name = "understanding"

    def __init__(self, text_runtime: AssistantTextRuntime | None = None) -> None:
        self.text_runtime = text_runtime or AssistantTextRuntime()

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        message = context.user_message.strip()
        intent = self._classify(message)
        language = "zh" if self.text_runtime._prefers_chinese(message) else "en"

        if intent in {"reschedule_event", "cancel_event", "mark_event_completed", "mark_task_completed"}:
            understanding = self._understand_update(message, intent=intent, language=language, context=context)
        elif intent == "create_event":
            understanding = self._understand_event(message, intent=intent, language=language, context=context)
        elif intent == "create_task":
            understanding = self._understand_task(message, intent=intent, language=language)
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
            )

        state.understanding = understanding
        return state

    def _classify(self, message: str) -> str:
        update_intent = self._classify_update_intent(message)
        if update_intent:
            return update_intent
        if self._looks_like_event(message):
            return "create_event"
        if self._looks_like_task(message):
            return "create_task"
        return self.text_runtime._classify_intent(message)

    def _classify_update_intent(self, message: str) -> str | None:
        if re.search(r"改到|改成|调整到|挪到|推迟到|提前到|延期到|reschedule|move", message, re.I):
            return "reschedule_event"
        if re.search(r"取消|不去了|不用去了|删掉|删除|cancel", message, re.I):
            return "cancel_event"
        if re.search(r"完成了|做完了|已完成|标记.*完成|打卡|done|completed", message, re.I):
            if re.search(r"任务|待办|todo", message, re.I):
                return "mark_task_completed"
            return "mark_event_completed"
        return None

    def _looks_like_event(self, message: str) -> bool:
        if re.search(r"见面|碰头|集合|约会|聚餐|上课|开会|会议|组会|答辩|面试|appointment|meeting", message, re.I):
            return True
        if self._extract_partial_start_time(message) is not None and re.search(r"去|到|在|于|at|in|to", message, re.I):
            return True
        return False

    def _looks_like_task(self, message: str) -> bool:
        return bool(re.search(r"任务|待办|todo|deadline|截止|完成|复习|整理|准备|记得|提醒我", message, re.I))

    def _understand_event(
        self,
        message: str,
        *,
        intent: str,
        language: str,
        context: AssistantAgentContext,
    ) -> UnderstandingResult:
        payload = self.text_runtime._build_rule_based_event_payload(message)
        start_time, end_time = self.text_runtime._extract_time_range(message, reference=context.now)
        start_time = start_time or self._extract_partial_start_time(message, reference=context.now)
        location_name = self._clean_location(self.text_runtime._extract_location(message), message)
        title = self._extract_event_title(message, location_name=location_name) or payload.get("title")
        if title == "New event":
            title = None

        slots: dict[str, Any] = {
            "title": title,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "location_name": location_name,
        }
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

        if title and start_time and location_name and missing_fields == ["end_time_or_duration"]:
            can_propose = True
            assumptions.append("default_event_duration_60_minutes")
        elif title and start_time and end_time:
            can_propose = True
            requires_clarification = False
        elif not start_time:
            ambiguities.append("event_time_window_too_broad")
        elif not location_name and re.search(r"去|到|在", message):
            ambiguities.append("location_unclear")

        if re.fullmatch(r".{0,6}(我要|想)?去?约会[。！!？?]?", message):
            can_propose = False
            requires_clarification = True
            missing_fields = ["intent_detail", "start_time", "location_name", "end_time_or_duration"]
            ambiguities.append("dating_request_too_vague")

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
        )

    def _understand_task(self, message: str, *, intent: str, language: str) -> UnderstandingResult:
        payload = self.text_runtime._build_rule_based_task_payload(message)
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
        )

    def _understand_update(
        self,
        message: str,
        *,
        intent: str,
        language: str,
        context: AssistantAgentContext,
    ) -> UnderstandingResult:
        if intent == "mark_task_completed":
            target = self._resolve_task_target(message, context.tasks)
            return self._update_understanding_from_target(
                intent=intent,
                goal_type="task",
                target=target,
                language=language,
            )

        target = self._resolve_event_target(message, context.events)
        missing_fields: list[str] = []
        ambiguities: list[str] = []
        slots: dict[str, Any] = {
            "action_type": intent,
            "target_kind": "event",
            "target_id": target.get("target_id"),
            "target_title": target.get("target_title"),
            "candidate_count": target.get("candidate_count"),
            "candidate_titles": target.get("candidate_titles", []),
        }

        if target.get("status") == "not_found":
            missing_fields.append("target_event")
            ambiguities.append("target_event_not_found")
        elif target.get("status") == "ambiguous":
            missing_fields.append("target_event")
            ambiguities.append("target_event_ambiguous")

        if intent == "reschedule_event":
            start_time, end_time = self.text_runtime._extract_time_range(message, reference=context.now)
            start_time = start_time or self._extract_partial_start_time(message, reference=context.now)
            slots["new_start_time"] = start_time.isoformat() if start_time else None
            slots["new_end_time"] = end_time.isoformat() if end_time else None
            if not start_time:
                missing_fields.append("new_start_time")
                ambiguities.append("reschedule_time_missing")

        can_propose = target.get("status") == "unique" and not missing_fields
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
        )

    def _update_understanding_from_target(
        self,
        *,
        intent: str,
        goal_type: str,
        target: dict[str, Any],
        language: str,
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
        )

    def _resolve_event_target(self, message: str, events: list[Any]) -> dict[str, Any]:
        active_events = [event for event in events if (getattr(event, "status", None) or "planned") != "canceled"]
        scored = []
        for event in active_events:
            score = self._score_event_target(message, event)
            if score > 0:
                scored.append((score, event))
        return self._target_result(scored, title_attr="title")

    def _resolve_task_target(self, message: str, tasks: list[Any]) -> dict[str, Any]:
        active_tasks = [task for task in tasks if (getattr(task, "status", None) or "pending") not in {"done", "canceled", "archived"}]
        scored = []
        for task in active_tasks:
            score = self._score_text_target(message, getattr(task, "content", None))
            if score > 0:
                scored.append((score, task))
        return self._target_result(scored, title_attr="content")

    def _score_event_target(self, message: str, event: Any) -> int:
        score = self._score_text_target(message, getattr(event, "title", None))
        score += self._score_text_target(message, getattr(event, "location_name", None))
        start_time = getattr(event, "start_time", None)
        if start_time is not None and hasattr(start_time, "hour"):
            hour = int(start_time.hour)
            if re.search(rf"{hour}\s*(点|时)", message):
                score += 4
            if hour >= 12 and "下午" in message:
                score += 1
            if hour < 12 and ("上午" in message or "早上" in message):
                score += 1
        return score

    def _score_text_target(self, message: str, value: str | None) -> int:
        if not value:
            return 0
        text = str(value).strip()
        if not text:
            return 0
        if text in message:
            return 8
        score = 0
        for token in self._target_tokens(text):
            if token in message:
                score += min(len(token), 4)
        return score

    def _target_tokens(self, text: str) -> list[str]:
        tokens = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text)
        if re.search(r"[\u4e00-\u9fa5]", text):
            compact = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
            for size in range(2, min(len(compact), 4) + 1):
                tokens.extend(compact[index : index + size] for index in range(0, len(compact) - size + 1))
        if len(text) >= 2:
            tokens.append(text)
        return list(dict.fromkeys(tokens))

    def _target_result(self, scored: list[tuple[int, Any]], *, title_attr: str) -> dict[str, Any]:
        if not scored:
            return {"status": "not_found", "candidate_count": 0, "candidate_titles": []}
        scored.sort(key=lambda item: item[0], reverse=True)
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

    def _extract_partial_start_time(self, message: str, *, reference: datetime | None = None) -> datetime | None:
        base_date = self.text_runtime._extract_target_date(message, (reference or datetime.now()).date())
        token_match = TIME_TOKEN_PATTERN.search(message)
        if token_match:
            start_time, _period = self.text_runtime._parse_time_token(token_match.group(0), base_date)
            if start_time:
                return start_time

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
        hour = self.text_runtime._apply_period(hour, period)
        return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)

    def _clean_location(self, location_name: str | None, message: str) -> str | None:
        if not location_name:
            return None
        location = location_name.strip(" ，。,")
        if "见面" in message and "和" in location:
            location = location.split("和", 1)[0].strip()
        return location or None

    def _extract_event_title(self, message: str, *, location_name: str | None) -> str | None:
        explicit = self.text_runtime._extract_event_title(message)
        if explicit:
            return explicit
        if "见面" in message:
            person_match = re.search(r"和(?P<person>[\u4e00-\u9fa5A-Za-z0-9]{1,12})见面", message)
            if person_match:
                return f"和{person_match.group('person')}见面"
            return "见面"
        if "约会" in message:
            return "约会"
        topic = self.text_runtime._extract_event_topic(message)
        if topic and topic != location_name:
            return topic
        return None
