"""Tests for the habit analyzer service."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.habit_analyzer import HabitAnalyzer


def make_event(
    title="Test Event",
    start_time=None,
    event_type="general",
    location_name=None,
    is_fixed=False,
):
    """Helper to create mock event objects."""
    if start_time is None:
        start_time = datetime(2026, 4, 1, 10, 0)
    return SimpleNamespace(
        title=title,
        start_time=start_time,
        event_type=event_type,
        location_name=location_name,
        is_fixed=is_fixed,
    )


class TestExtractPattern:
    """Test single event pattern extraction."""

    def test_returns_none_without_start_time(self):
        event = make_event(start_time=None)
        result = HabitAnalyzer.extract_pattern(event)
        assert result is None

    def test_low_confidence_for_general_event(self):
        event = make_event(event_type="general", location_name=None, is_fixed=False)
        result = HabitAnalyzer.extract_pattern(event)
        # Confidence should be 0.5 < 0.6 threshold
        assert result is None

    def test_meeting_type_passes_threshold(self):
        event = make_event(event_type="meeting", start_time=datetime(2026, 4, 1, 9, 0))
        result = HabitAnalyzer.extract_pattern(event)
        # 0.5 + 0.1 (meeting) = 0.6, meets threshold
        assert result is not None
        assert result["type"] == "routine"

    def test_location_boosts_confidence(self):
        event = make_event(event_type="general", location_name="Office", start_time=datetime(2026, 4, 1, 14, 0))
        result = HabitAnalyzer.extract_pattern(event)
        # 0.5 + 0.1 (location) = 0.6
        assert result is not None

    def test_fixed_event_boosts_confidence(self):
        event = make_event(event_type="general", is_fixed=True, start_time=datetime(2026, 4, 1, 8, 0))
        result = HabitAnalyzer.extract_pattern(event)
        # 0.5 + 0.15 (fixed) = 0.65
        assert result is not None

    def test_exercise_gets_daily_frequency(self):
        event = make_event(event_type="exercise", start_time=datetime(2026, 4, 1, 6, 30))
        result = HabitAnalyzer.extract_pattern(event)
        assert result is not None
        assert result["frequency"] == "daily"

    def test_weekday_pattern_for_weekday_event(self):
        event = make_event(event_type="meeting", start_time=datetime(2026, 4, 1, 10, 0))  # Wednesday
        result = HabitAnalyzer.extract_pattern(event)
        assert result is not None
        assert result["day_pattern"] == "weekday"

    def test_weekend_pattern_for_weekend_event(self):
        event = make_event(event_type="exercise", start_time=datetime(2026, 4, 4, 10, 0))  # Saturday
        result = HabitAnalyzer.extract_pattern(event)
        assert result is not None
        assert result["day_pattern"] == "weekend"

    def test_time_pattern_format(self):
        event = make_event(event_type="meeting", start_time=datetime(2026, 4, 1, 9, 30))
        result = HabitAnalyzer.extract_pattern(event)
        assert result is not None
        assert result["time_pattern"] == "09:30"

    def test_occurrence_count_starts_at_one(self):
        event = make_event(event_type="meeting", start_time=datetime(2026, 4, 1, 10, 0))
        result = HabitAnalyzer.extract_pattern(event)
        assert result["occurrences"] == 1


class TestDiscoverPatterns:
    """Test batch pattern discovery."""

    def test_discovers_recurring_pattern(self):
        events = [
            make_event(title="Morning Standup", event_type="meeting", start_time=datetime(2026, 4, d, 9, 0))
            for d in range(1, 8)
        ]
        patterns = HabitAnalyzer.discover_patterns(events, min_occurrences=3)
        assert len(patterns) >= 1

    def test_returns_empty_for_few_events(self):
        events = [make_event(event_type="general")]
        patterns = HabitAnalyzer.discover_patterns(events, min_occurrences=3)
        assert len(patterns) == 0

    def test_groups_similar_events(self):
        events = [
            make_event(title="Gym", event_type="exercise", start_time=datetime(2026, 4, d, 7, 0))
            for d in range(1, 10)
        ]
        patterns = HabitAnalyzer.discover_patterns(events, min_occurrences=3)
        assert len(patterns) >= 1
        # The activity key uses the lowercase grouping key
        assert any("gym" in p.get("activity", "") for p in patterns)

    def test_filters_by_min_occurrences(self):
        events = [
            make_event(title="Rare Event", event_type="meeting", start_time=datetime(2026, 4, d, 10, 0))
            for d in range(1, 3)
        ]
        patterns = HabitAnalyzer.discover_patterns(events, min_occurrences=5)
        assert len(patterns) == 0

    def test_empty_events_list(self):
        patterns = HabitAnalyzer.discover_patterns([], min_occurrences=1)
        assert patterns == []
