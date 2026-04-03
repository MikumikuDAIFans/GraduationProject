"""add performance indexes for events, tasks, and messages

Revision ID: 0006_performance_indexes
Revises: 0005_assistant_session_and_reminder_constraints
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_performance_indexes'
down_revision: Union[str, None] = '0005_assistant_session_and_reminder_constraints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Events table indexes for common query patterns
    op.create_index('ix_events_user_id_status', 'events', ['user_id', 'status'])
    op.create_index('ix_events_user_id_start_time', 'events', ['user_id', 'start_time'])
    
    # Tasks table indexes for common query patterns  
    op.create_index('ix_tasks_user_id_status', 'tasks', ['user_id', 'status'])
    op.create_index('ix_tasks_user_id_deadline', 'tasks', ['user_id', 'deadline'])
    
    # Assistant messages index for session-based queries
    op.create_index('ix_assistant_messages_session_id_role', 'assistant_messages', ['session_id', 'role'])


def downgrade() -> None:
    op.drop_index('ix_assistant_messages_session_id_role', table_name='assistant_messages')
    op.drop_index('ix_tasks_user_id_deadline', table_name='tasks')
    op.drop_index('ix_tasks_user_id_status', table_name='tasks')
    op.drop_index('ix_events_user_id_start_time', table_name='events')
    op.drop_index('ix_events_user_id_status', table_name='events')
