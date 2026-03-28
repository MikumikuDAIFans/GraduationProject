"""Add linked_task_id to events for focus-block lifecycle tracking.

Revision ID: 0003_event_task_linkage
Revises: 0002_google_calendar_sync_state
Create Date: 2026-03-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_event_task_linkage"
down_revision = "0002_google_calendar_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    indexes = {index["name"] for index in inspector.get_indexes("events")}

    if "linked_task_id" not in event_columns:
        op.add_column(
            "events",
            sa.Column("linked_task_id", sa.Integer(), nullable=True),
        )
    if "ix_events_linked_task_id" not in indexes:
        op.create_index("ix_events_linked_task_id", "events", ["linked_task_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("events")}
    event_columns = {column["name"] for column in inspector.get_columns("events")}

    if "ix_events_linked_task_id" in indexes:
        op.drop_index("ix_events_linked_task_id", table_name="events")
    if "linked_task_id" in event_columns:
        op.drop_column("events", "linked_task_id")
