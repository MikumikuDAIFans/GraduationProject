"""add_habits_and_task_splits_tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '1d052940e0a7'
down_revision = '0006_performance_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'habits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('habit_type', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('time_pattern', sa.String(length=100), nullable=True),
        sa.Column('day_pattern', sa.String(length=100), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('activity', sa.String(length=200), nullable=True),
        sa.Column('frequency', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('occurrences', sa.Integer(), nullable=True),
        sa.Column('last_occurrence', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_habits_id'), 'habits', ['id'], unique=False)
    op.create_index(op.f('ix_habits_user_id'), 'habits', ['user_id'], unique=False)
    
    op.create_table(
        'task_splits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('split_order', sa.Integer(), nullable=False),
        sa.Column('scheduled_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_splits_id'), 'task_splits', ['id'], unique=False)
    op.create_index(op.f('ix_task_splits_task_id'), 'task_splits', ['task_id'], unique=False)
    
    op.add_column('events', sa.Column('energy_level', sa.String(length=20), nullable=True))
    op.add_column('events', sa.Column('habit_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('events') as batch_op:
        batch_op.create_foreign_key('fk_events_habit_id', 'habits', ['habit_id'], ['id'])
    
    op.add_column('tasks', sa.Column('max_splits', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('min_chunk_minutes', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('split_strategy', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'split_strategy')
    op.drop_column('tasks', 'min_chunk_minutes')
    op.drop_column('tasks', 'max_splits')
    op.drop_constraint(None, 'events', type_='foreignkey')
    op.drop_column('events', 'habit_id')
    op.drop_column('events', 'energy_level')
    op.drop_index(op.f('ix_task_splits_task_id'), table_name='task_splits')
    op.drop_index(op.f('ix_task_splits_id'), table_name='task_splits')
    op.drop_table('task_splits')
    op.drop_index(op.f('ix_habits_user_id'), table_name='habits')
    op.drop_index(op.f('ix_habits_id'), table_name='habits')
    op.drop_table('habits')

