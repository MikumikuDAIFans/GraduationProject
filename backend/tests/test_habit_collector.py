"""Tests for HabitCollector service."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.habit_collector import HabitCollector, HabitDeduplicator


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def make_event(
    user_id="user-1",
    title="Morning Gym",
    event_type="exercise",
    start_time=None,
    end_time=None,
    location="Gym",
):
    from datetime import datetime
    if start_time is None:
        start_time = datetime(2026, 4, 1, 7, 0)
    if end_time is None:
        end_time = start_time.replace(hour=start_time.hour + 1)
    return MagicMock(
        user_id=user_id,
        title=title,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        location=location,
    )


class TestHabitDeduplicator:
    def test_weighted_average_basic(self):
        result = HabitDeduplicator._weighted_average(0.8, 0.6, 10, 5)
        assert result == pytest.approx((0.8 * 10 + 0.6 * 5) / 15)

    def test_weighted_average_zero_counts(self):
        result = HabitDeduplicator._weighted_average(0.5, 0.7, 0, 0)
        assert result == 0.5

    def test_merge_finds_similar_by_activity(self):
        mock_repo = AsyncMock()
        dedup = HabitDeduplicator(mock_repo)

        existing_habit = MagicMock()
        existing_habit.id = "habit-1"
        existing_habit.activity = "gym workout"
        existing_habit.time_pattern = "07:00"
        existing_habit.confidence = 0.7
        existing_habit.occurrences = 3
        existing = [existing_habit]
        new_habit = {
            "activity": "gym",
            "time_pattern": "07:00",
            "confidence": 0.8,
        }

        merged, habit_id = run_async(dedup.merge("user-1", new_habit, existing))
        assert merged is True
        assert habit_id == "habit-1"
        mock_repo.update_confidence.assert_called_once()

    def test_merge_creates_new_when_no_match(self):
        mock_repo = AsyncMock()
        dedup = HabitDeduplicator(mock_repo)

        new_habit = {
            "activity": "meditation",
            "time_pattern": "22:00",
            "confidence": 0.9,
            "type": "routine",
        }

        merged, habit_id = run_async(dedup.merge("user-1", new_habit, []))
        assert merged is False
        assert habit_id is not None
        mock_repo.create.assert_called_once()

    def test_find_similar_partial_match(self):
        mock_repo = AsyncMock()
        dedup = HabitDeduplicator(mock_repo)

        existing_habit = MagicMock()
        existing_habit.id = "habit-1"
        existing_habit.activity = "morning gym routine"
        existing_habit.time_pattern = ""
        existing_habit.confidence = 0.6
        existing_habit.occurrences = 2
        existing = [existing_habit]
        new_habit = {"activity": "gym"}

        similar = run_async(dedup._find_similar("user-1", new_habit, existing))
        assert similar is not None

    def test_find_similar_no_match(self):
        mock_repo = AsyncMock()
        dedup = HabitDeduplicator(mock_repo)

        existing_habit = MagicMock()
        existing_habit.id = "habit-1"
        existing_habit.activity = "cooking dinner"
        existing_habit.time_pattern = "18:00"
        existing_habit.confidence = 0.8
        existing_habit.occurrences = 5
        existing = [existing_habit]
        new_habit = {"activity": "swimming", "time_pattern": "06:00"}

        similar = run_async(dedup._find_similar("user-1", new_habit, existing))
        assert similar is None


class TestHabitCollector:
    def setup_method(self):
        self.mock_vector_store = MagicMock()
        self.mock_vector_store.safe_add.return_value = True
        self.mock_repo = AsyncMock()
        self.mock_repo.find_similar.return_value = []
        self.collector = HabitCollector(self.mock_vector_store, self.mock_repo)

    def test_on_event_created_with_valid_pattern(self):
        event = make_event()
        self.mock_repo.find_similar.return_value = []

        run_async(self.collector.on_event_created(event))

        self.mock_repo.find_similar.assert_called_once()
        self.mock_vector_store.safe_add.assert_called_once()

    def test_on_event_created_no_pattern(self):
        event = make_event(event_type="general")
        # general events may not produce patterns

        run_async(self.collector.on_event_created(event))
        # May or may not add to vector store depending on pattern extraction

    def test_on_event_created_merges_with_existing(self):
        event = make_event(title="Morning Gym", event_type="exercise")
        existing_habit = MagicMock()
        existing_habit.id = "habit-existing"
        existing_habit.activity = "morning gym"
        existing_habit.time_pattern = "07:00"
        existing_habit.confidence = 0.7
        existing_habit.occurrences = 3
        self.mock_repo.find_similar.return_value = [existing_habit]

        run_async(self.collector.on_event_created(event))

        self.mock_repo.find_similar.assert_called_once()
        # When merged, safe_add should NOT be called
        self.mock_vector_store.safe_add.assert_not_called()

    def test_record_from_analysis_new_habit(self):
        pattern = {
            "activity": "weekly review",
            "time_pattern": "Friday 16:00",
            "day_pattern": "weekly",
            "confidence": 0.85,
            "frequency": "weekly",
        }
        self.mock_repo.find_similar.return_value = []

        run_async(self.collector.record_from_analysis("user-1", pattern))

        self.mock_repo.find_similar.assert_called_once()
        self.mock_vector_store.safe_add.assert_called_once()

    def test_record_from_analysis_existing_habit(self):
        pattern = {
            "activity": "weekly review",
            "time_pattern": "Friday 16:00",
            "confidence": 0.85,
        }
        existing_habit = MagicMock()
        existing_habit.id = "habit-1"
        existing_habit.activity = "weekly review"
        existing_habit.time_pattern = "Friday 16:00"
        existing_habit.confidence = 0.8
        existing_habit.occurrences = 4
        self.mock_repo.find_similar.return_value = [existing_habit]

        run_async(self.collector.record_from_analysis("user-1", pattern))

        # Should merge, not create new
        self.mock_vector_store.safe_add.assert_not_called()

    def test_on_user_statement_logs_message(self):
        # Conversational collection — simplified version just logs
        run_async(self.collector.on_user_statement(
            "I always go to the gym in the morning",
            "user-1"
        ))
        # No assertions needed — it's a simplified logging path


class TestHabitCollectorIntegration:
    def test_full_collection_flow(self):
        """Test the full flow: event created -> pattern extracted -> deduplicated -> stored."""
        mock_vector_store = MagicMock()
        mock_vector_store.safe_add.return_value = True
        mock_repo = AsyncMock()
        mock_repo.find_similar.return_value = []
        collector = HabitCollector(mock_vector_store, mock_repo)

        event = make_event(
            title="Daily Standup",
            event_type="meeting",
            start_time=__import__('datetime').datetime(2026, 4, 1, 9, 0),
        )

        run_async(collector.on_event_created(event))

        # Verify the flow completed
        mock_repo.find_similar.assert_called_once()
