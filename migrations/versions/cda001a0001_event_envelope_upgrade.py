"""story cda core 001a event envelope and constraints"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "cda001a0001"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GENESIS_PREV_EVENT_HASH = b"\x00" * 32


def _normalize_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return {}
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"legacy": value}
        if isinstance(decoded, dict):
            return decoded
        return {"legacy": decoded}
    if isinstance(value, dict):
        return value
    try:
        canonical = json.loads(json.dumps(value, default=str))
    except Exception:
        return {"legacy": str(value)}
    if isinstance(canonical, dict):
        return canonical
    return {"legacy": canonical}


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _payload_hash(payload: dict[str, Any]) -> bytes:
    return hashlib.sha256(_canonical_bytes(payload)).digest()


def _idempotency_key(
    *,
    campaign_id: int,
    event_type: str,
    execution_request_id: str | None,
    plan_id: str | None,
    payload: dict[str, Any],
    replay_ordinal: int,
) -> bytes:
    material = [
        str(campaign_id).encode("utf-8"),
        event_type.encode("utf-8"),
        (execution_request_id or "").encode("utf-8"),
        (plan_id or "").encode("utf-8"),
        str(replay_ordinal).encode("utf-8"),
        _canonical_bytes(payload),
    ]
    return hashlib.sha256(b"|".join(material)).digest()[:16]


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return datetime.now(timezone.utc)


def upgrade() -> None:
    bind = op.get_bind()
    legacy_rows: list[dict[str, Any]] = []
    scene_campaign: dict[int, int] = {}

    try:
        scene_rows = bind.execute(sa.text("SELECT id, campaign_id FROM scenes")).mappings()
        scene_campaign = {row["id"]: row["campaign_id"] for row in scene_rows}
    except Exception:
        scene_campaign = {}

    try:
        rows = bind.execute(
            sa.text(
                "SELECT id, scene_id, actor_id, type, payload, request_id, created_at "
                "FROM events ORDER BY id"
            )
        ).mappings()
        legacy_rows = [dict(row) for row in rows]
    except Exception:
        legacy_rows = []

    inspector = inspect(bind)
    if inspector.has_table("events"):
        op.drop_table("events")

    op.create_table(
        "events",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("replay_ordinal", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_schema_version", sa.Integer(), nullable=False),
        sa.Column("world_time", sa.Integer(), nullable=False),
        sa.Column("wall_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prev_event_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("payload_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("idempotency_key", sa.LargeBinary(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("plan_id", sa.String(length=64), nullable=True),
        sa.Column("execution_request_id", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("migrator_applied_from", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "campaign_id",
            "replay_ordinal",
            name="ux_events_campaign_replay_ordinal",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "idempotency_key",
            name="ux_events_campaign_idempotency_key",
        ),
    )

    new_rows: list[dict[str, Any]] = []
    per_campaign_state: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "ordinal": 0,
            "prev_hash": GENESIS_PREV_EVENT_HASH,
        }
    )

    for row in legacy_rows:
        scene_id = row.get("scene_id")
        campaign_id = scene_campaign.get(scene_id)
        if campaign_id is None:
            # Unable to associate the legacy event with a campaign; skip it.
            continue
        state = per_campaign_state[campaign_id]
        ordinal = state["ordinal"]
        payload = _normalize_payload(row.get("payload"))
        payload_hash = _payload_hash(payload)
        prev_hash = state["prev_hash"]
        execution_request_id = row.get("request_id")
        new_rows.append(
            {
                "event_id": row.get("id"),
                "campaign_id": campaign_id,
                "scene_id": scene_id,
                "replay_ordinal": ordinal,
                "event_type": row.get("type") or "legacy.event",
                "event_schema_version": 1,
                "world_time": ordinal,
                "wall_time_utc": _coerce_datetime(row.get("created_at")),
                "prev_event_hash": prev_hash,
                "payload_hash": payload_hash,
                "idempotency_key": _idempotency_key(
                    campaign_id=campaign_id,
                    event_type=row.get("type") or "legacy.event",
                    execution_request_id=execution_request_id,
                    plan_id=None,
                    payload=payload,
                    replay_ordinal=ordinal,
                ),
                "actor_id": row.get("actor_id"),
                "plan_id": None,
                "execution_request_id": execution_request_id,
                "approved_by": None,
                "payload": payload,
                "migrator_applied_from": None,
            }
        )
        state["ordinal"] = ordinal + 1
        state["prev_hash"] = payload_hash

    if new_rows:
        events_table = sa.table(
            "events",
            sa.column("event_id", sa.Integer()),
            sa.column("campaign_id", sa.Integer()),
            sa.column("scene_id", sa.Integer()),
            sa.column("replay_ordinal", sa.Integer()),
            sa.column("event_type", sa.String()),
            sa.column("event_schema_version", sa.Integer()),
            sa.column("world_time", sa.Integer()),
            sa.column("wall_time_utc", sa.DateTime(timezone=True)),
            sa.column("prev_event_hash", sa.LargeBinary()),
            sa.column("payload_hash", sa.LargeBinary()),
            sa.column("idempotency_key", sa.LargeBinary()),
            sa.column("actor_id", sa.String()),
            sa.column("plan_id", sa.String()),
            sa.column("execution_request_id", sa.String()),
            sa.column("approved_by", sa.String()),
            sa.column("payload", sa.JSON()),
            sa.column("migrator_applied_from", sa.Integer()),
        )
        op.bulk_insert(events_table, new_rows)

    op.create_index(op.f("ix_events_campaign_id"), "events", ["campaign_id"])
    op.create_index(op.f("ix_events_scene_id"), "events", ["scene_id"])
    op.create_index(op.f("ix_events_actor_id"), "events", ["actor_id"])
    op.create_index(op.f("ix_events_plan_id"), "events", ["plan_id"])
    op.create_index(op.f("ix_events_execution_request_id"), "events", ["execution_request_id"])
    op.create_index(op.f("ix_events_event_type"), "events", ["event_type"])
    op.create_index("ix_events_scene_replay_ordinal", "events", ["scene_id", "replay_ordinal"])
    op.create_index(
        "ix_events_scene_actor_wall_time",
        "events",
        ["scene_id", "actor_id", "wall_time_utc"],
    )
    op.create_index("ix_events_scene_wall_time", "events", ["scene_id", "wall_time_utc"])

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION events_enforce_replay_ordinal() RETURNS TRIGGER AS $$
            DECLARE expected INTEGER;
            BEGIN
                SELECT COALESCE(MAX(replay_ordinal), -1) + 1 INTO expected
                FROM events
                WHERE campaign_id = NEW.campaign_id;
                IF NEW.replay_ordinal IS NULL THEN
                    RAISE EXCEPTION 'events.replay_ordinal_null';
                END IF;
                IF NEW.replay_ordinal <> expected THEN
                    RAISE EXCEPTION 'events.replay_ordinal_gap expected % got %', expected, NEW.replay_ordinal;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER events_replay_ordinal_enforce
            BEFORE INSERT ON events
            FOR EACH ROW
            EXECUTE FUNCTION events_enforce_replay_ordinal();
            """
        )
        op.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('events', 'event_id'),
                (SELECT COALESCE(MAX(event_id), 0) FROM events)
            )
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER events_replay_ordinal_null
            BEFORE INSERT ON events
            FOR EACH ROW
            WHEN NEW.replay_ordinal IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'events.replay_ordinal_null');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER events_replay_ordinal_gap
            BEFORE INSERT ON events
            FOR EACH ROW
            WHEN NEW.replay_ordinal <> (
                SELECT COALESCE(MAX(replay_ordinal), -1) + 1
                FROM events
                WHERE campaign_id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'events.replay_ordinal_gap');
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows: list[dict[str, Any]] = []

    try:
        data = bind.execute(
            sa.text(
                "SELECT event_id, scene_id, actor_id, event_type, payload, "
                "execution_request_id, wall_time_utc FROM events ORDER BY event_id"
            )
        ).mappings()
        rows = [dict(row) for row in data]
    except Exception:
        rows = []

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS events_replay_ordinal_enforce ON events")
        op.execute("DROP FUNCTION IF EXISTS events_enforce_replay_ordinal()")
    else:
        op.execute("DROP TRIGGER IF EXISTS events_replay_ordinal_gap")
        op.execute("DROP TRIGGER IF EXISTS events_replay_ordinal_null")

    op.drop_index("ix_events_scene_actor_wall_time", table_name="events")
    op.drop_index("ix_events_scene_replay_ordinal", table_name="events")
    op.drop_index("ix_events_scene_wall_time", table_name="events")
    op.drop_index(op.f("ix_events_campaign_id"), table_name="events")
    op.drop_index(op.f("ix_events_scene_id"), table_name="events")
    op.drop_index(op.f("ix_events_actor_id"), table_name="events")
    op.drop_index(op.f("ix_events_plan_id"), table_name="events")
    op.drop_index(op.f("ix_events_execution_request_id"), table_name="events")
    op.drop_index(op.f("ix_events_event_type"), table_name="events")
    op.drop_table("events")

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
    )

    if rows:
        legacy_table = sa.table(
            "events",
            sa.column("id", sa.Integer()),
            sa.column("scene_id", sa.Integer()),
            sa.column("actor_id", sa.String()),
            sa.column("type", sa.String()),
            sa.column("payload", sa.JSON()),
            sa.column("request_id", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        downgrade_rows: list[dict[str, Any]] = []
        for row in rows:
            scene_id = row.get("scene_id")
            if scene_id is None:
                # Legacy schema could not represent scene-less events.
                continue
            payload = _normalize_payload(row.get("payload"))
            downgrade_rows.append(
                {
                    "id": row.get("event_id"),
                    "scene_id": scene_id,
                    "actor_id": row.get("actor_id"),
                    "type": row.get("event_type") or "legacy.event",
                    "payload": payload,
                    "request_id": row.get("execution_request_id"),
                    "created_at": _coerce_datetime(row.get("wall_time_utc")),
                }
            )
        op.bulk_insert(legacy_table, downgrade_rows)

    op.create_index("ix_events_scene_time", "events", ["scene_id", "created_at"])
    op.create_index(
        "ix_events_scene_actor_time",
        "events",
        ["scene_id", "actor_id", "created_at"],
    )
    op.create_index(op.f("ix_events_type"), "events", ["type"])
    op.create_index(op.f("ix_events_request_id"), "events", ["request_id"])

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('events', 'id'),
                (SELECT COALESCE(MAX(id), 0) FROM events)
            )
            """
        )
