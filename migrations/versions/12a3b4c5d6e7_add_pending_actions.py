"""add pending_actions table

Revision ID: 12a3b4c5d6e7
Revises: 9f2a1d3c4b5a
Create Date: 2025-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12a3b4c5d6e7'
down_revision: Union[str, None] = '9f2a1d3c4b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pending_actions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=False),
        sa.Column('chain', sa.JSON(), nullable=False),
        sa.Column('mechanics', sa.Text(), nullable=False),
        sa.Column('narration', sa.Text(), nullable=False),
        sa.Column('player_tx_id', sa.Integer(), nullable=True),
        sa.Column('bot_tx_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pending_scene_user_time', 'pending_actions', ['scene_id', 'user_id', 'created_at'])
    op.create_index(op.f('ix_pending_actions_campaign_id'), 'pending_actions', ['campaign_id'])
    op.create_index(op.f('ix_pending_actions_scene_id'), 'pending_actions', ['scene_id'])
    op.create_index(op.f('ix_pending_actions_channel_id'), 'pending_actions', ['channel_id'])
    op.create_index(op.f('ix_pending_actions_user_id'), 'pending_actions', ['user_id'])
    op.create_index(op.f('ix_pending_actions_status'), 'pending_actions', ['status'])
    op.create_index(op.f('ix_pending_actions_request_id'), 'pending_actions', ['request_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_actions_request_id'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_status'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_user_id'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_channel_id'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_scene_id'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_campaign_id'), table_name='pending_actions')
    op.drop_index('ix_pending_scene_user_time', table_name='pending_actions')
    op.drop_table('pending_actions')
