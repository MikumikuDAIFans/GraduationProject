"""Proactive assistant signal generation jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import AssistantSignalCreate
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Event, Task, UserProfile
from app.services.context import ContextService
from app.services.assistant_signal_manager import AssistantSignalManager


DEADLINE_RISK_WINDOW = timedelta(hours=24)
CONFLICT_LOOKAHEAD = timedelta(hours=24)
DEPARTURE_READINESS_WINDOW = timedelta(minutes=30)
DAILY_RHYTHM_WINDOW = timedelta(minutes=30)
DEFAULT_WAKE_UP_TIME = "08:00"
DEFAULT_SLEEP_TIME = "23:30"


@celery_app.task(name="app.jobs.assistant_signals.scan_deadline_risk_signals")
def scan_deadline_risk_signals() -> dict[str, int | str]:
    """Create deadline risk signals without creating proposals or writes."""
    return asyncio.run(_scan_deadline_risk_signals())


@celery_app.task(name="app.jobs.assistant_signals.scan_conflict_repair_signals")
def scan_conflict_repair_signals() -> dict[str, int | str]:
    """Create conflict repair signals without creating proposals or writes."""
    return asyncio.run(_scan_conflict_repair_signals())


@celery_app.task(name="app.jobs.assistant_signals.scan_departure_readiness_signals")
def scan_departure_readiness_signals() -> dict[str, int | str]:
    """Create departure readiness signals around departure_time, not event_start."""
    return asyncio.run(_scan_departure_readiness_signals())


@celery_app.task(name="app.jobs.assistant_signals.scan_daily_rhythm_signals")
def scan_daily_rhythm_signals() -> dict[str, int | str]:
    """Create morning/night review signals using profile rhythm fallbacks."""
    return asyncio.run(_scan_daily_rhythm_signals())


async def _scan_deadline_risk_signals(
    *,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    manager: AssistantSignalManager | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    if not force and get_settings().assistant_proactive_mode == "off":
        return {"status": "skipped", "reason": "assistant proactive mode is off", "generated_count": 0}

    now = _as_utc(now or datetime.now(timezone.utc))
    session_factory = session_factory or get_sessionmaker()
    manager = manager or AssistantSignalManager()
    window_end = now + DEADLINE_RISK_WINDOW

    async with session_factory() as session:
        tasks = (
            await session.scalars(
                select(Task).where(
                    Task.deadline.is_not(None),
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).all()

    generated = 0
    for task in tasks:
        deadline = _as_utc(task.deadline)
        if deadline is None or deadline < now or deadline > window_end:
            continue
        dedup_key = f"deadline_risk:task:{task.id}:{deadline.date().isoformat()}"
        existing = await manager.repository.get_blocking_by_dedup_key(user_id=task.user_id, dedup_key=dedup_key, now=now)
        signal = await manager.create_signal(
            user_id=task.user_id,
            payload=AssistantSignalCreate(
                signal_type="deadline_risk",
                severity="negotiate",
                dedup_key=dedup_key,
                target_type="task",
                target_id=task.id,
                context_json={
                    "task_id": task.id,
                    "content": task.content,
                    "deadline": deadline.isoformat(),
                    "remaining_minutes": max(0, int((deadline - now).total_seconds() // 60)),
                },
                source_job="assistant_signals.deadline_risk",
            ),
        )
        if existing is None or signal.id != existing.id:
            generated += 1

    return {"status": "ok", "generated_count": generated}


async def _scan_conflict_repair_signals(
    *,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    manager: AssistantSignalManager | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    if not force and get_settings().assistant_proactive_mode == "off":
        return {"status": "skipped", "reason": "assistant proactive mode is off", "generated_count": 0}

    now = _as_utc(now or datetime.now(timezone.utc))
    session_factory = session_factory or get_sessionmaker()
    manager = manager or AssistantSignalManager()
    window_end = now + CONFLICT_LOOKAHEAD

    async with session_factory() as session:
        events = (
            await session.scalars(
                select(Event)
                .where(
                    Event.start_time.is_not(None),
                    Event.end_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= window_end,
                    Event.status.notin_(["cancelled", "done"]),
                )
                .order_by(Event.user_id.asc(), Event.start_time.asc(), Event.id.asc())
            )
        ).all()

    generated = 0
    for index, event_a in enumerate(events):
        for event_b in events[index + 1 :]:
            if event_b.user_id != event_a.user_id:
                break
            if not _events_conflict(event_a, event_b):
                continue

            start = _as_utc(event_a.start_time) or now
            dedup_key = f"conflict_warning:event:{event_a.id}:{event_b.id}:{start.date().isoformat()}"
            existing = await manager.repository.get_blocking_by_dedup_key(user_id=event_a.user_id, dedup_key=dedup_key, now=now)
            signal = await manager.create_signal(
                user_id=event_a.user_id,
                payload=AssistantSignalCreate(
                    signal_type="conflict_warning",
                    severity="negotiate",
                    dedup_key=dedup_key,
                    target_type="event",
                    target_id=event_a.id,
                    context_json={
                        "event_a_id": event_a.id,
                        "event_a_title": event_a.title,
                        "event_b_id": event_b.id,
                        "event_b_title": event_b.title,
                    },
                    source_job="assistant_signals.conflict_repair",
                ),
            )
            if existing is None or signal.id != existing.id:
                generated += 1
            break

    return {"status": "ok", "generated_count": generated}


async def _scan_departure_readiness_signals(
    *,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    manager: AssistantSignalManager | None = None,
    context_service: ContextService | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    if not force and get_settings().assistant_proactive_mode == "off":
        return {"status": "skipped", "reason": "assistant proactive mode is off", "generated_count": 0}

    now = _as_utc(now or datetime.now(timezone.utc))
    session_factory = session_factory or get_sessionmaker()
    manager = manager or AssistantSignalManager()
    window_end = now + DEPARTURE_READINESS_WINDOW

    async with session_factory() as session:
        events = (
            await session.scalars(
                select(Event).where(
                    Event.departure_time.is_not(None),
                    Event.departure_time >= now,
                    Event.departure_time <= window_end,
                    Event.status.notin_(["cancelled", "done"]),
                )
            )
        ).all()
        profiles = {profile.username: profile for profile in (await session.scalars(select(UserProfile))).all()}

    generated = 0
    context_service = context_service or ContextService()
    for event in events:
        departure_time = _as_utc(event.departure_time) or now
        dedup_key = f"departure_readiness:event:{event.id}:{departure_time.date().isoformat()}"
        existing = await manager.repository.get_blocking_by_dedup_key(user_id=event.user_id, dedup_key=dedup_key, now=now)
        weather_snapshot = await _cached_weather_for_departure(
            event=event,
            profile=profiles.get(event.user_id),
            context_service=context_service,
        )
        signal = await manager.create_signal(
            user_id=event.user_id,
            payload=AssistantSignalCreate(
                signal_type="departure_readiness",
                severity="urgent",
                dedup_key=dedup_key,
                target_type="event",
                target_id=event.id,
                context_json={
                    "event_id": event.id,
                    "title": event.title,
                    "event_start": (_as_utc(event.start_time) or departure_time).isoformat(),
                    "departure_time": departure_time.isoformat(),
                    "travel_duration_minutes": event.travel_duration_minutes,
                    "location_name": event.location_name,
                    "weather_snapshot": weather_snapshot,
                },
                source_job="assistant_signals.departure_readiness",
            ),
        )
        if existing is None or signal.id != existing.id:
            generated += 1

    return {"status": "ok", "generated_count": generated}


async def _cached_weather_for_departure(
    *,
    event: Event,
    profile: UserProfile | None,
    context_service: ContextService,
) -> dict | None:
    location = event.location_coords or (profile.home_location_coords if profile else None) or (profile.work_location_coords if profile else None)
    if not location:
        return None
    snapshot = await context_service.weather_snapshot(location=location, allow_refresh=False)
    if snapshot.source == "missing" or snapshot.weather is None:
        return None
    return snapshot.model_dump(mode="json")


async def _scan_daily_rhythm_signals(
    *,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    manager: AssistantSignalManager | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    if not force and get_settings().assistant_proactive_mode == "off":
        return {"status": "skipped", "reason": "assistant proactive mode is off", "generated_count": 0}

    now = now or datetime.now(timezone.utc)
    session_factory = session_factory or get_sessionmaker()
    manager = manager or AssistantSignalManager()

    async with session_factory() as session:
        profiles = (await session.scalars(select(UserProfile))).all()

    generated = 0
    for profile in profiles:
        timezone_name = profile.timezone or get_settings().app_timezone or "Asia/Shanghai"
        local_now = _to_local(now, timezone_name)
        for signal_type, trigger_at in _daily_rhythm_triggers(profile, local_now).items():
            if not _within_window(local_now, trigger_at, DAILY_RHYTHM_WINDOW):
                continue
            dedup_key = f"{signal_type}:{profile.username}:{local_now.date().isoformat()}"
            existing = await manager.repository.get_blocking_by_dedup_key(user_id=profile.username, dedup_key=dedup_key, now=_as_utc(now) or now)
            signal = await manager.create_signal(
                user_id=profile.username,
                payload=AssistantSignalCreate(
                    signal_type=signal_type,
                    severity="info",
                    dedup_key=dedup_key,
                    context_json={
                        "local_date": local_now.date().isoformat(),
                        "trigger_at": trigger_at.isoformat(),
                        "timezone": timezone_name,
                    },
                    source_job="assistant_signals.daily_rhythm",
                ),
            )
            if existing is None or signal.id != existing.id:
                generated += 1

    return {"status": "ok", "generated_count": generated}


def _events_conflict(event_a: Event, event_b: Event) -> bool:
    a_end = _as_utc(event_a.end_time)
    b_start = _as_utc(event_b.start_time)
    if a_end is None or b_start is None:
        return False
    a_effective_end = a_end + timedelta(minutes=(event_a.buffer_after or 0))
    b_effective_start = b_start - timedelta(minutes=(event_b.buffer_before or 0))
    return a_effective_end > b_effective_start


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _daily_rhythm_triggers(profile: UserProfile, local_now: datetime) -> dict[str, datetime]:
    wake_up_time = _parse_time(profile.wake_up_time, DEFAULT_WAKE_UP_TIME)
    sleep_time = _parse_time(profile.sleep_time, DEFAULT_SLEEP_TIME)
    morning = local_now.replace(hour=wake_up_time[0], minute=wake_up_time[1], second=0, microsecond=0) + timedelta(minutes=30)
    night = local_now.replace(hour=sleep_time[0], minute=sleep_time[1], second=0, microsecond=0) - timedelta(minutes=30)
    return {
        "daily_morning_review": morning,
        "daily_night_review": night,
    }


def _parse_time(value: str | None, fallback: str) -> tuple[int, int]:
    raw = value or fallback
    try:
        hour, minute = raw.split(":", 1)
        parsed = int(hour), int(minute)
    except (TypeError, ValueError):
        hour, minute = fallback.split(":", 1)
        parsed = int(hour), int(minute)
    if not (0 <= parsed[0] <= 23 and 0 <= parsed[1] <= 59):
        hour, minute = fallback.split(":", 1)
        return int(hour), int(minute)
    return parsed


def _to_local(value: datetime, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("Asia/Shanghai")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone)


def _within_window(now: datetime, trigger_at: datetime, window: timedelta) -> bool:
    return trigger_at <= now < trigger_at + window
