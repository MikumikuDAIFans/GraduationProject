"""SQLAlchemy ORM models for the personal affairs assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    energy_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high/medium/low
    habit_id: Mapped[str | None] = mapped_column(ForeignKey("habits.id", ondelete="SET NULL"), nullable=True)

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
    max_splits: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_chunk_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    split_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)  # equal/priority_based/time_based


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

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "target_type",
            "target_id",
            "remind_type",
            "remind_at",
            name="uq_reminders_user_target_type_time",
        ),
    )


class Habit(Base, TimestampMixin):
    """User habit pattern and routine tracking."""

    __tablename__ = "habits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    habit_type: Mapped[str] = mapped_column(String(50), nullable=False)  # routine/preference/pattern
    description: Mapped[str] = mapped_column(Text, nullable=False)
    time_pattern: Mapped[str | None] = mapped_column(String(50), nullable=True)
    day_pattern: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)  # daily/weekly/monthly
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_occurrence: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskSplit(Base, TimestampMixin):
    """Task split records for intelligent task decomposition."""

    __tablename__ = "task_splits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    split_order: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending/completed/skipped


class AssistantSession(Base, TimestampMixin):
    __tablename__ = "assistant_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    session_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New chat")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
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


class AssistantSignal(Base, TimestampMixin):
    __tablename__ = "assistant_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_job: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposal_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_assistant_signals_user_status_type", "user_id", "status", "signal_type"),
        Index("ix_assistant_signals_user_dedup_key", "user_id", "dedup_key"),
    )


class AssistantThreadState(Base, TimestampMixin):
    __tablename__ = "assistant_thread_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("assistant_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    thread_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    # Intentionally not a foreign key to avoid a circular dependency with assistant_proposals.
    active_proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_waiting_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_specialist: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_system_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_assistant_thread_states_user_session_status", "user_id", "session_id", "status"),
    )


class AssistantProposal(Base, TimestampMixin):
    __tablename__ = "assistant_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("assistant_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    # Thread state owns conversation continuity only; proposal status remains the execution authority.
    thread_state_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="user_message")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recommended_option_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_option_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_time_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    source_signal_id: Mapped[int | None] = mapped_column(ForeignKey("assistant_signals.id", ondelete="SET NULL"), nullable=True, index=True)
    supersedes_proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_proposals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    followup_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_assistant_proposals_user_status_created", "user_id", "status", "created_at"),
        Index("ix_assistant_proposals_user_dedup_key", "user_id", "dedup_key"),
        Index("ix_assistant_proposals_session_status", "session_id", "status"),
    )


class AssistantMemoryUpdateCandidate(Base, TimestampMixin):
    __tablename__ = "assistant_memory_update_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_specialist: Mapped[str] = mapped_column(String(128), nullable=False, default="memory")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    proposed_change_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_assistant_memory_candidates_user_status_type", "user_id", "status", "memory_type"),
        Index("ix_assistant_memory_candidates_user_dedup_key", "user_id", "dedup_key"),
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
