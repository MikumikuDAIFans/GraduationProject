"""Tests for the preference learner service."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.preference_learner import PreferenceLearner


def make_event(
    user_id="user-1",
    start_time=None,
    event_type="meeting",
    location="Office",
    status="completed",
    reschedule_count=0,
    title="Test Event",
):
    """Helper to create mock event objects."""
    if start_time is None:
        start_time = datetime(2026, 4, 1, 10, 0)
    return SimpleNamespace(
        user_id=user_id,
        start_time=start_time,
        event_type=event_type,
        location=location,
        status=status,
        reschedule_count=reschedule_count,
        title=title,
    )


def run_async(coro):
    """Helper to run async functions synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestPreferenceLearner:
    """Test preference learning from user history."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async database session."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        vs = MagicMock()
        vs.safe_add = MagicMock(return_value=True)
        return vs

    def test_analyze_time_patterns(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [
            make_event(start_time=datetime(2026, 4, d, 9, 0))
            for d in range(1, 8)
        ]
        result = learner._analyze_time_patterns(events)
        assert "weekday" in result
        assert "peak_hours" in result["weekday"]

    def test_analyze_location_patterns(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [
            make_event(location="Office"),
            make_event(location="Office"),
            make_event(location="Home"),
        ]
        result = learner._analyze_location_patterns(events)
        assert "frequent_locations" in result
        assert result["frequent_locations"]["Office"] == 2

    def test_analyze_task_acceptance_all_completed(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [make_event(status="completed") for _ in range(5)]
        result = learner._analyze_task_acceptance(events)
        assert result["completion_rate"] == 1.0
        assert result["cancellation_rate"] == 0.0

    def test_analyze_task_acceptance_mixed(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [
            make_event(status="completed"),
            make_event(status="cancelled"),
            make_event(status="completed"),
        ]
        result = learner._analyze_task_acceptance(events)
        assert result["completion_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert result["cancellation_rate"] == pytest.approx(1 / 3, abs=0.01)

    def test_analyze_task_acceptance_empty(self, mock_db):
        learner = PreferenceLearner(mock_db)
        result = learner._analyze_task_acceptance([])
        assert result["completion_rate"] == 0
        assert result["cancellation_rate"] == 0

    def test_analyze_conflict_resolutions_rigid(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [make_event(reschedule_count=0) for _ in range(10)]
        result = learner._analyze_conflict_resolutions(events)
        assert result["style"] == "rigid"

    def test_analyze_conflict_resolutions_flexible(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [make_event(reschedule_count=1) for _ in range(10)]
        result = learner._analyze_conflict_resolutions(events)
        assert result["style"] == "flexible"

    def test_estimate_energy_curve(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [
            make_event(start_time=datetime(2026, 4, 1, h, 0), status="completed")
            for h in range(8, 18)
        ]
        curve = learner._estimate_energy_curve(events)
        assert len(curve) == 24
        # Morning hours should have completion data
        assert curve[9] > 0

    def test_estimate_energy_curve_defaults_missing_hours(self, mock_db):
        learner = PreferenceLearner(mock_db)
        events = [make_event(start_time=datetime(2026, 4, 1, 10, 0))]
        curve = learner._estimate_energy_curve(events)
        # Hours without data should default to 0.5
        assert curve[3] == 0.5
        assert curve[23] == 0.5

    def test_learn_from_history_no_events(self, mock_db):
        learner = PreferenceLearner(mock_db)
        result = run_async(learner.learn_from_history("user-1", days=30))
        assert result == {}

    def test_learn_from_history_with_events(self, mock_db):
        events = [make_event(start_time=datetime(2026, 4, d, 9, 0)) for d in range(1, 8)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=mock_result)

        learner = PreferenceLearner(mock_db)
        result = run_async(learner.learn_from_history("user-1", days=30))
        assert "preferred_time_slots" in result
        assert "preferred_locations" in result
        assert "task_acceptance_rate" in result

    def test_learn_stores_preferences_with_vector_store(self, mock_db, mock_vector_store):
        events = [make_event(start_time=datetime(2026, 4, d, 9, 0)) for d in range(1, 8)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=mock_result)

        learner = PreferenceLearner(mock_db, vector_store=mock_vector_store)
        run_async(learner.learn_from_history("user-1", days=30))
        mock_vector_store.safe_add.assert_called()
