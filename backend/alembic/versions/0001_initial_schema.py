"""Initial schema.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("home_location_name", sa.String(length=255), nullable=True),
        sa.Column("home_location_coords", sa.String(length=64), nullable=True),
        sa.Column("work_location_name", sa.String(length=255), nullable=True),
        sa.Column("work_location_coords", sa.String(length=64), nullable=True),
        sa.Column("transport_preference", sa.String(length=64), nullable=True),
        sa.Column("wake_up_time", sa.String(length=16), nullable=True),
        sa.Column("sleep_time", sa.String(length=16), nullable=True),
        sa.Column("preferences_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column("location_coords", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_fixed", sa.Boolean(), nullable=False),
        sa.Column("buffer_before", sa.Integer(), nullable=True),
        sa.Column("buffer_after", sa.Integer(), nullable=True),
        sa.Column("travel_mode", sa.String(length=32), nullable=True),
        sa.Column("travel_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("user_id", "external_event_id", name="uq_events_user_external_event"),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_start_time", "events", ["start_time"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("can_split", sa.Boolean(), nullable=False),
        sa.Column("preferred_period", sa.String(length=64), nullable=True),
        sa.Column("linked_event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_deadline", "tasks", ["deadline"])
    op.create_index("ix_tasks_linked_event_id", "tasks", ["linked_event_id"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("remind_type", sa.String(length=64), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_channel", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_target_id", "reminders", ["target_id"])
    op.create_index("ix_reminders_remind_type", "reminders", ["remind_type"])
    op.create_index("ix_reminders_remind_at", "reminders", ["remind_at"])

    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("session_type", sa.String(length=64), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_assistant_sessions_user_id", "assistant_sessions", ["user_id"])

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("assistant_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assistant_messages_session_id", "assistant_messages", ["session_id"])

    op.create_table(
        "schedule_change_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("trigger_source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedule_change_logs_user_id", "schedule_change_logs", ["user_id"])
    op.create_index("ix_schedule_change_logs_event_id", "schedule_change_logs", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_schedule_change_logs_event_id", table_name="schedule_change_logs")
    op.drop_index("ix_schedule_change_logs_user_id", table_name="schedule_change_logs")
    op.drop_table("schedule_change_logs")

    op.drop_index("ix_assistant_messages_session_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")

    op.drop_index("ix_assistant_sessions_user_id", table_name="assistant_sessions")
    op.drop_table("assistant_sessions")

    op.drop_index("ix_reminders_remind_at", table_name="reminders")
    op.drop_index("ix_reminders_remind_type", table_name="reminders")
    op.drop_index("ix_reminders_target_id", table_name="reminders")
    op.drop_index("ix_reminders_user_id", table_name="reminders")
    op.drop_table("reminders")

    op.drop_index("ix_tasks_linked_event_id", table_name="tasks")
    op.drop_index("ix_tasks_deadline", table_name="tasks")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_events_start_time", table_name="events")
    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_table("events")

    op.drop_table("user_profile")
