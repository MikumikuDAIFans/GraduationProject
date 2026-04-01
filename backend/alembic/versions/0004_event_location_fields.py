"""Add richer event location fields.

Revision ID: 0004_event_location_fields
Revises: 0003_event_task_linkage
Create Date: 2026-04-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_event_location_fields"
down_revision = "0003_event_task_linkage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("events")}

    if "location_address" not in event_columns:
        op.add_column("events", sa.Column("location_address", sa.String(length=500), nullable=True))
    if "location_lat" not in event_columns:
        op.add_column("events", sa.Column("location_lat", sa.Float(), nullable=True))
    if "location_lng" not in event_columns:
        op.add_column("events", sa.Column("location_lng", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("events")}

    if "location_lng" in event_columns:
        op.drop_column("events", "location_lng")
    if "location_lat" in event_columns:
        op.drop_column("events", "location_lat")
    if "location_address" in event_columns:
        op.drop_column("events", "location_address")
