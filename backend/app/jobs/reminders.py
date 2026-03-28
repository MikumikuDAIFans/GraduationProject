"""Reminder-related Celery jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.models import Event, Reminder


@celery_app.task(name="app.jobs.reminders.scan_upcoming_reminders")
def scan_upcoming_reminders() -> dict[str, int]:
    """Scan for reminders that should soon be delivered."""
    return asyncio.run(_scan_upcoming_reminders())


async def _scan_upcoming_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=30)
    event_window_end = now + timedelta(hours=24)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.start_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= event_window_end,
                )
            )
        ).all()

        generated_count = 0
        for event in upcoming_events:
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == event.user_id,
                    Reminder.target_type == "event",
                    Reminder.target_id == event.id,
                    Reminder.remind_type == "event_start",
                )
            )
            if existing is not None:
                continue

            payload = _build_event_start_reminder_payload(event=event, now=now)
            session.add(
                Reminder(
                    user_id=event.user_id,
                    **payload,
                )
            )
            generated_count += 1

            if event.departure_time is not None:
                existing_departure = await session.scalar(
                    select(Reminder).where(
                        Reminder.user_id == event.user_id,
                        Reminder.target_type == "event",
                        Reminder.target_id == event.id,
                        Reminder.remind_type == "departure",
                    )
                )
                if existing_departure is None:
                    departure_payload = _build_departure_reminder_payload(event=event, now=now)
                    session.add(
                        Reminder(
                            user_id=event.user_id,
                            **departure_payload,
                        )
                    )
                    generated_count += 1

        if generated_count:
            await session.commit()

        pending = await session.scalar(
            select(func.count(Reminder.id)).where(
                Reminder.status == "pending",
                Reminder.remind_at >= now,
                Reminder.remind_at <= window_end,
            )
        )

    return {
        "generated_count": generated_count,
        "pending_count": int(pending or 0),
    }


def _build_event_start_reminder_payload(*, event: Event, now: datetime) -> dict[str, object]:
    event_start = event.start_time
    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    remind_at = event_start - timedelta(minutes=30)
    if remind_at < now:
        remind_at = now

    return {
        "target_type": "event",
        "target_id": event.id,
        "remind_type": "event_start",
        "remind_at": remind_at,
        "delivery_channel": "in_app",
        "message": f"Upcoming event: {event.title}",
        "status": "pending",
    }


def _build_departure_reminder_payload(*, event: Event, now: datetime) -> dict[str, object]:
    departure_time = event.departure_time
    if departure_time.tzinfo is None:
        departure_time = departure_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    remind_at = departure_time if departure_time > now else now
    return {
        "target_type": "event",
        "target_id": event.id,
        "remind_type": "departure",
        "remind_at": remind_at,
        "delivery_channel": "in_app",
        "message": f"Time to leave for: {event.title}",
        "status": "pending",
    }
