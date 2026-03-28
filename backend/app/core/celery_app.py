"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "personal_affairs_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.jobs.reminders"],
)

celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "scan-upcoming-reminders": {
            "task": "app.jobs.reminders.scan_upcoming_reminders",
            "schedule": 60.0,
        }
    },
)
