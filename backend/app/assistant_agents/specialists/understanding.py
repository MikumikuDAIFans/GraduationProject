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

        if intent == "create_event":
            understanding = self._understand_event(message, intent=intent, language=language)
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
        if self._looks_like_event(message):
            return "create_event"
        if self._looks_like_task(message):
            return "create_task"
        return self.text_runtime._classify_intent(message)

    def _looks_like_event(self, message: str) -> bool:
        if re.search(r"见面|碰头|集合|约会|聚餐|上课|开会|会议|组会|答辩|面试|appointment|meeting", message, re.I):
            return True
        if self._extract_partial_start_time(message) is not None and re.search(r"去|到|在|于|at|in|to", message, re.I):
            return True
        return False

    def _looks_like_task(self, message: str) -> bool:
        return bool(re.search(r"任务|待办|todo|deadline|截止|完成|复习|整理|准备|记得|提醒我", message, re.I))

    def _understand_event(self, message: str, *, intent: str, language: str) -> UnderstandingResult:
        payload = self.text_runtime._build_rule_based_event_payload(message)
        start_time, end_time = self.text_runtime._extract_time_range(message)
        start_time = start_time or self._extract_partial_start_time(message)
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

    def _extract_partial_start_time(self, message: str) -> datetime | None:
        base_date = self.text_runtime._extract_target_date(message, datetime.now().date())
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
