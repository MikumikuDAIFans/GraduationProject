"""Text parsing and rule-based planning helpers for the assistant runtime."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any


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

TIME_PERIOD_RAW = r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)"
TIME_TOKEN_RAW = (
    rf"{TIME_PERIOD_RAW}?\s*"
    r"(?:\d{1,2}(?::\d{2}|点半|点一刻|点三刻|点\d{1,2}分?|点|时半|时一刻|时三刻|时\d{1,2}分?|时)?|[零〇一二两三四五六七八九十]{1,3}(?:点半|点一刻|点三刻|点[零〇一二三四五六七八九十]{1,3}分?|点|时半|时一刻|时三刻|时[零〇一二三四五六七八九十]{1,3}分?|时))"
)
TIME_TOKEN_PATTERN = re.compile(TIME_TOKEN_RAW)
EXPLICIT_TIME_TOKEN_PATTERN = re.compile(
    rf"{TIME_PERIOD_RAW}?\s*"
    r"(?:\d{1,2}(?::\d{2}|点半|点一刻|点三刻|点\d{1,2}分?|点|时半|时一刻|时三刻|时\d{1,2}分?|时)|[零〇一二两三四五六七八九十]{1,3}(?:点半|点一刻|点三刻|点[零〇一二三四五六七八九十]{1,3}分?|点|时半|时一刻|时三刻|时[零〇一二三四五六七八九十]{1,3}分?|时))"
)


class AssistantTextRuntime:
    """Pure text parsing helpers used by the assistant runtime."""

    def _build_rule_based_event_payload(self, user_message: str) -> dict[str, Any]:
        start_time, end_time = self._extract_time_range(user_message)
        return {
            "title": "New event",
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "location_name": None,
            "description": None,
            "event_type": "general",
        }

    def _build_rule_based_task_payload(self, user_message: str) -> dict[str, Any]:
        deadline = self._extract_task_deadline(user_message)
        duration = self._extract_duration_minutes(user_message)
        preferred_period = self._extract_period_preference(user_message)
        can_split = bool(re.search(r"拆分|拆成|分成|分两次|分几次|分块", user_message))
        return {
            "content": None,
            "deadline": deadline.isoformat() if deadline else None,
            "estimated_duration_minutes": duration,
            "priority": 3,
            "can_split": can_split,
            "preferred_period": preferred_period,
        }

    def _classify_intent(self, user_message: str) -> str:
        has_time = self._extract_time_range(user_message)[0] is not None
        has_location_hint = bool(re.search(r"去|到|在|于|at|in|to", user_message, re.I))
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
        if asks_event_advice and (has_time or has_event_keyword or has_location_hint):
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

        relative_match = re.search(
            r"(?P<amount>\d+|[零〇一二两三四五六七八九十]{1,3})\s*个?\s*(?P<unit>分钟|分|小时|钟头|天|日)\s*后",
            user_message,
        )
        if relative_match:
            amount = self._parse_number(relative_match.group("amount"))
            unit = relative_match.group("unit")
            if amount is not None:
                if unit in {"分钟", "分"}:
                    start_dt = now + timedelta(minutes=amount)
                elif unit in {"天", "日"}:
                    start_dt = now + timedelta(days=amount)
                else:
                    start_dt = now + timedelta(hours=amount)
                if re.search(
                    r"提醒我|日程|会议|开会|组会|答辩|面试|约会|聚餐|上课|演示|汇报|看医生|去|到|在|于|meeting|event|appointment",
                    user_message,
                    re.I,
                ):
                    duration_minutes = (
                        self._extract_duration_minutes(user_message)
                        if re.search(r"持续|时长|预计|大概|约", user_message)
                        else None
                    )
                    return start_dt.replace(second=0, microsecond=0), (
                        start_dt + timedelta(minutes=duration_minutes or 60)
                    ).replace(second=0, microsecond=0)

        range_match = re.search(
            rf"({TIME_TOKEN_RAW})\s*(?:到|至|~|～|—|－|-)\s*({TIME_TOKEN_RAW})",
            user_message,
        )
        if range_match:
            start_dt, start_period = self._parse_time_token(range_match.group(1), base_date)
            end_dt, _ = self._parse_time_token(range_match.group(2), base_date, inherited_period=start_period)
            if start_dt and end_dt:
                end_dt = self._normalize_range_end(start_dt, end_dt)
                return start_dt, end_dt

        labeled_range_patterns = [
            rf"(?:从|由)?\s*({TIME_TOKEN_RAW})\s*(?:开始|起|出发)\s*(?:[，,、\s]*(?:到|至|一直到)?[，,、\s]*)({TIME_TOKEN_RAW})\s*(?:结束|截止|前|止)?",
            rf"(?:从|由)?\s*({TIME_TOKEN_RAW})\s*(?:[，,、\s]*(?:到|至|一直到)?[，,、\s]*)({TIME_TOKEN_RAW})\s*(?:结束|截止|前|止)",
            rf"(?:从|由)\s*({TIME_TOKEN_RAW})\s*(?:到|至|一直到)\s*({TIME_TOKEN_RAW})",
        ]
        for pattern in labeled_range_patterns:
            labeled_match = re.search(pattern, user_message)
            if not labeled_match:
                continue
            start_dt, start_period = self._parse_time_token(labeled_match.group(1), base_date)
            end_dt, _ = self._parse_time_token(labeled_match.group(2), base_date, inherited_period=start_period)
            if start_dt and end_dt:
                end_dt = self._normalize_range_end(start_dt, end_dt)
                return start_dt, end_dt

        token_match = EXPLICIT_TIME_TOKEN_PATTERN.search(user_message)
        if token_match:
            start_dt, _ = self._parse_time_token(token_match.group(0), base_date)
            if start_dt and re.search(r"日程|会议|开会|组会|答辩|面试|约会|聚餐|上课|演示|汇报|看医生|出发|去|到|在|于|meeting|event|appointment", user_message, re.I):
                duration_minutes = self._extract_duration_minutes(user_message)
                return start_dt, start_dt + timedelta(minutes=duration_minutes) if duration_minutes else None

        return None, None

    def _normalize_range_end(self, start_dt: datetime, end_dt: datetime) -> datetime:
        """Move an end time forward until it is after the start time."""
        while end_dt <= start_dt:
            end_dt += timedelta(hours=12)
        return end_dt

    def _extract_target_date(self, user_message: str, reference_date: date) -> date:
        if "大后天" in user_message:
            return reference_date + timedelta(days=3)
        if "后天" in user_message:
            return reference_date + timedelta(days=2)
        if "明天" in user_message or "明早" in user_message or "明晚" in user_message:
            return reference_date + timedelta(days=1)
        if "今天" in user_message or "今晚" in user_message or "今早" in user_message:
            return reference_date

        next_month_match = re.search(r"(?:下个?月|下月)(?:的)?(?P<day>\d{1,2}|[一二两三四五六七八九十]{1,3})[日号]?", user_message)
        if next_month_match:
            month = reference_date.month + 1
            year = reference_date.year
            if month > 12:
                month = 1
                year += 1
            day = self._parse_number(next_month_match.group("day")) or 1
            return date(year, month, day)

        explicit = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})月(\d{1,2})[日号]", user_message)
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
        return None

    def _normalize_event_title(self, *, current_title: str | None, user_message: str) -> str:
        if current_title and current_title.lower() not in {"new event", "event"}:
            return current_title
        return current_title or "New event"

    def _extract_event_title(self, user_message: str) -> str | None:
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
        message = user_message.strip()
        if not message:
            return None

        keyword_patterns = [
            r"(?:今天|明天|后天|大后天|这周|本周|下周)?(?:帮我|请|麻烦)?(?:安排一下|安排|规划一下|规划)?\s*(?P<content>(?:复习|学习|准备|整理)[\u4e00-\u9fa5A-Za-z0-9]{1,24})",
            r"(?:帮我|请|麻烦)?(?:安排一下|安排|规划一下|规划|提醒我|记得)?\s*(?P<content>[\u4e00-\u9fa5A-Za-z0-9]{1,24}(?:复习|整理|准备|论文|材料|作业|报告|任务|待办))",
            r"(?:完成|推进|处理)\s*(?P<content>[\u4e00-\u9fa5A-Za-z0-9]{1,24})",
        ]
        for pattern in keyword_patterns:
            match = re.search(pattern, message, re.I)
            if not match:
                continue
            content = self._clean_task_content(match.group("content"))
            if content:
                return content

        cleaned = re.sub(
            r"(帮我|请|麻烦|安排一下|安排|规划一下|规划|创建|新增|添加|给我|提醒我|记得|一下|任务|待办)",
            "",
            message,
        )
        cleaned = TIME_TOKEN_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"\d{1,2}:\d{2}", "", cleaned)
        cleaned = re.sub(r"(今天|明天|后天|大后天|今晚|明晚|上午|下午|晚上|早上|中午|这周|本周|下周)", "", cleaned)
        cleaned = re.sub(r"(之前|前|截止|deadline|due|每天|隔天|集中|分成|拆成|分块).*$", "", cleaned, flags=re.I)
        return self._clean_task_content(cleaned)

    def _clean_task_content(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip(" \t\r\n，。,；;：:！!?？“”\"'")
        cleaned = re.sub(r"^(一下|一个|这个|那个|的)", "", cleaned)
        cleaned = re.sub(r"(一下|这个任务|这个待办)$", "", cleaned)
        cleaned = cleaned.strip(" \t\r\n，。,；;：:！!?？“”\"'")
        return cleaned[:40] if cleaned else None

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
        return []

    def _select_schedule_guidance_dates(self, user_message: str) -> list[date]:
        reference = datetime.now().date()
        if re.search(r"这周|本周|下周|周[一二三四五六日天末]|星期[一二三四五六日天末]", user_message):
            start_date = self._extract_target_date(user_message, reference)
            return [start_date + timedelta(days=offset) for offset in range(0, 3)]
        return [self._extract_target_date(user_message, reference)]

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
