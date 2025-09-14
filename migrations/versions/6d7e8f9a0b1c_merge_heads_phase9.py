"""Merge heads for Phase 9 branches (pending_actions idx and events)

Revision ID: 6d7e8f9a0b1c
Revises: 2a4b6c8d0e1f, 3b1c2d4e5f6a
Create Date: 2025-09-14
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "6d7e8f9a0b1c"
down_revision: Union[str, tuple[str, ...], None] = ("2a4b6c8d0e1f", "3b1c2d4e5f6a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a merge-only migration; no schema changes.
    pass


def downgrade() -> None:
    # No-op: cannot un-merge heads automatically.
    pass
