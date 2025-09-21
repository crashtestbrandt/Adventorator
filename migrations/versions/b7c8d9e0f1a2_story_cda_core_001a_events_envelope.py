"""Story CDA CORE 001A events envelope and trigger"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EVENTS_REPLAY_TRIGGER_FN = "events_enforce_dense_replay_fn"
_EVENTS_REPLAY_TRIGGER = "events_enforce_dense_replay"

_POSTGRES_REPLAY_FN_SQL = f"""
CREATE OR REPLACE FUNCTION {_EVENTS_REPLAY_TRIGGER_FN}()
RETURNS TRIGGER AS $$
DECLARE
    last_ordinal integer;
BEGIN
    SELECT replay_ordinal INTO last_ordinal
    FROM events
    WHERE campaign_id = NEW.campaign_id
    ORDER BY replay_ordinal DESC
    LIMIT 1
    FOR UPDATE;

    IF last_ordinal IS NULL THEN
        IF NEW.replay_ordinal IS NULL THEN
            NEW.replay_ordinal := 0;
        ELSIF NEW.replay_ordinal <> 0 THEN
            RAISE EXCEPTION USING MESSAGE = format(
                'Replay ordinal must start at 0 for campaign %%s (got %%s)',
                NEW.campaign_id,
                NEW.replay_ordinal
            );
        END IF;
    ELSE
        IF NEW.replay_ordinal IS NULL THEN
            NEW.replay_ordinal := last_ordinal + 1;
        ELSIF NEW.replay_ordinal <> last_ordinal + 1 THEN
            RAISE EXCEPTION USING MESSAGE = format(
                'Replay ordinal must increment by 1 for campaign %%s (expected %%s got %%s)',
                NEW.campaign_id,
                last_ordinal + 1,
                NEW.replay_ordinal
            );
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_POSTGRES_REPLAY_TRIGGER_SQL = f"""
CREATE TRIGGER {_EVENTS_REPLAY_TRIGGER}
BEFORE INSERT ON events
FOR EACH ROW
EXECUTE FUNCTION {_EVENTS_REPLAY_TRIGGER_FN}();
"""

_SQLITE_REPLAY_TRIGGER_SQL = f"""
CREATE TRIGGER {_EVENTS_REPLAY_TRIGGER}
BEFORE INSERT ON events
BEGIN
    SELECT
        CASE
            WHEN NEW.replay_ordinal IS NULL THEN
                RAISE(ABORT, 'replay_ordinal must not be NULL')
            WHEN NEW.replay_ordinal <> (
                COALESCE(
                    (SELECT replay_ordinal FROM events WHERE campaign_id = NEW.campaign_id ORDER BY replay_ordinal DESC LIMIT 1),
                    -1
                ) + 1
            ) THEN
                RAISE(ABORT, 'replay_ordinal must form a dense sequence per campaign')
        END;
END;
"""


def _create_trigger() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(sa.text(_POSTGRES_REPLAY_FN_SQL))
        op.execute(sa.text(_POSTGRES_REPLAY_TRIGGER_SQL))
    elif dialect == "sqlite":
        op.execute(sa.text(_SQLITE_REPLAY_TRIGGER_SQL))


def _drop_trigger() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_EVENTS_REPLAY_TRIGGER} ON events"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_EVENTS_REPLAY_TRIGGER_FN}()"))
    elif dialect == "sqlite":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_EVENTS_REPLAY_TRIGGER}"))


def upgrade() -> None:
    # Replace legacy events table with deterministic envelope columns
    op.drop_table("events")
    op.create_table(
        "events",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("replay_ordinal", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_schema_version", sa.Integer(), nullable=False),
        sa.Column("world_time", sa.BigInteger(), nullable=False),
        sa.Column("wall_time_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("prev_event_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("payload_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("idempotency_key", sa.LargeBinary(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("plan_id", sa.String(length=64), nullable=True),
        sa.Column("execution_request_id", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("migrator_applied_from", sa.Integer(), nullable=True),
        sa.UniqueConstraint("campaign_id", "replay_ordinal", name="ux_events_campaign_replay"),
        sa.UniqueConstraint("campaign_id", "idempotency_key", name="ux_events_campaign_idempotency"),
    )
    op.create_index("ix_events_campaign_replay", "events", ["campaign_id", "replay_ordinal"])
    op.create_index("ix_events_campaign_wall_time", "events", ["campaign_id", "wall_time_utc"])
    op.create_index("ix_events_campaign_actor", "events", ["campaign_id", "actor_id"])
    op.create_index("ix_events_plan", "events", ["plan_id"])
    op.create_index("ix_events_execution_request", "events", ["execution_request_id"])
    _create_trigger()


def downgrade() -> None:
    _drop_trigger()
    op.drop_index("ix_events_execution_request", table_name="events")
    op.drop_index("ix_events_plan", table_name="events")
    op.drop_index("ix_events_campaign_actor", table_name="events")
    op.drop_index("ix_events_campaign_wall_time", table_name="events")
    op.drop_index("ix_events_campaign_replay", table_name="events")
    op.drop_table("events")
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_events_scene_time", "events", ["scene_id", "created_at"])
    op.create_index("ix_events_scene_actor_time", "events", ["scene_id", "actor_id", "created_at"])
    op.create_index(op.f("ix_events_type"), "events", ["type"])
    op.create_index(op.f("ix_events_request_id"), "events", ["request_id"])
