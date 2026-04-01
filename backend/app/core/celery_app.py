"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "personal_affairs_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.jobs.reminders", "app.jobs.inbox"],
)

celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "scan-event-start-reminders": {
            "task": "app.jobs.reminders.scan_upcoming_reminders",
            "schedule": 60.0,
        },
        "scan-departure-reminders": {
            "task": "app.jobs.reminders.scan_departure_reminders",
            "schedule": 300.0,
        },
        "scan-idle-slot-suggestions": {
            "task": "app.jobs.reminders.scan_idle_slot_risks",
            "schedule": 900.0,
        },
        "scan-conflict-warnings": {
            "task": "app.jobs.reminders.scan_conflict_warnings",
            "schedule": 1800.0,
        },
        "generate-proactive-inbox": {
            "task": "app.jobs.inbox.generate_proactive_inbox_items",
            "schedule": 600.0,
        },
    },
)
