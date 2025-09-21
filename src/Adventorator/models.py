# models.py

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    event as sa_event,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from Adventorator.db import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # Discord guild
    name: Mapped[str] = mapped_column(String(120))
    system: Mapped[str] = mapped_column(String(32), default="5e-srd")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    sheet: Mapped[dict] = mapped_column(JSON)  # validated by Pydantic on write
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    # Map scenes 1:1 to Discord channels/threads
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True, unique=True)
    mode: Mapped[str] = mapped_column(String(16), default="exploration")  # exploration|combat
    location_node_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # optional content link
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    # who is acting; could be a character id or an npc key
    actor_ref: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True
    )
    channel_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, index=True
    )  # snowflake if you capture
    author: Mapped[str] = mapped_column(String(64))  # 'player'|'bot'|'system'
    author_ref: Mapped[str | None] = mapped_column(String(64))  # e.g., discord user id
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # rolls, dc, etc.
    status: Mapped[str] = mapped_column(String(16), default="complete")  # pending|complete|error
    activity_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("activity_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


Index(
    "ix_transcripts_campaign_channel_time",
    Transcript.campaign_id,
    Transcript.channel_id,
    Transcript.created_at,
)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index(
            "ix_activity_logs_campaign_scene_time",
            "campaign_id",
            "scene_id",
            "created_at",
        ),
    )


# -----------------------------
# Phase 6: Content ingestion
# -----------------------------


class NodeType(str, enum.Enum):
    location = "location"
    npc = "npc"
    encounter = "encounter"
    lore = "lore"


class ContentNode(Base):
    __tablename__ = "content_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    node_type: Mapped[NodeType] = mapped_column(SAEnum(NodeType), index=True)
    title: Mapped[str] = mapped_column(String(200))
    # Player-visible text only; GM-only content must never be surfaced to players/LLM
    player_text: Mapped[str] = mapped_column(Text)
    # GM-only notes; never included in prompts or responses
    gm_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-form tags/keywords for retrieval filtering (list of strings)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index(
            "ix_content_nodes_campaign_type_title",
            "campaign_id",
            "node_type",
            "title",
        ),
    )


# -----------------------------
# Phase 8: Pending Actions
# -----------------------------


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    # Correlates a planner/orchestrator request end-to-end
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Store the executor ToolCallChain JSON for confirm/apply
    chain: Mapped[dict] = mapped_column(JSON)
    # Store preview strings for quick display without recomputation
    mechanics: Mapped[str] = mapped_column(Text)
    narration: Mapped[str] = mapped_column(Text)
    # Link to associated transcripts created during proposal
    player_tx_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bot_tx_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activity_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("activity_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Idempotency key computed from normalized ToolCallChain JSON
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index(
            "ix_pending_scene_user_time",
            "scene_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ux_pending_scene_user_dedup",
            "scene_id",
            "user_id",
            "dedup_hash",
            unique=True,
        ),
    )


# -----------------------------
# Phase 9: Event Ledger
# -----------------------------


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column("event_id", Integer, primary_key=True, autoincrement=True)
    id = synonym("event_id")

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    replay_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column("event_type", String(64), nullable=False)
    type = synonym("event_type")
    event_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    world_time: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    wall_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    prev_event_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    payload_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    idempotency_key: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    execution_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    request_id = synonym("execution_request_id")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    migrator_applied_from: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("campaign_id", "replay_ordinal", name="ux_events_campaign_replay"),
        UniqueConstraint("campaign_id", "idempotency_key", name="ux_events_campaign_idempotency"),
        Index(
            "ix_events_campaign_replay",
            "campaign_id",
            "replay_ordinal",
        ),
        Index(
            "ix_events_campaign_wall_time",
            "campaign_id",
            "wall_time_utc",
        ),
        Index(
            "ix_events_campaign_actor",
            "campaign_id",
            "actor_id",
        ),
        Index(
            "ix_events_plan",
            "plan_id",
        ),
        Index(
            "ix_events_execution_request",
            "execution_request_id",
        ),
    )


# Dense replay ordinal trigger DDL
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
                    (
                        SELECT replay_ordinal
                        FROM events
                        WHERE campaign_id = NEW.campaign_id
                        ORDER BY replay_ordinal DESC
                        LIMIT 1
                    ),
                    -1
                ) + 1
            ) THEN
                RAISE(ABORT, 'replay_ordinal must form a dense sequence per campaign')
        END;
END;
"""


@sa_event.listens_for(Event.__table__, "after_create")
def _create_events_replay_trigger(target, connection, **kw) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.execute(text(_POSTGRES_REPLAY_FN_SQL))
        connection.execute(text(_POSTGRES_REPLAY_TRIGGER_SQL))
    elif dialect == "sqlite":
        connection.execute(text(_SQLITE_REPLAY_TRIGGER_SQL))


@sa_event.listens_for(Event.__table__, "before_drop")
def _drop_events_replay_trigger(target, connection, **kw) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.execute(text(f"DROP TRIGGER IF EXISTS {_EVENTS_REPLAY_TRIGGER} ON events"))
        connection.execute(text(f"DROP FUNCTION IF EXISTS {_EVENTS_REPLAY_TRIGGER_FN}()"))
    elif dialect == "sqlite":
        connection.execute(text(f"DROP TRIGGER IF EXISTS {_EVENTS_REPLAY_TRIGGER}"))


# -----------------------------
# Phase 10: Encounters & Turns
# -----------------------------


class EncounterStatus(str, enum.Enum):
    setup = "setup"
    active = "active"
    ended = "ended"


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    status: Mapped[EncounterStatus] = mapped_column(
        SAEnum(EncounterStatus), default=EncounterStatus.setup, index=True
    )
    round: Mapped[int] = mapped_column(Integer, default=1)
    active_idx: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Combatant(Base):
    __tablename__ = "combatants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    initiative: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hp: Mapped[int] = mapped_column(Integer, default=0)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    token_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Stable order to break ties and to preserve insertion order during setup
    order_idx: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index(
            "ix_combatants_encounter_order",
            "encounter_id",
            "initiative",
            "order_idx",
        ),
    )
