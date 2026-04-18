"""Tests for HabitRetriever service."""

import asyncio
from unittest.mock import MagicMock
from app.services.habit_retriever import HabitRetriever


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSuggestTime:
    def setup_method(self):
        self.mock_vs = MagicMock()
        self.retriever = HabitRetriever(self.mock_vs)

    def test_suggest_time_returns_top_match(self):
        self.mock_vs.query.return_value = {
            "ids": [["habit-1"]],
            "documents": [["Morning gym routine"]],
            "metadatas": [[{
                "activity": "gym",
                "time_pattern": "07:00",
                "confidence": 0.9,
                "type": "routine",
            }]],
            "distances": [[0.1]],
        }

        result = run_async(self.retriever.suggest_time("gym"))

        assert result is not None
        assert result["time_pattern"] == "07:00"
        assert result["confidence"] == 0.9
        assert result["activity"] == "gym"

    def test_suggest_time_filters_by_confidence(self):
        self.mock_vs.query.return_value = {
            "ids": [["habit-1", "habit-2"]],
            "documents": [["Low confidence habit", "High confidence habit"]],
            "metadatas": [[{
                "activity": "gym",
                "time_pattern": "07:00",
                "confidence": 0.5,  # Below threshold
                "type": "routine",
            }, {
                "activity": "gym",
                "time_pattern": "18:00",
                "confidence": 0.85,  # Above threshold
                "type": "routine",
            }]],
            "distances": [[0.5, 0.2]],
        }

        result = run_async(self.retriever.suggest_time("gym"))
        assert result is not None
        assert result["confidence"] == 0.85

    def test_suggest_time_no_results(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = run_async(self.retriever.suggest_time("unknown_activity"))
        assert result is None

    def test_suggest_time_vector_store_failure(self):
        self.mock_vs.query.side_effect = Exception("Connection error")

        result = run_async(self.retriever.suggest_time("gym"))
        assert result is None

    def test_suggest_time_with_user_filter(self):
        self.mock_vs.query.return_value = {
            "ids": [["habit-1"]],
            "documents": [["Personal habit"]],
            "metadatas": [[{
                "activity": "reading",
                "time_pattern": "21:00",
                "confidence": 0.8,
                "type": "routine",
                "user_id": "user-1",
            }]],
            "distances": [[0.15]],
        }

        result = run_async(self.retriever.suggest_time(
            "reading", user_id="user-1"
        ))
        assert result is not None
        # Verify query was called with user_id filter
        call_kwargs = self.mock_vs.query.call_args
        assert call_kwargs.kwargs.get("where", {}).get("user_id") == "user-1"

    def test_suggest_time_with_context(self):
        self.mock_vs.query.return_value = {
            "ids": [["habit-1"]],
            "documents": [["Cooking dinner"]],
            "metadatas": [[{
                "activity": "cooking",
                "time_pattern": "18:00",
                "confidence": 0.85,
                "type": "routine",
            }]],
            "distances": [[0.1]],
        }

        result = run_async(self.retriever.suggest_time(
            "cooking", context="dinner time"
        ))
        assert result is not None


class TestCheckPreference:
    def setup_method(self):
        self.mock_vs = MagicMock()
        self.retriever = HabitRetriever(self.mock_vs)

    def test_check_preference_finds_conflicts(self):
        self.mock_vs.query.return_value = {
            "ids": [["pref-1"]],
            "documents": [["No early meetings"]],
            "metadatas": [[{
                "description": "No meetings before 9am",
                "strength": 0.9,
                "category": "time",
                "polarity": "negative",
            }]],
            "distances": [[0.2]],
        }

        result = run_async(self.retriever.check_preference({
            "time": "07:00",
            "type": "meeting",
            "title": "Early standup",
        }))

        assert len(result) == 1
        assert result[0]["preference"] == "No meetings before 9am"
        assert result[0]["strength"] == 0.9

    def test_check_preference_below_strength_threshold(self):
        self.mock_vs.query.return_value = {
            "ids": [["pref-1"]],
            "documents": [["Weak preference"]],
            "metadatas": [[{
                "description": "Maybe no afternoon calls",
                "strength": 0.5,  # Below 0.7 threshold
                "category": "time",
                "polarity": "negative",
            }]],
            "distances": [[0.4]],
        }

        result = run_async(self.retriever.check_preference({
            "time": "14:00",
            "type": "call",
        }))
        assert len(result) == 0

    def test_check_preference_no_results(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = run_async(self.retriever.check_preference({
            "time": "10:00",
            "type": "meeting",
        }))
        assert result == []

    def test_check_preference_handles_exception(self):
        self.mock_vs.query.side_effect = Exception("DB error")

        result = run_async(self.retriever.check_preference({
            "time": "10:00",
        }))
        assert result == []

    def test_check_preference_with_user_filter(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        run_async(self.retriever.check_preference(
            {"time": "10:00"}, user_id="user-1"
        ))

        call_kwargs = self.mock_vs.query.call_args
        assert call_kwargs.kwargs.get("where", {}).get("user_id") == "user-1"


class TestGetSimilarExperience:
    def setup_method(self):
        self.mock_vs = MagicMock()
        self.retriever = HabitRetriever(self.mock_vs)

    def test_get_similar_experience_returns_results(self):
        self.mock_vs.query.return_value = {
            "ids": [["exp-1"]],
            "documents": [["Rescheduled meeting due to conflict"]],
            "metadatas": [[{
                "situation": "meeting conflict",
                "outcome": "rescheduled",
                "user_id": "user-1",
            }]],
            "distances": [[0.15]],
        }

        result = run_async(self.retriever.get_similar_experience(
            "meeting conflict", user_id="user-1"
        ))

        assert len(result) == 1
        assert result[0]["description"] == "Rescheduled meeting due to conflict"
        assert result[0]["metadata"]["outcome"] == "rescheduled"

    def test_get_similar_experience_no_results(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = run_async(self.retriever.get_similar_experience("unknown situation"))
        assert result == []

    def test_get_similar_experience_handles_exception(self):
        self.mock_vs.query.side_effect = Exception("Query failed")

        result = run_async(self.retriever.get_similar_experience("test"))
        assert result == []


class TestGetRelevantHabits:
    def setup_method(self):
        self.mock_vs = MagicMock()
        self.retriever = HabitRetriever(self.mock_vs)

    def test_get_relevant_habits_returns_all(self):
        self.mock_vs.query.return_value = {
            "ids": [["habit-1", "habit-2"]],
            "documents": [["Morning gym", "Evening reading"]],
            "metadatas": [[{
                "activity": "gym",
                "time_pattern": "07:00",
                "confidence": 0.9,
            }, {
                "activity": "reading",
                "time_pattern": "21:00",
                "confidence": 0.75,
            }]],
            "distances": [[0.1, 0.3]],
        }

        result = run_async(self.retriever.get_relevant_habits("exercise"))

        assert len(result) == 2
        assert result[0]["id"] == "habit-1"
        assert result[0]["distance"] == 0.1

    def test_get_relevant_habits_empty(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = run_async(self.retriever.get_relevant_habits("unknown"))
        assert result == []

    def test_get_relevant_habits_handles_exception(self):
        self.mock_vs.query.side_effect = Exception("Vector store down")

        result = run_async(self.retriever.get_relevant_habits("anything"))
        assert result == []

    def test_get_relevant_habits_with_user_filter(self):
        self.mock_vs.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        run_async(self.retriever.get_relevant_habits(
            "gym", user_id="user-1"
        ))

        call_kwargs = self.mock_vs.query.call_args
        assert call_kwargs.kwargs.get("where", {}).get("user_id") == "user-1"
