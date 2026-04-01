"""Reminder-related Celery jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.models import Event, Reminder, Task


@celery_app.task(name="app.jobs.reminders.scan_upcoming_reminders")
def scan_upcoming_reminders() -> dict[str, int]:
    """Scan for reminders that should soon be delivered."""
    return asyncio.run(_scan_upcoming_reminders())


async def _scan_upcoming_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=30)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.start_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= window_end,
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


@celery_app.task(name="app.jobs.reminders.scan_departure_reminders")
def scan_departure_reminders() -> dict[str, int]:
    """Scan for departure reminders that should soon be delivered."""
    return asyncio.run(_scan_departure_reminders())


async def _scan_departure_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=2)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.departure_time.is_not(None),
                    Event.departure_time >= now,
                    Event.departure_time <= window_end,
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
                    Reminder.remind_type == "departure",
                )
            )
            if existing is not None:
                continue

            session.add(Reminder(user_id=event.user_id, **_build_departure_reminder_payload(event=event, now=now)))
            generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}


@celery_app.task(name="app.jobs.reminders.scan_idle_slot_risks")
def scan_idle_slot_risks() -> dict[str, int]:
    """Scan near-term deadlines and generate task risk reminders."""
    return asyncio.run(_scan_idle_slot_risks())


async def _scan_idle_slot_risks() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        at_risk_tasks = (
            await session.scalars(
                select(Task).where(
                    Task.deadline.is_not(None),
                    Task.deadline <= today_end,
                    Task.status.notin_(["done"]),
                )
            )
        ).all()

        generated_count = 0
        for task in at_risk_tasks:
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == task.user_id,
                    Reminder.target_type == "task",
                    Reminder.target_id == task.id,
                    Reminder.remind_type == "task_deadline",
                    Reminder.remind_at >= now - timedelta(hours=1),
                )
            )
            if existing is not None:
                continue

            due_text = task.deadline.strftime("%m-%d %H:%M") if task.deadline else "soon"
            session.add(
                Reminder(
                    user_id=task.user_id,
                    target_type="task",
                    target_id=task.id,
                    remind_type="task_deadline",
                    remind_at=now,
                    delivery_channel="in_app",
                    message=f"Task deadline approaching: {task.content} (due {due_text})",
                    status="pending",
                )
            )
            generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}


@celery_app.task(name="app.jobs.reminders.scan_conflict_warnings")
def scan_conflict_warnings() -> dict[str, int]:
    """Scan upcoming events for overlap or buffer collisions."""
    return asyncio.run(_scan_conflict_warnings())


async def _scan_conflict_warnings() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.start_time.is_not(None),
                    Event.end_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= window_end,
                ).order_by(Event.user_id.asc(), Event.start_time.asc(), Event.id.asc())
            )
        ).all()

        generated_count = 0
        for index, event_a in enumerate(upcoming_events):
            for event_b in upcoming_events[index + 1:]:
                if event_b.user_id != event_a.user_id:
                    break

                a_effective_end = event_a.end_time + timedelta(minutes=(event_a.buffer_after or 0))
                b_effective_start = event_b.start_time - timedelta(minutes=(event_b.buffer_before or 0))
                if a_effective_end <= b_effective_start:
                    continue

                existing = await session.scalar(
                    select(Reminder).where(
                        Reminder.user_id == event_a.user_id,
                        Reminder.target_type == "event",
                        Reminder.target_id == event_a.id,
                        Reminder.remind_type == "conflict_warning",
                        Reminder.remind_at >= now - timedelta(hours=6),
                    )
                )
                if existing is not None:
                    continue

                session.add(
                    Reminder(
                        user_id=event_a.user_id,
                        target_type="event",
                        target_id=event_a.id,
                        remind_type="conflict_warning",
                        remind_at=now,
                        delivery_channel="in_app",
                        message=f"Schedule conflict: '{event_a.title}' and '{event_b.title}' overlap (including buffer time).",
                        status="pending",
                    )
                )
                generated_count += 1
                break

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}


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
