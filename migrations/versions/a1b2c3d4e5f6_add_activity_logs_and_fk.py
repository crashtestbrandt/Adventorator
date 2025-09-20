"""add activity_logs table and activity_log_id FKs

Revision ID: a1b2c3d4e5f6
Revises: 7a8b9c0d1e2f
Create Date: 2025-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create activity_logs table if not exists (fresh clones rely on models but earlier head lacked this table)
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_ref", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_activity_logs_campaign_scene_time",
        "activity_logs",
        ["campaign_id", "scene_id", "created_at"],
    )
    op.create_index(op.f("ix_activity_logs_campaign_id"), "activity_logs", ["campaign_id"])
    op.create_index(op.f("ix_activity_logs_scene_id"), "activity_logs", ["scene_id"])
    op.create_index(op.f("ix_activity_logs_event_type"), "activity_logs", ["event_type"])
    op.create_index(op.f("ix_activity_logs_request_id"), "activity_logs", ["request_id"])

    # Add activity_log_id to transcripts if missing
    with op.batch_alter_table("transcripts") as batch_op:
        batch_op.add_column(sa.Column("activity_log_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transcripts_activity_logs", "activity_logs", ["activity_log_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_transcripts_activity_log_id", ["activity_log_id"])

    # Add activity_log_id to pending_actions if table exists and column missing
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "pending_actions" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("pending_actions")}
        if "activity_log_id" not in cols:
            with op.batch_alter_table("pending_actions") as batch_op:
                batch_op.add_column(sa.Column("activity_log_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_pending_actions_activity_logs", "activity_logs", ["activity_log_id"], ["id"], ondelete="SET NULL"
                )
                batch_op.create_index("ix_pending_actions_activity_log_id", ["activity_log_id"])


def downgrade() -> None:
    # Drop FKs/columns first
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "pending_actions" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("pending_actions")}
        if "activity_log_id" in cols:
            with op.batch_alter_table("pending_actions") as batch_op:
                batch_op.drop_index("ix_pending_actions_activity_log_id")
                batch_op.drop_constraint("fk_pending_actions_activity_logs", type_="foreignkey")
                batch_op.drop_column("activity_log_id")

    with op.batch_alter_table("transcripts") as batch_op:
        batch_op.drop_index("ix_transcripts_activity_log_id")
        batch_op.drop_constraint("fk_transcripts_activity_logs", type_="foreignkey")
        batch_op.drop_column("activity_log_id")

    # Drop activity_logs table
    op.drop_index("ix_activity_logs_request_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_event_type", table_name="activity_logs")
    op.drop_index("ix_activity_logs_scene_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_campaign_scene_time", table_name="activity_logs")
    op.drop_index("ix_activity_logs_campaign_id", table_name="activity_logs")
    op.drop_table("activity_logs")
