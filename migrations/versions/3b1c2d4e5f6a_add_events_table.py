"""add events table

Revision ID: 3b1c2d4e5f6a
Revises: 12a3b4c5d6e7
Create Date: 2025-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b1c2d4e5f6a'
# Chain after pending_actions for Phase 9
down_revision: Union[str, None] = '12a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=True),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_scene_time', 'events', ['scene_id', 'created_at'])
    op.create_index('ix_events_scene_actor_time', 'events', ['scene_id', 'actor_id', 'created_at'])
    op.create_index(op.f('ix_events_type'), 'events', ['type'])
    op.create_index(op.f('ix_events_request_id'), 'events', ['request_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_events_request_id'), table_name='events')
    op.drop_index(op.f('ix_events_type'), table_name='events')
    op.drop_index('ix_events_scene_actor_time', table_name='events')
    op.drop_index('ix_events_scene_time', table_name='events')
    op.drop_table('events')
