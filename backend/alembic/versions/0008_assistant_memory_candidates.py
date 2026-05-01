"""assistant memory update candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_assistant_memory_candidates"
down_revision = "0007_assistant_proposal_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_memory_update_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("source_specialist", sa.String(length=128), nullable=False, server_default="memory"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("proposed_change_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_memory_update_candidates_user_id", "assistant_memory_update_candidates", ["user_id"])
    op.create_index("ix_assistant_memory_update_candidates_memory_type", "assistant_memory_update_candidates", ["memory_type"])
    op.create_index("ix_assistant_memory_update_candidates_status", "assistant_memory_update_candidates", ["status"])
    op.create_index("ix_assistant_memory_update_candidates_dedup_key", "assistant_memory_update_candidates", ["dedup_key"])
    op.create_index(
        "ix_assistant_memory_candidates_user_status_type",
        "assistant_memory_update_candidates",
        ["user_id", "status", "memory_type"],
    )
    op.create_index(
        "ix_assistant_memory_candidates_user_dedup_key",
        "assistant_memory_update_candidates",
        ["user_id", "dedup_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_memory_candidates_user_dedup_key", table_name="assistant_memory_update_candidates")
    op.drop_index("ix_assistant_memory_candidates_user_status_type", table_name="assistant_memory_update_candidates")
    op.drop_index("ix_assistant_memory_update_candidates_dedup_key", table_name="assistant_memory_update_candidates")
    op.drop_index("ix_assistant_memory_update_candidates_status", table_name="assistant_memory_update_candidates")
    op.drop_index("ix_assistant_memory_update_candidates_memory_type", table_name="assistant_memory_update_candidates")
    op.drop_index("ix_assistant_memory_update_candidates_user_id", table_name="assistant_memory_update_candidates")
    op.drop_table("assistant_memory_update_candidates")
