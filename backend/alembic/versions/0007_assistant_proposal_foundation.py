"""assistant proposal foundation"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_assistant_proposal_foundation"
down_revision = "1d052940e0a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("source_job", sa.String(length=128), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposal_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_signals_user_id", "assistant_signals", ["user_id"])
    op.create_index("ix_assistant_signals_signal_type", "assistant_signals", ["signal_type"])
    op.create_index("ix_assistant_signals_status", "assistant_signals", ["status"])
    op.create_index("ix_assistant_signals_dedup_key", "assistant_signals", ["dedup_key"])
    op.create_index("ix_assistant_signals_target_id", "assistant_signals", ["target_id"])
    op.create_index("ix_assistant_signals_user_status_type", "assistant_signals", ["user_id", "status", "signal_type"])
    op.create_index("ix_assistant_signals_user_dedup_key", "assistant_signals", ["user_id", "dedup_key"])

    op.create_table(
        "assistant_thread_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("assistant_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("thread_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("related_task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active_proposal_id", sa.Integer(), nullable=True),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("is_waiting_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_specialist", sa.String(length=128), nullable=True),
        sa.Column("last_user_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_system_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_thread_states_user_id", "assistant_thread_states", ["user_id"])
    op.create_index("ix_assistant_thread_states_session_id", "assistant_thread_states", ["session_id"])
    op.create_index("ix_assistant_thread_states_status", "assistant_thread_states", ["status"])
    op.create_index("ix_assistant_thread_states_related_task_id", "assistant_thread_states", ["related_task_id"])
    op.create_index("ix_assistant_thread_states_related_event_id", "assistant_thread_states", ["related_event_id"])
    op.create_index("ix_assistant_thread_states_active_proposal_id", "assistant_thread_states", ["active_proposal_id"])
    op.create_index(
        "ix_assistant_thread_states_user_session_status",
        "assistant_thread_states",
        ["user_id", "session_id", "status"],
    )

    op.create_table(
        "assistant_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_profile.username", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("assistant_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("thread_state_id", sa.Integer(), nullable=True),
        sa.Column("proposal_type", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, server_default="user_message"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("recommended_option_id", sa.String(length=64), nullable=True),
        sa.Column("selected_option_id", sa.String(length=64), nullable=True),
        sa.Column("is_time_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("related_task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_signal_id", sa.Integer(), sa.ForeignKey("assistant_signals.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "supersedes_proposal_id",
            sa.Integer(),
            sa.ForeignKey("assistant_proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("followup_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_proposals_user_id", "assistant_proposals", ["user_id"])
    op.create_index("ix_assistant_proposals_session_id", "assistant_proposals", ["session_id"])
    op.create_index("ix_assistant_proposals_thread_state_id", "assistant_proposals", ["thread_state_id"])
    op.create_index("ix_assistant_proposals_proposal_type", "assistant_proposals", ["proposal_type"])
    op.create_index("ix_assistant_proposals_status", "assistant_proposals", ["status"])
    op.create_index("ix_assistant_proposals_dedup_key", "assistant_proposals", ["dedup_key"])
    op.create_index("ix_assistant_proposals_related_task_id", "assistant_proposals", ["related_task_id"])
    op.create_index("ix_assistant_proposals_related_event_id", "assistant_proposals", ["related_event_id"])
    op.create_index("ix_assistant_proposals_source_signal_id", "assistant_proposals", ["source_signal_id"])
    op.create_index("ix_assistant_proposals_supersedes_proposal_id", "assistant_proposals", ["supersedes_proposal_id"])
    op.create_index("ix_assistant_proposals_expires_at", "assistant_proposals", ["expires_at"])
    op.create_index("ix_assistant_proposals_user_status_created", "assistant_proposals", ["user_id", "status", "created_at"])
    op.create_index("ix_assistant_proposals_user_dedup_key", "assistant_proposals", ["user_id", "dedup_key"])
    op.create_index("ix_assistant_proposals_session_status", "assistant_proposals", ["session_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_assistant_proposals_session_status", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_user_dedup_key", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_user_status_created", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_expires_at", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_supersedes_proposal_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_source_signal_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_related_event_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_related_task_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_dedup_key", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_status", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_proposal_type", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_thread_state_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_session_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_user_id", table_name="assistant_proposals")
    op.drop_table("assistant_proposals")

    op.drop_index("ix_assistant_thread_states_user_session_status", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_active_proposal_id", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_related_event_id", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_related_task_id", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_status", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_session_id", table_name="assistant_thread_states")
    op.drop_index("ix_assistant_thread_states_user_id", table_name="assistant_thread_states")
    op.drop_table("assistant_thread_states")

    op.drop_index("ix_assistant_signals_user_dedup_key", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_user_status_type", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_target_id", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_dedup_key", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_status", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_signal_type", table_name="assistant_signals")
    op.drop_index("ix_assistant_signals_user_id", table_name="assistant_signals")
    op.drop_table("assistant_signals")
