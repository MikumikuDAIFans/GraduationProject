from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.jobs.reminders import (
    _build_departure_reminder_payload,
    _build_event_start_reminder_payload,
    cleanup_old_reminders,
    scan_conflict_warnings,
    scan_departure_reminders,
    scan_idle_slot_risks,
    scan_upcoming_reminders,
)


def test_build_event_start_reminder_payload() -> None:
    now = datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc)
    event = SimpleNamespace(
        id=9,
        title="Defense rehearsal",
        start_time=now + timedelta(hours=2),
    )

    payload = _build_event_start_reminder_payload(event=event, now=now)

    assert payload["target_type"] == "event"
    assert payload["target_id"] == 9
    assert payload["remind_type"] == "event_start"
    assert payload["remind_at"] == now + timedelta(hours=1, minutes=30)


def test_build_event_start_reminder_payload_with_naive_datetime() -> None:
    now = datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc)
    event = SimpleNamespace(
        id=10,
        title="Defense rehearsal",
        start_time=datetime(2026, 3, 26, 11, 0),
    )

    payload = _build_event_start_reminder_payload(event=event, now=now)

    assert payload["remind_at"] == datetime(2026, 3, 26, 10, 30, tzinfo=timezone.utc)


def test_build_departure_reminder_payload() -> None:
    now = datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc)
    event = SimpleNamespace(
        id=11,
        title="Defense rehearsal",
        departure_time=now + timedelta(minutes=25),
    )

    payload = _build_departure_reminder_payload(event=event, now=now)

    assert payload["remind_type"] == "departure"
    assert payload["target_id"] == 11
    assert payload["message"] == "Time to leave for: Defense rehearsal"


def test_scan_upcoming_reminders_is_callable() -> None:
    assert callable(scan_upcoming_reminders)


def test_scan_departure_reminders_is_callable() -> None:
    assert callable(scan_departure_reminders)


def test_scan_idle_slot_risks_is_callable() -> None:
    assert callable(scan_idle_slot_risks)


def test_scan_conflict_warnings_is_callable() -> None:
    assert callable(scan_conflict_warnings)


def test_cleanup_old_reminders_is_callable() -> None:
    assert callable(cleanup_old_reminders)
