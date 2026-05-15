"""assistant message render blocks"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_assistant_message_render_blocks"
down_revision = "0008_assistant_memory_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assistant_messages", sa.Column("render_blocks_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistant_messages", "render_blocks_json")
