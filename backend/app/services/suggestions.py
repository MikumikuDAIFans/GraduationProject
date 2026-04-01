"""Suggestion service for rule-based scheduling recommendations."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.api.schemas import SuggestionList, SuggestionRead
from app.db.session import get_sessionmaker
from app.repositories.events import EventRepository
from app.repositories.profiles import UserProfileRepository
from app.repositories.tasks import TaskRepository
from app.services.context import ContextService
from app.tools.maps import MapsClient


class SuggestionService:
    """Build scheduling suggestions from tasks, profile preferences, and calendar gaps."""

    def __init__(self) -> None:
        session_factory = get_sessionmaker()
        self.event_repository = EventRepository(session_factory)
        self.profile_repository = UserProfileRepository(session_factory)
        self.task_repository = TaskRepository(session_factory)
        self.context_service = ContextService()
        self.maps_client = MapsClient()

    async def get_today_suggestions(self, user_id: str) -> SuggestionList:
        target_date = datetime.now().date()
        items = await self._build_suggestions_for_dates(user_id=user_id, dates=[target_date], limit=5)
        return SuggestionList(items=items, total=len(items))

    async def get_next_suggestions(self, user_id: str) -> SuggestionList:
        today = datetime.now().date()
        dates = [today + timedelta(days=offset) for offset in range(1, 4)]
        items = await self._build_suggestions_for_dates(user_id=user_id, dates=dates, limit=8)
        return SuggestionList(items=items, total=len(items))

    async def build_suggestions_for_dates(
        self,
        *,
        user_id: str,
        dates: list[date],
        limit: int,
        related_task_ids: list[int] | None = None,
    ) -> list[SuggestionRead]:
        return await self._build_suggestions_for_dates(
            user_id=user_id,
            dates=dates,
            limit=limit,
            related_task_ids=related_task_ids,
        )

    async def _build_suggestions_for_dates(
        self,
        *,
        user_id: str,
        dates: list[date],
        limit: int,
        related_task_ids: list[int] | None = None,
    ) -> list[SuggestionRead]:
        events = await self.event_repository.list_events(user_id=user_id)
        profile = await self.profile_repository.get_profile(user_id)
        tasks = await self.task_repository.list_tasks(user_id=user_id)
        task_progress = self._task_progress_map(events=events)
        pending_tasks = [task for task in tasks if (task.status or "pending") != "done"]
        if related_task_ids:
            pending_tasks = [task for task in pending_tasks if task.id in related_task_ids]
        pending_tasks.sort(
            key=lambda task: (
                -(task_progress.get(task.id, {}).get("canceled_blocks_count", 0)),
                -(task_progress.get(task.id, {}).get("completed_blocks_count", 0)),
                -(task.priority or 0),
                task.deadline or datetime.max,
                task.id,
            )
        )

        suggestions: list[SuggestionRead] = []
        suggestions.extend(await self._build_context_suggestions(events=events, profile=profile, dates=dates))
        task_suggestions = self._build_task_slot_suggestions(
            events=events,
            profile=profile,
            tasks=pending_tasks,
            task_progress=task_progress,
            dates=dates,
            limit=max(limit - len(suggestions), 0),
        )
        suggestions.extend(task_suggestions)
        suggestions.sort(key=lambda item: item.start_time)
        return suggestions[:limit]

    def _build_task_slot_suggestions(self, *, events, profile, tasks, task_progress: dict[int, dict[str, int]] | None = None, dates: list[date], limit: int) -> list[SuggestionRead]:
        if limit <= 0:
            return []
        task_progress = task_progress or {}

        available_slots: list[tuple[datetime, datetime]] = []
        for target_date in dates:
            available_slots.extend(self._compute_gaps_for_date(events=events, profile=profile, target_date=target_date))

        suggestions: list[SuggestionRead] = []
        focus_block_minutes = self._focus_block_minutes(profile)

        for task in tasks:
            if len(suggestions) >= limit:
                break

            progress = task_progress.get(task.id, {})
            estimated_duration = task.estimated_duration_minutes or 60
            completed_minutes = progress.get("completed_minutes", 0)
            duration_minutes = max(estimated_duration - completed_minutes, 30)
            suggestion_type, suggestion_title_prefix = self._task_suggestion_identity(task=task, progress=progress)
            matching_slots = [
                adjusted
                for start, end in available_slots
                if (adjusted := self._adjust_slot_for_preference(task.preferred_period, start, end)) is not None
            ]
            if not matching_slots:
                matching_slots = available_slots

            if not matching_slots:
                continue

            if task.can_split:
                split_items = self._build_split_task_suggestions(
                    task=task,
                    duration_minutes=duration_minutes,
                    focus_block_minutes=focus_block_minutes,
                    slots=matching_slots,
                    remaining_limit=limit - len(suggestions),
                    suggestion_type=suggestion_type,
                    suggestion_title_prefix=suggestion_title_prefix,
                )
                if split_items:
                    suggestions.extend(split_items)
                    available_slots = self._consume_slots(available_slots, split_items)
                    continue

            single_item = self._build_single_task_suggestion(
                task=task,
                duration_minutes=duration_minutes,
                slots=matching_slots,
                suggestion_type=suggestion_type,
                suggestion_title_prefix=suggestion_title_prefix,
            )
            if single_item is None:
                continue

            suggestions.append(single_item)
            available_slots = self._consume_slots(available_slots, [single_item])

        return suggestions

    def _build_single_task_suggestion(
        self,
        *,
        task,
        duration_minutes: int,
        slots: list[tuple[datetime, datetime]],
        suggestion_type: str = "task_slot",
        suggestion_title_prefix: str = "Suggested slot for",
    ) -> SuggestionRead | None:
        for gap_start, gap_end in slots:
            suggestion_end = gap_start + timedelta(minutes=duration_minutes)
            if suggestion_end > gap_end:
                continue
            return SuggestionRead(
                type=suggestion_type,
                title=f"{suggestion_title_prefix} {task.content}",
                description=(
                    f"Use this free slot for task '{task.content}'. "
                    f"Priority={task.priority or 0}, duration={duration_minutes} minutes."
                ),
                start_time=gap_start,
                end_time=suggestion_end,
                related_task_id=task.id,
                confidence=0.72,
                estimated_minutes=duration_minutes,
            )
        return None

    def _build_split_task_suggestions(
        self,
        *,
        task,
        duration_minutes: int,
        focus_block_minutes: int,
        slots: list[tuple[datetime, datetime]],
        remaining_limit: int,
        suggestion_type: str = "task_split_slot",
        suggestion_title_prefix: str = "Split",
    ) -> list[SuggestionRead]:
        if remaining_limit <= 1:
            return []

        remaining = duration_minutes
        segments: list[SuggestionRead] = []
        split_group = f"task-{task.id}-split"

        for gap_start, gap_end in slots:
            cursor = gap_start
            while cursor < gap_end and remaining > 0 and len(segments) < remaining_limit:
                slot_minutes = int((gap_end - cursor).total_seconds() // 60)
                if slot_minutes < 30:
                    break

                segment_minutes = min(remaining, focus_block_minutes, slot_minutes)
                if segment_minutes < 30:
                    break

                segment_end = cursor + timedelta(minutes=segment_minutes)
                segments.append(
                    SuggestionRead(
                        type=suggestion_type,
                        title=f"{suggestion_title_prefix} {task.content}",
                        description=(
                            f"Break '{task.content}' into focused chunks. "
                            f"This segment covers {segment_minutes} minutes out of {duration_minutes}."
                        ),
                        start_time=cursor,
                        end_time=segment_end,
                        related_task_id=task.id,
                        confidence=0.76,
                        split_group=split_group,
                        estimated_minutes=segment_minutes,
                    )
                )
                remaining -= segment_minutes
                cursor = segment_end
                if remaining > 0 and (gap_end - cursor) >= timedelta(minutes=35):
                    cursor += timedelta(minutes=5)
            if remaining <= 0 or len(segments) >= remaining_limit:
                break

        if remaining > 0 or len(segments) < 2:
            return []

        total = len(segments)
        for index, item in enumerate(segments, start=1):
            item.segment_index = index
            item.segment_total = total
            item.description += f" Segment {index}/{total}."

        return segments

    def _consume_slots(self, slots: list[tuple[datetime, datetime]], suggestions: list[SuggestionRead]) -> list[tuple[datetime, datetime]]:
        result = list(slots)
        for suggestion in suggestions:
            updated: list[tuple[datetime, datetime]] = []
            for slot_start, slot_end in result:
                if suggestion.end_time <= slot_start or suggestion.start_time >= slot_end:
                    updated.append((slot_start, slot_end))
                    continue
                if suggestion.start_time > slot_start:
                    updated.append((slot_start, suggestion.start_time))
                if suggestion.end_time < slot_end:
                    updated.append((suggestion.end_time, slot_end))
            result = updated
        result.sort(key=lambda item: item[0])
        return result

    def _compute_gaps_for_date(self, *, events, profile=None, target_date: date) -> list[tuple[datetime, datetime]]:
        working_start, working_end = self._working_window_for_date(profile=profile, target_date=target_date)
        day_events = sorted(
            [
                event for event in events
                if event.start_time is not None
                and event.end_time is not None
                and event.start_time.date() == target_date
            ],
            key=lambda item: item.start_time,
        )

        gaps: list[tuple[datetime, datetime]] = []
        cursor = working_start
        for event in day_events:
            buffer_before = getattr(event, "buffer_before", None) or 0
            buffer_after = getattr(event, "buffer_after", None) or 0
            effective_start = event.start_time - timedelta(minutes=buffer_before)
            effective_end = event.end_time + timedelta(minutes=buffer_after)
            if effective_start > cursor:
                gaps.append((cursor, effective_start))
            cursor = max(cursor, effective_end)

        if cursor < working_end:
            gaps.append((cursor, working_end))
        return gaps

    async def _build_context_suggestions(self, *, events, profile, dates: list[date]) -> list[SuggestionRead]:
        suggestions: list[SuggestionRead] = []
        today = datetime.now()

        for event in events:
            if event.start_time is None or event.end_time is None:
                continue
            if event.start_time.date() not in dates:
                continue

            if event.departure_time is not None and event.travel_duration_minutes:
                suggestions.append(
                    SuggestionRead(
                        type="departure_plan",
                        title=f"Leave for {event.title}",
                        description=(
                            f"Planned departure at {event.departure_time.isoformat()} "
                            f"for {event.location_name or 'the destination'}, travel {event.travel_duration_minutes} minutes."
                        ),
                        start_time=event.departure_time,
                        end_time=event.start_time,
                        related_event_id=event.id,
                        confidence=0.84,
                        estimated_minutes=event.travel_duration_minutes,
                    )
                )

        if profile.home_location_coords and dates and dates[0] == today.date():
            try:
                weather = await self.context_service.weather_now(location=profile.home_location_coords)
                suggestions.append(
                    SuggestionRead(
                        type="weather_watch",
                        title="Current weather check",
                        description=(
                            f"{weather.text}, {weather.temp}°C, humidity {weather.humidity}%. "
                            "Use this as a quick condition check before leaving."
                        ),
                        start_time=today,
                        end_time=today + timedelta(minutes=30),
                        confidence=0.63,
                        estimated_minutes=30,
                    )
                )
                suggestions.extend(
                    self._build_weather_risk_suggestions(
                        events=events,
                        dates=dates,
                        weather=weather,
                        now=today,
                    )
                )
            except Exception:
                pass

        suggestions.extend(
            await self._build_location_break_suggestions(
                events=events,
                profile=profile,
                dates=dates,
            )
        )

        return suggestions

    async def _build_location_break_suggestions(self, *, events, profile, dates: list[date]) -> list[SuggestionRead]:
        if not dates:
            return []
        location = self._parse_coords(getattr(profile, "home_location_coords", None))
        if location is None:
            return []
        if not self.maps_client.enabled:
            return []

        target_date = dates[0]
        gaps = self._compute_gaps_for_date(events=events, profile=profile, target_date=target_date)
        long_gaps = [gap for gap in gaps if int((gap[1] - gap[0]).total_seconds() // 60) >= 45]
        if not long_gaps:
            return []

        try:
            pois = await self.maps_client.search_poi(keyword="咖啡厅", location=location, radius=2000)
        except Exception:
            return []
        if not pois:
            return []

        gap_start, gap_end = long_gaps[0]
        poi = pois[0]
        return [
            SuggestionRead(
                type="location_based_break",
                title=f"Nearby break option: {poi.get('name') or 'Recommended spot'}",
                description=(
                    f"Take a break during {gap_start.isoformat()} - {gap_end.isoformat()}. "
                    f"Nearby option: {poi.get('address') or poi.get('name')}. Distance {poi.get('distance') or 'unknown'}."
                ),
                start_time=gap_start,
                end_time=min(gap_start + timedelta(minutes=30), gap_end),
                confidence=0.58,
                estimated_minutes=30,
            )
        ]

    def _build_weather_risk_suggestions(self, *, events, dates: list[date], weather, now: datetime) -> list[SuggestionRead]:
        if not dates:
            return []
        weather_text = (getattr(weather, "text", "") or "").lower()
        risk_terms = ("rain", "storm", "snow", "shower", "thunder", "暴雨", "雷", "雪", "雨")
        if not any(term in weather_text for term in risk_terms):
            return []

        target_dates = set(dates)
        suggestions: list[SuggestionRead] = []
        for event in events:
            if event.start_time is None or event.end_time is None:
                continue
            if event.start_time.date() not in target_dates:
                continue
            if not self._is_outdoor_event(event):
                continue
            suggestions.append(
                SuggestionRead(
                    type="weather_alert",
                    title=f"Weather risk for {event.title}",
                    description=(
                        f"Current weather is {getattr(weather, 'text', 'changing')}. "
                        "Consider bringing an umbrella or adjusting the time and location."
                    ),
                    start_time=max(now, event.start_time - timedelta(minutes=30)),
                    end_time=event.start_time,
                    related_event_id=event.id,
                    confidence=0.68,
                    estimated_minutes=30,
                )
            )
        return suggestions[:2]

    def _parse_coords(self, raw_value: str | None) -> tuple[float, float] | None:
        if not raw_value or "," not in raw_value:
            return None
        try:
            lng, lat = raw_value.split(",", 1)
            return float(lat), float(lng)
        except ValueError:
            return None

    def _is_outdoor_event(self, event) -> bool:
        title = (getattr(event, "title", "") or "").lower()
        location_name = (getattr(event, "location_name", "") or "").lower()
        keywords = ("park", "outdoor", "run", "walk", "campus", "field", "公园", "操场", "户外", "球场", "广场")
        return any(keyword in title or keyword in location_name for keyword in keywords)

    def _working_window_for_date(self, *, profile, target_date: date) -> tuple[datetime, datetime]:
        wake_time = self._parse_profile_time(getattr(profile, "wake_up_time", None), fallback=time(hour=8))
        sleep_time = self._parse_profile_time(getattr(profile, "sleep_time", None), fallback=time(hour=22))
        start_dt = datetime.combine(target_date, wake_time)
        end_dt = datetime.combine(target_date, sleep_time)
        if end_dt <= start_dt:
            end_dt = datetime.combine(target_date, time(hour=22))
        return start_dt, end_dt

    def _parse_profile_time(self, raw_value: str | None, *, fallback: time) -> time:
        if not raw_value:
            return fallback
        try:
            parsed = datetime.strptime(raw_value, "%H:%M")
            return parsed.time()
        except ValueError:
            return fallback

    def _slot_matches_preference(self, preference: str | None, slot_start: datetime, slot_end: datetime) -> bool:
        return self._adjust_slot_for_preference(preference, slot_start, slot_end) is not None

    def _adjust_slot_for_preference(
        self,
        preference: str | None,
        slot_start: datetime,
        slot_end: datetime,
    ) -> tuple[datetime, datetime] | None:
        if preference == "morning":
            adjusted_end = min(slot_end, datetime.combine(slot_start.date(), time(hour=12)))
            return (slot_start, adjusted_end) if adjusted_end > slot_start else None
        if preference == "afternoon":
            adjusted_start = max(slot_start, datetime.combine(slot_start.date(), time(hour=12)))
            adjusted_end = min(slot_end, datetime.combine(slot_start.date(), time(hour=18)))
            return (adjusted_start, adjusted_end) if adjusted_end > adjusted_start else None
        if preference == "evening":
            adjusted_start = max(slot_start, datetime.combine(slot_start.date(), time(hour=18)))
            return (adjusted_start, slot_end) if slot_end > adjusted_start else None
        return (slot_start, slot_end)

    def _focus_block_minutes(self, profile) -> int:
        preferences = getattr(profile, "preferences_json", None) or {}
        raw_value = preferences.get("focus_block_minutes")
        if isinstance(raw_value, int) and raw_value >= 30:
            return raw_value
        return 60

    def _task_progress_map(self, *, events) -> dict[int, dict[str, int]]:
        progress: dict[int, dict[str, int]] = {}
        for event in events:
            task_id = getattr(event, "linked_task_id", None)
            if task_id is None or event.start_time is None or event.end_time is None:
                continue
            duration_minutes = int((event.end_time - event.start_time).total_seconds() // 60)
            task_progress = progress.setdefault(
                task_id,
                {
                    "scheduled_minutes": 0,
                    "completed_minutes": 0,
                    "completed_blocks_count": 0,
                    "canceled_blocks_count": 0,
                },
            )
            status = getattr(event, "status", None) or "planned"
            if status != "canceled":
                task_progress["scheduled_minutes"] += duration_minutes
            if status == "completed":
                task_progress["completed_minutes"] += duration_minutes
                task_progress["completed_blocks_count"] += 1
            if status == "canceled":
                task_progress["canceled_blocks_count"] += 1
        return progress

    def _task_suggestion_identity(self, *, task, progress: dict[str, int]) -> tuple[str, str]:
        if progress.get("canceled_blocks_count", 0) > 0:
            return "task_replan_slot", "Replan"
        if progress.get("completed_blocks_count", 0) > 0:
            return "task_resume_slot", "Resume"
        if task.can_split:
            return "task_split_slot", "Split"
        return "task_slot", "Suggested slot for"
