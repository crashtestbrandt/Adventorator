"""add dedup_hash to pending_actions

Revision ID: 1f3e9c2a7b8c
Revises: 12a3b4c5d6e7
Create Date: 2025-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1f3e9c2a7b8c'
down_revision: Union[str, None] = '12a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pending_actions', sa.Column('dedup_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_pending_actions_dedup_hash'), 'pending_actions', ['dedup_hash'])


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_actions_dedup_hash'), table_name='pending_actions')
    op.drop_column('pending_actions', 'dedup_hash')
