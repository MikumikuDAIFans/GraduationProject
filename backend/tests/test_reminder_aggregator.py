"""Tests for the reminder aggregator service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from app.services.reminder_aggregator import Reminder, ReminderAggregator


def make_reminder(
    reminder_id: int,
    message: str,
    remind_at: datetime,
    priority: str = "normal",
    user_id: str = "user-1",
    target_id: int | None = None,
):
    """Helper to create mock reminder objects."""
    return Reminder(
        id=reminder_id,
        user_id=user_id,
        target_type="event",
        target_id=target_id or reminder_id,
        message=message,
        remind_at=remind_at,
        priority=priority,
    )


def run_async(coro):
    """Helper to run async functions synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestDNDPeriod:
    """Test do-not-disturb period checks."""

    def test_reminder_during_dnd_suppressed(self):
        agg = ReminderAggregator()
        night = datetime(2026, 4, 1, 2, 0)  # 2 AM
        reminder = make_reminder(1, "Late night reminder", night)
        assert agg._is_in_dnd_period(reminder.remind_at) is True

    def test_reminder_outside_dnd_allowed(self):
        agg = ReminderAggregator()
        day = datetime(2026, 4, 1, 10, 0)  # 10 AM
        reminder = make_reminder(1, "Daytime reminder", day)
        assert agg._is_in_dnd_period(reminder.remind_at) is False

    def test_dnd_start_boundary(self):
        agg = ReminderAggregator()
        boundary = datetime(2026, 4, 1, 23, 0)
        assert agg._is_in_dnd_period(boundary) is True

    def test_dnd_end_boundary(self):
        agg = ReminderAggregator()
        end = datetime(2026, 4, 1, 7, 0)
        assert agg._is_in_dnd_period(end) is True

    def test_just_after_dnd_ends(self):
        agg = ReminderAggregator()
        after = datetime(2026, 4, 1, 7, 1)
        assert agg._is_in_dnd_period(after) is False


class TestCooldown:
    """Test cooldown period logic."""

    def test_first_reminder_not_in_cooldown(self):
        agg = ReminderAggregator()
        assert agg._is_in_cooldown(1) is False

    def test_reminder_within_cooldown(self):
        agg = ReminderAggregator()
        import datetime as dt
        agg.last_sent[1] = dt.datetime.utcnow()
        # Immediately check - should be in cooldown
        assert agg._is_in_cooldown(1) is True

    def test_reminder_after_cooldown_expired(self):
        agg = ReminderAggregator()
        import datetime as dt
        # Set last_sent to 20 minutes ago (past 15-min cooldown)
        agg.last_sent[1] = dt.datetime.utcnow() - dt.timedelta(minutes=20)
        assert agg._is_in_cooldown(1) is False


class TestAggregation:
    """Test reminder aggregation."""

    def test_single_reminder_unchanged(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        reminders = [make_reminder(1, "Single reminder", now)]
        result = run_async(agg.aggregate_reminders(reminders))
        assert len(result) == 1
        assert result[0].message == "Single reminder"

    def test_close_reminders_merged(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        reminders = [
            make_reminder(1, "Meeting A", now),
            make_reminder(2, "Meeting B", now + timedelta(minutes=10)),
            make_reminder(3, "Meeting C", now + timedelta(minutes=20)),
        ]
        result = run_async(agg.aggregate_reminders(reminders))
        # All within 30-min window, should be merged
        assert len(result) == 1
        assert "3 条" in result[0].message

    def test_far_reminders_separate(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        reminders = [
            make_reminder(1, "Morning meeting", now),
            make_reminder(2, "Afternoon meeting", now + timedelta(hours=4)),
        ]
        result = run_async(agg.aggregate_reminders(reminders))
        assert len(result) == 2

    def test_empty_list(self):
        agg = ReminderAggregator()
        result = run_async(agg.aggregate_reminders([]))
        assert result == []


class TestMergeBatch:
    """Test batch merging logic."""

    def test_merge_single_reminder(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        reminder = make_reminder(1, "Solo reminder", now)
        merged = agg._merge_batch([reminder])
        assert "1 条" in merged.message

    def test_merge_preserves_highest_priority(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        batch = [
            make_reminder(1, "Normal", now, priority="normal"),
            make_reminder(2, "Urgent", now + timedelta(minutes=5), priority="urgent"),
        ]
        merged = agg._merge_batch(batch)
        assert merged.priority == "urgent"

    def test_merge_collects_target_ids(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        batch = [
            make_reminder(1, "A", now, target_id=10),
            make_reminder(2, "B", now + timedelta(minutes=5), target_id=20),
        ]
        merged = agg._merge_batch(batch)
        assert merged.target_type == "batch"
        assert 10 in merged.target_ids
        assert 20 in merged.target_ids


class TestShouldSendReminder:
    """Test the should_send_reminder decision logic."""

    def test_allowed_outside_dnd(self):
        agg = ReminderAggregator()
        now = datetime(2026, 4, 1, 10, 0)
        reminder = make_reminder(1, "OK to send", now)
        assert run_async(agg.should_send_reminder(reminder)) is True

    def test_blocked_during_dnd(self):
        agg = ReminderAggregator()
        night = datetime(2026, 4, 1, 2, 0)
        reminder = make_reminder(1, "DND blocked", night)
        assert run_async(agg.should_send_reminder(reminder)) is False
