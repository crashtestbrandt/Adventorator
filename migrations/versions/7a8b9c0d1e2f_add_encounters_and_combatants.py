"""add encounters and combatants tables

Revision ID: 7a8b9c0d1e2f
Revises: 6d7e8f9a0b1c
Create Date: 2025-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "6d7e8f9a0b1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Named enum for Encounter.status
def _encounter_status_enum(create_type: bool = False) -> sa.Enum:
    return sa.Enum(
        "setup",
        "active",
        "ended",
        name="encounterstatus",
        create_type=create_type,
    )


def upgrade() -> None:
    # Create enum type conditionally on Postgres to avoid DuplicateObject
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'encounterstatus') THEN
                    CREATE TYPE encounterstatus AS ENUM ('setup', 'active', 'ended');
                END IF;
            END$$;
            """
        )

    op.create_table(
        "encounters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            psql.ENUM(name="encounterstatus", create_type=False),
            nullable=False,
            server_default="setup",
        ),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(op.f("ix_encounters_scene_id"), "encounters", ["scene_id"], unique=False)
    op.create_index(op.f("ix_encounters_status"), "encounters", ["status"], unique=False)

    op.create_table(
        "combatants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("encounter_id", sa.Integer(), sa.ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("initiative", sa.Integer(), nullable=True),
        sa.Column("hp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "conditions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json") if bind.dialect.name == "postgresql" else "{}",
        ),
        sa.Column("token_id", sa.String(length=64), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(op.f("ix_combatants_encounter_id"), "combatants", ["encounter_id"], unique=False)
    op.create_index("ix_combatants_encounter_order", "combatants", ["encounter_id", "initiative", "order_idx"], unique=False)
    op.create_index(op.f("ix_combatants_name"), "combatants", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_combatants_name"), table_name="combatants")
    op.drop_index("ix_combatants_encounter_order", table_name="combatants")
    op.drop_index(op.f("ix_combatants_encounter_id"), table_name="combatants")
    op.drop_table("combatants")

    op.drop_index(op.f("ix_encounters_status"), table_name="encounters")
    op.drop_index(op.f("ix_encounters_scene_id"), table_name="encounters")
    op.drop_table("encounters")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'encounterstatus') THEN
                    DROP TYPE encounterstatus;
                END IF;
            END$$;
            """
        )
