"""add content_nodes table

Revision ID: 9f2a1d3c4b5a
Revises: 8c7f2d1a9b2b
Create Date: 2025-09-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9f2a1d3c4b5a"
down_revision = "8c7f2d1a9b2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.Enum("location", "npc", "encounter", "lore", name="nodetype"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("player_text", sa.Text(), nullable=False),
        sa.Column("gm_text", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_content_nodes_campaign_type_title",
        "content_nodes",
        ["campaign_id", "node_type", "title"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_nodes_campaign_type_title", table_name="content_nodes")
    op.drop_table("content_nodes")
