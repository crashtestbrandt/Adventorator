"""Utilities for the deterministic event ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import models

GENESIS_EVENT_TYPE = "campaign.genesis"
GENESIS_PREVIOUS_HASH = b"\x00" * 32


def _canonical_payload_bytes(payload: Mapping[str, Any] | None) -> bytes:
    """Serialize payload deterministically for hashing."""

    if payload is None:
        payload = {}
    try:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except TypeError as exc:  # pragma: no cover - defensive; tests cover happy path
        raise ValueError("Payload must be JSON-serializable") from exc
    return serialized.encode("utf-8")


def compute_payload_hash(payload: Mapping[str, Any] | None) -> bytes:
    """Compute SHA-256 over the canonical payload representation."""

    return hashlib.sha256(_canonical_payload_bytes(payload)).digest()


GENESIS_PAYLOAD_HASH = compute_payload_hash({})


def compute_idempotency_key(
    *,
    campaign_id: int,
    event_type: str,
    payload: Mapping[str, Any] | None,
    plan_id: str | None = None,
    execution_request_id: str | None = None,
) -> bytes:
    """Return a stable 16-byte idempotency key prefix."""

    h = hashlib.sha256()
    h.update(str(campaign_id).encode())
    h.update(b"\x1f")
    h.update(event_type.encode())
    h.update(b"\x1f")
    if plan_id:
        h.update(plan_id.encode())
    h.update(b"\x1f")
    if execution_request_id:
        h.update(execution_request_id.encode())
    h.update(b"\x1f")
    h.update(_canonical_payload_bytes(payload))
    return h.digest()[:16]


def _genesis_idempotency_key(campaign_id: int) -> bytes:
    h = hashlib.sha256()
    h.update(f"genesis:{campaign_id}".encode())
    return h.digest()[:16]


async def get_chain_tip(session: AsyncSession, *, campaign_id: int) -> tuple[int, bytes] | None:
    """Return the latest replay ordinal and payload hash for a campaign."""

    q = await session.execute(
        select(models.Event.replay_ordinal, models.Event.payload_hash)
        .where(models.Event.campaign_id == campaign_id)
        .order_by(models.Event.replay_ordinal.desc())
        .limit(1)
    )
    row = q.first()
    if row is None:
        return None
    return int(row.replay_ordinal), bytes(row.payload_hash)


async def create_genesis_event(
    session: AsyncSession,
    *,
    campaign_id: int,
    wall_time_utc: datetime | None = None,
) -> models.Event:
    """Insert the genesis event for a campaign; caller ensures none exists."""

    wall_time = wall_time_utc or datetime.now(timezone.utc)
    event = models.Event(
        campaign_id=campaign_id,
        scene_id=None,
        replay_ordinal=0,
        event_type=GENESIS_EVENT_TYPE,
        event_schema_version=1,
        world_time=0,
        wall_time_utc=wall_time,
        prev_event_hash=GENESIS_PREVIOUS_HASH,
        payload_hash=GENESIS_PAYLOAD_HASH,
        idempotency_key=_genesis_idempotency_key(campaign_id),
        actor_id=None,
        plan_id=None,
        execution_request_id=None,
        approved_by=None,
        payload={},
        migrator_applied_from=None,
    )
    session.add(event)
    await session.flush()
    return event


async def ensure_genesis_event(
    session: AsyncSession,
    *,
    campaign_id: int,
    wall_time_utc: datetime | None = None,
) -> models.Event:
    """Idempotently create the genesis event if missing."""

    existing = await session.execute(
        select(models.Event).where(
            models.Event.campaign_id == campaign_id,
            models.Event.replay_ordinal == 0,
        )
    )
    event = existing.scalar_one_or_none()
    if event is not None:
        return event
    return await create_genesis_event(session, campaign_id=campaign_id, wall_time_utc=wall_time_utc)
