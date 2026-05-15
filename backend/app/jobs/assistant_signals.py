"""Proactive assistant signal generation jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import AssistantSignalCreate
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import AssistantProposal, Event, Task, UserProfile
from app.services.context import ContextService
from app.services.assistant_signal_manager import AssistantSignalManager


DEADLINE_RISK_WINDOW = timedelta(hours=24)
CONFLICT_LOOKAHEAD = timedelta(hours=24)
DEPARTURE_READINESS_WINDOW = timedelta(minutes=30)
DAILY_RHYTHM_WINDOW = timedelta(minutes=30)
PROPOSAL_FOLLOWUP_AGE = timedelta(hours=2)
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


@celery_app.task(name="app.jobs.assistant_signals.scan_pending_proposal_followup_signals")
def scan_pending_proposal_followup_signals() -> dict[str, int | str]:
    """Create follow-up signals for stale pending proposals without executing writes."""
    return asyncio.run(_scan_pending_proposal_followup_signals())


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


async def _scan_pending_proposal_followup_signals(
    *,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    manager: AssistantSignalManager | None = None,
    force: bool = False,
    limit: int = 100,
) -> dict[str, int | str]:
    if not force and get_settings().assistant_proactive_mode == "off":
        return {"status": "skipped", "reason": "assistant proactive mode is off", "generated_count": 0}

    now = _as_utc(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    session_factory = session_factory or get_sessionmaker()
    manager = manager or AssistantSignalManager()
    cutoff = now - PROPOSAL_FOLLOWUP_AGE

    async with session_factory() as session:
        proposals = (
            await session.scalars(
                select(AssistantProposal)
                .where(
                    AssistantProposal.status == "pending",
                    AssistantProposal.created_at <= cutoff,
                    or_(AssistantProposal.expires_at.is_(None), AssistantProposal.expires_at > now),
                    AssistantProposal.archived_at.is_(None),
                )
                .order_by(AssistantProposal.created_at.asc(), AssistantProposal.id.asc())
                .limit(limit)
            )
        ).all()

    generated = 0
    for proposal in proposals:
        dedup_key = f"proposal_followup:proposal:{proposal.id}"
        existing = await manager.repository.get_blocking_by_dedup_key(user_id=proposal.user_id, dedup_key=dedup_key, now=now)
        payload_json = proposal.payload_json or {}
        signal = await manager.create_signal(
            user_id=proposal.user_id,
            payload=AssistantSignalCreate(
                signal_type="proposal_followup",
                severity="info",
                dedup_key=dedup_key,
                target_type="proposal",
                target_id=proposal.id,
                context_json={
                    "proposal_id": proposal.id,
                    "proposal_type": proposal.proposal_type,
                    "proposal_summary": proposal.summary,
                    "protocol_label": payload_json.get("protocol_label"),
                    "recommended_option_id": proposal.recommended_option_id,
                    "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
                    "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
                },
                source_job="assistant_signals.proposal_followup",
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
        event_start = _as_utc(event.start_time) or departure_time
        slack_minutes = None
        if event.travel_duration_minutes is not None:
            slack_minutes = int((event_start - departure_time).total_seconds() // 60) - event.travel_duration_minutes
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
                    "event_start": event_start.isoformat(),
                    "departure_time": departure_time.isoformat(),
                    "travel_duration_minutes": event.travel_duration_minutes,
                    "slack_minutes": slack_minutes,
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
            context_json = await _daily_rhythm_context(
                session_factory=session_factory,
                user_id=profile.username,
                signal_type=signal_type,
                local_now=local_now,
                trigger_at=trigger_at,
                timezone_name=timezone_name,
            )
            signal = await manager.create_signal(
                user_id=profile.username,
                payload=AssistantSignalCreate(
                    signal_type=signal_type,
                    severity="info",
                    dedup_key=dedup_key,
                    context_json=context_json,
                    source_job="assistant_signals.daily_rhythm",
                ),
            )
            if existing is None or signal.id != existing.id:
                generated += 1

    return {"status": "ok", "generated_count": generated}


async def _daily_rhythm_context(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: str,
    signal_type: str,
    local_now: datetime,
    trigger_at: datetime,
    timezone_name: str,
) -> dict[str, object]:
    target_date = local_now.date()
    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)
    async with session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(Event)
                    .where(
                        Event.user_id == user_id,
                        Event.start_time >= day_start,
                        Event.start_time < day_end,
                        Event.status != "canceled",
                    )
                    .order_by(Event.start_time.asc(), Event.id.asc())
                    .limit(5)
                )
            ).all()
        )
        tasks = list(
            (
                await session.scalars(
                    select(Task)
                    .where(
                        Task.user_id == user_id,
                        Task.status.notin_(["done", "completed", "archived", "canceled", "cancelled"]),
                    )
                    .order_by(Task.priority.desc(), Task.id.asc())
                    .limit(5)
                )
            ).all()
        )
        proposals = list(
            (
                await session.scalars(
                    select(AssistantProposal)
                    .where(
                        AssistantProposal.user_id == user_id,
                        AssistantProposal.status == "pending",
                    )
                    .order_by(AssistantProposal.created_at.desc(), AssistantProposal.id.desc())
                    .limit(5)
                )
            ).all()
        )

    event_items = [_event_snapshot_label(event) for event in events]
    task_items = [str(task.content) for task in tasks if getattr(task, "content", None)]
    proposal_items = [str(proposal.summary) for proposal in proposals if getattr(proposal, "summary", None)]
    context: dict[str, object] = {
        "local_date": target_date.isoformat(),
        "trigger_at": trigger_at.isoformat(),
        "timezone": timezone_name,
        "today_events": event_items,
        "active_tasks": task_items,
        "pending_proposals": proposal_items,
    }
    context["message"] = _daily_rhythm_message(signal_type=signal_type, context=context)
    return context


def _event_snapshot_label(event: Event) -> str:
    start_time = getattr(event, "start_time", None)
    prefix = start_time.strftime("%H:%M") if isinstance(start_time, datetime) else "时间待定"
    return f"{prefix} {event.title}"


def _daily_rhythm_message(*, signal_type: str, context: dict[str, object]) -> str:
    event_text = _join_snapshot_items(context.get("today_events")) or "暂无已确定日程"
    task_text = _join_snapshot_items(context.get("active_tasks")) or "暂无需要推进的任务"
    proposal_text = _join_snapshot_items(context.get("pending_proposals"), limit=3) or "暂无待确认方案"
    if signal_type == "daily_night_review":
        return (
            "睡前复盘："
            f"今日日程完成核对：{event_text}。"
            f"未完成任务：{task_text}。"
            f"pending proposal 跟进：{proposal_text}。"
            "可回复：今天这两个都完成了；政治课完成了，复习没做；先不要安排。"
        )
    return (
        "晨间汇报："
        f"今天已确定日程：{event_text}。"
        f"需要推进的任务：{task_text}。"
        f"仍有效待确认方案：{proposal_text}。"
        "可回复：下午的见面改到4点；确认 P1 方案A；先不要安排。"
    )


def _join_snapshot_items(value: object, *, limit: int | None = None) -> str:
    if not isinstance(value, list):
        return ""
    items = [str(item).strip(" ；;。") for item in value]
    items = [item for item in items if item]
    if limit is not None:
        items = items[:limit]
    return "；".join(items)


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
