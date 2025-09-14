"""
Add unique composite index on (scene_id, user_id, dedup_hash) to pending_actions

Revision ID: 2a4b6c8d0e1f
Revises: 1f3e9c2a7b8c
Create Date: 2025-09-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2a4b6c8d0e1f'
down_revision: Union[str, None] = '1f3e9c2a7b8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use a WHERE clause to avoid NULL collisions only if dialect supports partial indexes.
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind else ''
    if dialect_name in ('postgresql', 'postgres'):
        op.create_index(
            'ux_pending_scene_user_dedup',
            'pending_actions',
            ['scene_id', 'user_id', 'dedup_hash'],
            unique=True,
            postgresql_where=sa.text('dedup_hash IS NOT NULL'),
        )
    else:
        # SQLite: unique index treats NULLs as distinct; safe to create plain unique index.
        op.create_index(
            'ux_pending_scene_user_dedup',
            'pending_actions',
            ['scene_id', 'user_id', 'dedup_hash'],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index('ux_pending_scene_user_dedup', table_name='pending_actions')
