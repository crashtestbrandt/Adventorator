"""
Add status column to transcripts table.

Revision ID: 8c7f2d1a9b2b
Revises: 47831d6a93c3
Create Date: 2025-09-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8c7f2d1a9b2b'
down_revision = '47831d6a93c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('transcripts', sa.Column('status', sa.String(length=16), nullable=False, server_default='complete'))
    # Optional: if you plan to query by status often, you can add an index
    # op.create_index('ix_transcripts_status', 'transcripts', ['status'])


def downgrade() -> None:
    # If index was created in upgrade, drop it here first
    # op.drop_index('ix_transcripts_status', table_name='transcripts')
    op.drop_column('transcripts', 'status')
