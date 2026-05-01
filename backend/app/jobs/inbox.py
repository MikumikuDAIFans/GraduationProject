"""Background job for proactive inbox item generation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Event, Reminder, Task


@celery_app.task(name="app.jobs.inbox.generate_proactive_inbox_items")
def generate_proactive_inbox_items() -> dict[str, int | str]:
    """Scan tasks with partial progress and generate inbox follow-up reminders."""
    return asyncio.run(_generate_proactive_inbox_items())


async def _generate_proactive_inbox_items(*, force: bool = False) -> dict[str, int | str]:
    settings = get_settings()
    if not force and not settings.assistant_legacy_inbox_job_enabled:
        return {
            "status": "skipped",
            "reason": "legacy proactive inbox job is disabled",
            "generated_count": 0,
        }
    if not force and settings.assistant_proactive_mode == "off":
        return {
            "status": "skipped",
            "reason": "assistant proactive mode is off",
            "generated_count": 0,
        }

    now = datetime.now(timezone.utc)
    session_factory = get_sessionmaker()
    generated_count = 0

    async with session_factory() as session:
        pending_tasks = (
            await session.scalars(
                select(Task).where(
                    Task.status.notin_(["done"]),
                )
            )
        ).all()

        for task in pending_tasks:
            focus_blocks = (
                await session.scalars(
                    select(Event).where(
                        Event.linked_task_id == task.id,
                        Event.event_type == "focus_block",
                    )
                )
            ).all()

            if not focus_blocks:
                continue

            completed_blocks = [event for event in focus_blocks if event.status == "completed"]
            canceled_blocks = [event for event in focus_blocks if event.status == "canceled"]

            if canceled_blocks:
                existing_replan = await session.scalar(
                    select(Reminder).where(
                        Reminder.user_id == task.user_id,
                        Reminder.target_type == "task",
                        Reminder.target_id == task.id,
                        Reminder.remind_type == "task_replan",
                        Reminder.remind_at >= now - timedelta(hours=4),
                    )
                )
                if existing_replan is None:
                    session.add(
                        Reminder(
                            user_id=task.user_id,
                            target_type="task",
                            target_id=task.id,
                            remind_type="task_replan",
                            remind_at=now,
                            delivery_channel="in_app",
                            message=f"Task '{task.content}' has {len(canceled_blocks)} canceled focus block(s). Consider replanning.",
                            status="pending",
                        )
                    )
                    generated_count += 1

            if completed_blocks and not canceled_blocks:
                total_minutes = sum(
                    int((event.end_time - event.start_time).total_seconds() // 60)
                    for event in completed_blocks
                    if event.start_time and event.end_time
                )
                estimated = task.estimated_duration_minutes or 60
                if total_minutes < estimated:
                    existing_progress = await session.scalar(
                        select(Reminder).where(
                            Reminder.user_id == task.user_id,
                            Reminder.target_type == "task",
                            Reminder.target_id == task.id,
                            Reminder.remind_type == "task_progress",
                            Reminder.remind_at >= now - timedelta(hours=4),
                        )
                    )
                    if existing_progress is None:
                        session.add(
                            Reminder(
                                user_id=task.user_id,
                                target_type="task",
                                target_id=task.id,
                                remind_type="task_progress",
                                remind_at=now,
                                delivery_channel="in_app",
                                message=f"Task '{task.content}': {total_minutes}/{estimated} min completed. {estimated - total_minutes} min remaining.",
                                status="pending",
                            )
                        )
                        generated_count += 1

        if generated_count:
            await session.commit()

    return {"status": "ok", "generated_count": generated_count}
