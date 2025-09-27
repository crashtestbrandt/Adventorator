"""widen import_logs.stable_id to 64 chars

Revision ID: cda001a0003
Revises: cda001a0002
Create Date: 2025-09-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "cda001a0003"
down_revision: Union[str, None] = "cda001a0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("import_logs", "stable_id", existing_type=sa.String(length=26), type_=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.alter_column("import_logs", "stable_id", existing_type=sa.String(length=64), type_=sa.String(length=26), nullable=False)
