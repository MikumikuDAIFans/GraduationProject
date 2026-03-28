"""Add Google Calendar sync state fields.

Revision ID: 0002_google_calendar_sync_state
Revises: 0001_initial_schema
Create Date: 2026-03-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_google_calendar_sync_state"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_profile_columns = {column["name"] for column in inspector.get_columns("user_profile")}
    event_columns = {column["name"] for column in inspector.get_columns("events")}

    if "google_calendar_status" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_status", sa.String(length=32), nullable=False, server_default="disconnected"))
    if "google_calendar_tokens_json" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_tokens_json", sa.JSON(), nullable=True))
    if "google_calendar_sync_token" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_sync_token", sa.String(length=255), nullable=True))
    if "google_calendar_connected_at" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_connected_at", sa.DateTime(timezone=True), nullable=True))
    if "google_calendar_last_sync_at" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_last_sync_at", sa.DateTime(timezone=True), nullable=True))
    if "google_calendar_error" not in user_profile_columns:
        op.add_column("user_profile", sa.Column("google_calendar_error", sa.Text(), nullable=True))

    if "external_calendar_id" not in event_columns:
        op.add_column("events", sa.Column("external_calendar_id", sa.String(length=255), nullable=True))
    if "external_etag" not in event_columns:
        op.add_column("events", sa.Column("external_etag", sa.String(length=255), nullable=True))
    if "sync_status" not in event_columns:
        op.add_column("events", sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="local_only"))
    if "last_synced_at" not in event_columns:
        op.add_column("events", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "last_synced_at")
    op.drop_column("events", "sync_status")
    op.drop_column("events", "external_etag")
    op.drop_column("events", "external_calendar_id")

    op.drop_column("user_profile", "google_calendar_error")
    op.drop_column("user_profile", "google_calendar_last_sync_at")
    op.drop_column("user_profile", "google_calendar_connected_at")
    op.drop_column("user_profile", "google_calendar_sync_token")
    op.drop_column("user_profile", "google_calendar_tokens_json")
    op.drop_column("user_profile", "google_calendar_status")
