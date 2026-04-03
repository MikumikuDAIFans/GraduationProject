"""Add assistant session metadata and reminder dedupe constraints.

Revision ID: 0005_assistant_session_and_reminder_constraints
Revises: 0004_event_location_fields
Create Date: 2026-04-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_assistant_session_and_reminder_constraints"
down_revision = "0004_event_location_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    assistant_columns = {column["name"] for column in inspector.get_columns("assistant_sessions")}
    if "title" not in assistant_columns:
        op.add_column(
            "assistant_sessions",
            sa.Column("title", sa.String(length=255), nullable=False, server_default="New chat"),
        )
    if "is_archived" not in assistant_columns:
        op.add_column(
            "assistant_sessions",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_assistant_sessions_is_archived", "assistant_sessions", ["is_archived"], unique=False)

    reminder_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("reminders")}
    if "uq_reminders_user_target_type_time" not in reminder_constraints:
        with op.batch_alter_table("reminders", recreate="always") as batch_op:
            batch_op.create_unique_constraint(
                "uq_reminders_user_target_type_time",
                ["user_id", "target_type", "target_id", "remind_type", "remind_at"],
            )

    op.execute("UPDATE assistant_sessions SET title = COALESCE(title, 'New chat')")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    reminder_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("reminders")}
    if "uq_reminders_user_target_type_time" in reminder_constraints:
        with op.batch_alter_table("reminders", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_reminders_user_target_type_time", type_="unique")

    assistant_columns = {column["name"] for column in inspector.get_columns("assistant_sessions")}
    indexes = {index["name"] for index in inspector.get_indexes("assistant_sessions")}
    if "ix_assistant_sessions_is_archived" in indexes:
        op.drop_index("ix_assistant_sessions_is_archived", table_name="assistant_sessions")
    if "is_archived" in assistant_columns:
        op.drop_column("assistant_sessions", "is_archived")
    if "title" in assistant_columns:
        op.drop_column("assistant_sessions", "title")
