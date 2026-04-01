"""SQLAlchemy ORM models for the personal affairs assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    home_location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_location_coords: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_location_coords: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transport_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wake_up_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sleep_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    preferences_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    google_calendar_status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    google_calendar_tokens_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    google_calendar_sync_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_calendar_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_calendar_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_calendar_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_coords: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_lat: Mapped[float | None] = mapped_column(nullable=True)
    location_lng: Mapped[float | None] = mapped_column(nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True, default="general")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    is_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    buffer_before: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    buffer_after: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    travel_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    travel_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    departure_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    linked_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="local_only")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "external_event_id", name="uq_events_user_external_event"),
    )


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    can_split: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_period: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    remind_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    delivery_channel: Mapped[str | None] = mapped_column(String(64), nullable=True, default="in_app")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantSession(Base, TimestampMixin):
    __tablename__ = "assistant_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    session_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assistant_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class ScheduleChangeLog(Base):
    __tablename__ = "schedule_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trigger_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
