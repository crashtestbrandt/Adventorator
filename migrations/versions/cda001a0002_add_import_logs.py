"""add import_logs table for importer provenance

Revision ID: cda001a0002
Revises: cda001a0001
Create Date: 2025-09-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "cda001a0002"
down_revision: Union[str, None] = "cda001a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=26), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("campaign_id", "sequence_no", name="ux_import_logs_campaign_sequence"),
    )
    op.create_index("ix_import_logs_campaign_phase_object", "import_logs", ["campaign_id", "phase", "object_type"]) 
    op.create_index("ix_import_logs_manifest_hash", "import_logs", ["manifest_hash"]) 


def downgrade() -> None:
    op.drop_index("ix_import_logs_manifest_hash", table_name="import_logs")
    op.drop_index("ix_import_logs_campaign_phase_object", table_name="import_logs")
    op.drop_table("import_logs")
