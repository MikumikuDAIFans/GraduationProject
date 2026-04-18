"""Tests for the smart task splitter service."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.task_splitter import (
    IdleSlot,
    SmartTaskSplitter,
    SplitStrategy,
    TaskSplitPlan,
)


def make_task(
    task_id: int = 1,
    estimated_duration_minutes: int = 60,
    deadline: datetime | None = None,
    priority: str = "normal",
    max_splits: int = 3,
    min_chunk_minutes: int | None = None,
    split_strategy: str | None = None,
    content: str = "Test task",
):
    """Helper to create mock task objects."""
    from types import SimpleNamespace
    return SimpleNamespace(
        id=task_id,
        estimated_duration_minutes=estimated_duration_minutes,
        deadline=deadline,
        priority=priority,
        max_splits=max_splits,
        min_chunk_minutes=min_chunk_minutes,
        split_strategy=split_strategy,
        content=content,
    )


class TestIdleSlot:
    """Test IdleSlot dataclass."""

    def test_create_idle_slot(self):
        slot = IdleSlot(
            start=datetime(2026, 4, 1, 10, 0),
            end=datetime(2026, 4, 1, 11, 0),
            duration_minutes=60,
        )
        assert slot.duration_minutes == 60
        assert slot.energy_level == "medium"

    def test_effective_minutes_with_buffer(self):
        slot = IdleSlot(
            start=datetime(2026, 4, 1, 10, 0),
            end=datetime(2026, 4, 1, 11, 0),
            duration_minutes=60,
        )
        # 5-minute buffer subtracted
        assert slot.effective_minutes == 55

    def test_effective_minutes_small_slot(self):
        slot = IdleSlot(
            start=datetime(2026, 4, 1, 10, 0),
            end=datetime(2026, 4, 1, 10, 3),
            duration_minutes=3,
        )
        # Below buffer, should return 0
        assert slot.effective_minutes == 0


class TestStrategyDetermination:
    """Test split strategy determination."""

    def test_default_strategy_is_equal(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task()
        strategy = splitter._determine_strategy(task)
        assert strategy.strategy_type == "equal"

    def test_uses_task_split_strategy_if_set(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task(split_strategy="priority_based")
        strategy = splitter._determine_strategy(task)
        assert strategy.strategy_type == "priority_based"

    def test_urgent_task_gets_priority_based(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        now = datetime.utcnow()
        task = make_task(deadline=now + timedelta(hours=12))
        strategy = splitter._determine_strategy(task)
        assert strategy.strategy_type == "priority_based"

    def test_user_pref_overrides_default(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task()
        prefs = {"default_split_strategy": "time_based"}
        strategy = splitter._determine_strategy(task, prefs)
        assert strategy.strategy_type == "time_based"

    def test_chunk_size_respects_task_minimum(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task(min_chunk_minutes=45)
        strategy = splitter._determine_strategy(task)
        assert strategy.chunk_size_minutes >= 45


class TestTaskContentAnalysis:
    """Test task content analysis for semantic splitting."""

    def test_analyze_with_chinese_delimiter(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        result = splitter._analyze_task_content("写报告 和 做演示", 2)
        assert len(result) == 2
        assert "写报告" in result
        assert "做演示" in result

    def test_analyze_with_comma(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        result = splitter._analyze_task_content("Research, Write, Review", 3)
        assert len(result) == 3

    def test_analyze_generates_numbered_parts(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        result = splitter._analyze_task_content("完成项目文档", 3)
        assert len(result) == 3
        assert "第1/3部分" in result[0]

    def test_analyze_empty_content(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        result = splitter._analyze_task_content("", 3)
        assert result == []

    def test_analyze_max_splits_1(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        result = splitter._analyze_task_content("Simple task", 1)
        assert result == []


class TestSlotSorting:
    """Test idle slot sorting by strategy."""

    def test_sort_by_default_earliest_first(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task()
        strategy = SplitStrategy()
        slots = [
            IdleSlot(start=datetime(2026, 4, 1, 14, 0), end=datetime(2026, 4, 1, 15, 0), duration_minutes=60),
            IdleSlot(start=datetime(2026, 4, 1, 10, 0), end=datetime(2026, 4, 1, 11, 0), duration_minutes=60),
        ]
        sorted_slots = splitter._sort_slots(slots, strategy, task)
        assert sorted_slots[0].start.hour == 10

    def test_sort_by_preferred_period_morning(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task()
        strategy = SplitStrategy(preferred_period="morning")
        slots = [
            IdleSlot(start=datetime(2026, 4, 1, 14, 0), end=datetime(2026, 4, 1, 15, 0), duration_minutes=60),
            IdleSlot(start=datetime(2026, 4, 1, 9, 0), end=datetime(2026, 4, 1, 10, 0), duration_minutes=60),
        ]
        sorted_slots = splitter._sort_slots(slots, strategy, task)
        assert sorted_slots[0].start.hour == 9


class TestSlotMatching:
    """Test matching task chunks to idle slots."""

    def test_match_chunks_to_slots(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task(estimated_duration_minutes=90, max_splits=3)
        strategy = SplitStrategy(chunk_size_minutes=30)
        slots = [
            IdleSlot(start=datetime(2026, 4, 1, 10, 0), end=datetime(2026, 4, 1, 11, 0), duration_minutes=60),
            IdleSlot(start=datetime(2026, 4, 1, 11, 0), end=datetime(2026, 4, 1, 12, 0), duration_minutes=60),
            IdleSlot(start=datetime(2026, 4, 1, 14, 0), end=datetime(2026, 4, 1, 15, 0), duration_minutes=60),
        ]
        plan = splitter._match_slots(task, strategy, slots)
        assert len(plan.splits) >= 1
        assert plan.task_id == 1
        assert plan.strategy_used == "equal"

    def test_no_suitable_slots(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task(estimated_duration_minutes=120, max_splits=3)
        strategy = SplitStrategy(chunk_size_minutes=60)
        slots = [
            IdleSlot(start=datetime(2026, 4, 1, 10, 0), end=datetime(2026, 4, 1, 10, 20), duration_minutes=20),
        ]
        plan = splitter._match_slots(task, strategy, slots)
        assert len(plan.splits) == 0
        assert plan.notes == "未找到合适的空闲时间段"

    def test_partial_coverage_note(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        task = make_task(estimated_duration_minutes=120, max_splits=3)
        strategy = SplitStrategy(chunk_size_minutes=30)
        slots = [
            IdleSlot(start=datetime(2026, 4, 1, 10, 0), end=datetime(2026, 4, 1, 10, 45), duration_minutes=45),
        ]
        plan = splitter._match_slots(task, strategy, slots)
        # Should note remaining time
        assert plan.notes is not None


class TestBlockedHours:
    """Test blocked hours filtering."""

    def test_is_in_blocked_hours_overnight(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        # 2 AM is within 22:00-07:00
        assert splitter._is_in_blocked_hours("2026-04-01T02:00:00", "22:00", "07:00") is True

    def test_is_not_in_blocked_hours_daytime(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        # 10 AM is outside 22:00-07:00
        assert splitter._is_in_blocked_hours("2026-04-01T10:00:00", "22:00", "07:00") is False

    def test_is_in_blocked_hours_daytime_range(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        assert splitter._is_in_blocked_hours("2026-04-01T14:00:00", "13:00", "15:00") is True

    def test_invalid_time_string_returns_false(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        assert splitter._is_in_blocked_hours("invalid", "22:00", "07:00") is False


class TestAdjustForPreferences:
    """Test preference-based plan adjustment."""

    def test_filter_blocked_hours(self):
        splitter = SmartTaskSplitter(db_session=MagicMock())
        plan = TaskSplitPlan(
            task_id=1,
            original_duration_minutes=90,
            splits=[
                {"task_id": 1, "split_order": 0, "scheduled_time": "2026-04-01T02:00:00", "duration_minutes": 30, "description": "Part 1", "status": "pending"},
                {"task_id": 1, "split_order": 1, "scheduled_time": "2026-04-01T10:00:00", "duration_minutes": 30, "description": "Part 2", "status": "pending"},
            ],
        )
        prefs = {"blocked_hours_start": "22:00", "blocked_hours_end": "07:00"}
        result = splitter._adjust_for_preferences(plan, prefs)
        # 2 AM split should be removed, 10 AM should remain
        assert len(result.splits) == 1
        assert result.splits[0]["scheduled_time"] == "2026-04-01T10:00:00"
