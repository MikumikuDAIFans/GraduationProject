"""Celery application factory."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "personal_affairs_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.jobs.reminders",
        "app.jobs.inbox",
        "app.jobs.proposals",
        "app.jobs.assistant_signals",
        "app.jobs.weather",
    ],
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
        "cleanup-old-reminders": {
            "task": "app.jobs.reminders.cleanup_old_reminders",
            "schedule": 3600.0,
        },
        "expire-due-assistant-proposals": {
            "task": "app.jobs.proposals.expire_due_assistant_proposals",
            "schedule": 600.0,
        },
        "scan-assistant-deadline-risk-signals": {
            "task": "app.jobs.assistant_signals.scan_deadline_risk_signals",
            "schedule": 900.0,
        },
        "scan-assistant-conflict-repair-signals": {
            "task": "app.jobs.assistant_signals.scan_conflict_repair_signals",
            "schedule": 1800.0,
        },
        "scan-assistant-departure-readiness-signals": {
            "task": "app.jobs.assistant_signals.scan_departure_readiness_signals",
            "schedule": 300.0,
        },
        "scan-assistant-daily-rhythm-signals": {
            "task": "app.jobs.assistant_signals.scan_daily_rhythm_signals",
            "schedule": 600.0,
        },
        "scan-assistant-proposal-followup-signals": {
            "task": "app.jobs.assistant_signals.scan_pending_proposal_followup_signals",
            "schedule": 900.0,
        },
        "sync-daily-weather-snapshots": {
            "task": "app.jobs.weather.sync_daily_weather_snapshots",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)
