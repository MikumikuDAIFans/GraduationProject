"""
Smart Task Splitting Service.

Intelligently splits tasks into sub-tasks based on:
1. Estimated duration vs available idle slots
2. User's historical splitting preferences
3. Deadline pressure
4. Task content analysis (LLM-assisted when available)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskSplit, Event, UserProfile


@dataclass
class IdleSlot:
    """Represents an available time slot between scheduled events."""
    start: datetime
    end: datetime
    duration_minutes: int
    energy_level: str = "medium"  # high/medium/low, inferred from surrounding events

    @property
    def effective_minutes(self) -> int:
        """Return usable minutes after accounting for transition overhead."""
        # Assume 5-minute buffer for context switching
        return max(0, self.duration_minutes - 5)


@dataclass
class SplitStrategy:
    """Strategy for how a task should be split."""
    strategy_type: str = "equal"  # equal/priority_based/time_based/semantic
    chunk_size_minutes: int = 30
    subtask_descriptions: list[str] = field(default_factory=list)
    requires_continuity: bool = False  # Whether sub-tasks should be consecutive
    preferred_period: str | None = None  # morning/afternoon/evening


@dataclass
class TaskSplitPlan:
    """A complete split plan for a task."""
    task_id: int
    original_duration_minutes: int
    splits: list[dict[str, Any]] = field(default_factory=list)
    completion_ratio: float = 0.0
    strategy_used: str = "equal"
    notes: str | None = None


class SmartTaskSplitter:
    """
    Intelligent task splitting service.
    
    Analyzes tasks and available idle slots to produce optimal split plans
    that respect user preferences, deadlines, and scheduling constraints.
    """

    # Default minimum chunk sizes by strategy
    MIN_CHUNK_BY_STRATEGY = {
        "equal": 15,
        "priority_based": 20,
        "time_based": 25,
        "semantic": 30,
    }

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def suggest_splits(
        self,
        task: Task,
        available_slots: list[IdleSlot],
        user_prefs: dict[str, Any] | None = None,
    ) -> TaskSplitPlan:
        """
        Generate intelligent split suggestions for a task.
        
        Args:
            task: The task to split
            available_slots: Available idle time slots
            user_prefs: Optional user preference overrides
            
        Returns:
            TaskSplitPlan with suggested splits
        """
        # 1. Determine split strategy
        strategy = self._determine_strategy(task, user_prefs)
        
        # 2. Sort slots by strategy preference
        sorted_slots = self._sort_slots(available_slots, strategy, task)
        
        # 3. Match task chunks to slots
        plan = self._match_slots(task, strategy, sorted_slots)
        
        # 4. Adjust for user preferences
        if user_prefs:
            plan = self._adjust_for_preferences(plan, user_prefs)
        
        return plan

    def _determine_strategy(
        self, task: Task, user_prefs: dict[str, Any] | None = None
    ) -> SplitStrategy:
        """Determine the best split strategy for a task."""
        prefs = user_prefs or {}
        
        # Use task's own strategy if set
        if task.split_strategy:
            strategy_type = task.split_strategy
        elif prefs.get("default_split_strategy"):
            strategy_type = prefs["default_split_strategy"]
        elif task.deadline and self._is_urgent(task):
            strategy_type = "priority_based"
        else:
            strategy_type = "equal"
        
        # Determine chunk size
        min_chunk = task.min_chunk_minutes or self.MIN_CHUNK_BY_STRATEGY.get(
            strategy_type, 15
        )
        chunk_size = max(min_chunk, 15)
        
        # Analyze task content for semantic hints
        descriptions = self._analyze_task_content(task.content, task.max_splits)
        
        return SplitStrategy(
            strategy_type=strategy_type,
            chunk_size_minutes=chunk_size,
            subtask_descriptions=descriptions,
            requires_continuity=prefs.get("prefer_consecutive_splits", False),
            preferred_period=prefs.get("preferred_work_period"),
        )

    def _analyze_task_content(self, content: str, max_splits: int) -> list[str]:
        """
        Analyze task content to generate meaningful sub-task descriptions.
        
        In a full implementation, this would call an LLM to semantically
        decompose the task. For now, uses heuristic keyword extraction.
        """
        if not content or max_splits <= 1:
            return []
        
        # Simple heuristic: split on common delimiters
        parts = []
        for delimiter in ["和", "以及", ",", ";", "、", "\n"]:
            if delimiter in content:
                parts = [p.strip() for p in content.split(delimiter) if p.strip()]
                if len(parts) >= 2:
                    break
        
        # If no natural splits found, generate numbered descriptions
        if len(parts) < 2:
            parts = [
                f"{content}（第{i + 1}/{max_splits}部分）"
                for i in range(min(max_splits, 3))
            ]
        
        return parts[:max_splits]

    def _is_urgent(self, task: Task) -> bool:
        """Check if a task is approaching its deadline."""
        if not task.deadline:
            return False
        deadline = task.deadline
        if isinstance(deadline, str):
            deadline = datetime.fromisoformat(deadline)
        now = datetime.now(timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return (deadline - now).total_seconds() < 86400  # 24 hours

    def _sort_slots(
        self,
        slots: list[IdleSlot],
        strategy: SplitStrategy,
        task: Task,
    ) -> list[IdleSlot]:
        """Sort idle slots based on strategy and task context."""
        if strategy.preferred_period:
            period_order = {"morning": 0, "afternoon": 1, "evening": 2}
            target = period_order.get(strategy.preferred_period, 1)
            
            def period_score(slot: IdleSlot) -> int:
                hour = slot.start.hour
                if 6 <= hour < 12:
                    return abs(period_order["morning"] - target)
                elif 12 <= hour < 18:
                    return abs(period_order["afternoon"] - target)
                else:
                    return abs(period_order["evening"] - target)
            
            return sorted(slots, key=lambda s: (period_score(s), s.start))
        
        # Default: earliest slots first
        return sorted(slots, key=lambda s: s.start)

    def _match_slots(
        self,
        task: Task,
        strategy: SplitStrategy,
        sorted_slots: list[IdleSlot],
    ) -> TaskSplitPlan:
        """Match task chunks to available idle slots."""
        remaining_minutes = task.estimated_duration_minutes or 0
        max_splits = task.max_splits or 3
        splits = []
        split_order = 0
        
        for slot in sorted_slots:
            if remaining_minutes <= 0 or split_order >= max_splits:
                break
            
            effective = slot.effective_minutes
            if effective < strategy.chunk_size_minutes:
                continue  # Slot too small to be useful
            
            # Calculate chunk size for this slot
            chunk_minutes = min(effective, remaining_minutes)
            
            # Respect minimum chunk size
            if chunk_minutes < strategy.chunk_size_minutes:
                if not splits:  # Only skip if we haven't found any slot yet
                    continue
                break  # We have some splits already, stop looking
            
            description = (
                strategy.subtask_descriptions[split_order]
                if split_order < len(strategy.subtask_descriptions)
                else task.content
            )
            
            splits.append({
                "task_id": task.id,
                "split_order": split_order,
                "scheduled_time": slot.start.isoformat(),
                "duration_minutes": chunk_minutes,
                "description": description,
                "status": "pending",
                "slot_energy": slot.energy_level,
            })
            
            remaining_minutes -= chunk_minutes
            split_order += 1
        
        total_original = task.estimated_duration_minutes or 1
        completed_minutes = total_original - remaining_minutes
        
        return TaskSplitPlan(
            task_id=task.id,
            original_duration_minutes=total_original,
            splits=splits,
            completion_ratio=completed_minutes / total_original,
            strategy_used=strategy.strategy_type,
            notes=self._generate_notes(splits, total_original),
        )

    def _generate_notes(self, splits: list[dict], total_minutes: int) -> str | None:
        """Generate human-readable notes about the split plan."""
        if not splits:
            return "未找到合适的空闲时间段"
        
        scheduled_minutes = sum(s["duration_minutes"] for s in splits)
        if scheduled_minutes < total_minutes:
            remaining = total_minutes - scheduled_minutes
            return f"已安排 {scheduled_minutes} 分钟，剩余 {remaining} 分钟需另行安排"
        
        return None

    def _adjust_for_preferences(
        self, plan: TaskSplitPlan, prefs: dict[str, Any]
    ) -> TaskSplitPlan:
        """Adjust split plan based on user preferences."""
        # Filter out slots during user's blocked hours
        blocked_start = prefs.get("blocked_hours_start")  # e.g., "22:00"
        blocked_end = prefs.get("blocked_hours_end")  # e.g., "07:00"
        
        if blocked_start and blocked_end:
            plan.splits = [
                s for s in plan.splits
                if not self._is_in_blocked_hours(s["scheduled_time"], blocked_start, blocked_end)
            ]
            # Recalculate completion ratio
            if plan.original_duration_minutes > 0:
                scheduled = sum(s["duration_minutes"] for s in plan.splits)
                plan.completion_ratio = scheduled / plan.original_duration_minutes
        
        return plan

    def _is_in_blocked_hours(
        self, time_str: str, blocked_start: str, blocked_end: str
    ) -> bool:
        """Check if a time falls within blocked hours."""
        try:
            dt = datetime.fromisoformat(time_str)
            hour = dt.hour
            start_h = int(blocked_start.split(":")[0])
            end_h = int(blocked_end.split(":")[0])
            
            if start_h > end_h:  # Overnight block (e.g., 22:00 - 07:00)
                return hour >= start_h or hour < end_h
            else:
                return start_h <= hour < end_h
        except (ValueError, IndexError):
            return False

    async def apply_splits(self, plan: TaskSplitPlan) -> list[TaskSplit]:
        """
        Apply a split plan by creating TaskSplit records in the database.
        
        Args:
            plan: The split plan to apply
            
        Returns:
            List of created TaskSplit records
        """
        created = []
        for split_data in plan.splits:
            ts = TaskSplit(
                id=str(uuid.uuid4()),
                task_id=split_data["task_id"],
                split_order=split_data["split_order"],
                scheduled_time=datetime.fromisoformat(split_data["scheduled_time"]),
                duration_minutes=split_data["duration_minutes"],
                description=split_data.get("description"),
                status=split_data.get("status", "pending"),
            )
            self.db.add(ts)
            created.append(ts)
        
        await self.db.flush()
        return created

    async def get_idle_slots(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
        min_duration: int = 15,
    ) -> list[IdleSlot]:
        """
        Find idle time slots between scheduled events.
        
        Args:
            user_id: The user to find slots for
            start: Start of the search window
            end: End of the search window
            min_duration: Minimum slot duration in minutes
            
        Returns:
            List of IdleSlot objects
        """
        # Get all events in the time window
        result = await self.db.execute(
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.end_time <= end,
                Event.status != "cancelled",
            )
            .order_by(Event.start_time)
        )
        events = list(result.scalars().all())
        
        # Get user's wake/sleep times from profile
        user_result = await self.db.execute(
            select(UserProfile).where(UserProfile.username == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        wake_hour = 8
        sleep_hour = 23
        if user:
            if user.wake_up_time:
                try:
                    wake_hour = int(user.wake_up_time.split(":")[0])
                except (ValueError, AttributeError):
                    pass
            if user.sleep_time:
                try:
                    sleep_hour = int(user.sleep_time.split(":")[0])
                except (ValueError, AttributeError):
                    pass
        
        slots = []
        current = start
        
        # Iterate through each day in the range
        day = start.date()
        end_day = end.date()
        while day <= end_day:
            day_start = datetime(day.year, day.month, day.day, wake_hour, 0)
            day_end = datetime(day.year, day.month, day.day, sleep_hour, 0)
            
            # Get events for this day
            day_events = [
                e for e in events
                if e.start_time and e.start_time.date() == day
            ]
            day_events.sort(key=lambda e: e.start_time or datetime.min)
            
            # Find gaps between events
            cursor = max(day_start, current if current.date() == day else day_start)
            
            for event in day_events:
                if not event.start_time or not event.end_time:
                    continue
                    
                gap_start = max(cursor, event.end_time)
                gap_end = event.start_time
                
                if gap_start < gap_end:
                    duration = int((gap_end - gap_start).total_seconds() / 60)
                    if duration >= min_duration:
                        energy = self._infer_energy_level(gap_start, wake_hour, sleep_hour)
                        slots.append(IdleSlot(
                            start=gap_start,
                            end=gap_end,
                            duration_minutes=duration,
                            energy_level=energy,
                        ))
                
                cursor = max(cursor, event.end_time)
            
            # Check gap after last event until end of day
            if cursor < day_end:
                duration = int((day_end - cursor).total_seconds() / 60)
                if duration >= min_duration:
                    energy = self._infer_energy_level(cursor, wake_hour, sleep_hour)
                    slots.append(IdleSlot(
                        start=cursor,
                        end=day_end,
                        duration_minutes=duration,
                        energy_level=energy,
                    ))
            
            current = day_end
            day = day + timedelta(days=1)
        
        return slots

    def _infer_energy_level(
        self, slot_time: datetime, wake_hour: int, sleep_hour: int
    ) -> str:
        """Infer energy level based on time of day."""
        hour = slot_time.hour
        midday = (wake_hour + sleep_hour) // 2
        
        if wake_hour <= hour < midday - 1:
            return "high"
        elif midday - 1 <= hour < midday + 2:
            return "medium"
        elif midday + 2 <= hour < sleep_hour:
            return "medium"
        else:
            return "low"
