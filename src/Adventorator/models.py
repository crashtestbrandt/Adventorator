# models.py

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


Index(
    "ix_transcripts_campaign_channel_time",
    Transcript.campaign_id,
    Transcript.channel_id,
    Transcript.created_at,
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
    scene_id: Mapped[int] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index(
            "ix_events_scene_time",
            "scene_id",
            "created_at",
        ),
        Index(
            "ix_events_scene_actor_time",
            "scene_id",
            "actor_id",
            "created_at",
        ),
    )


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
