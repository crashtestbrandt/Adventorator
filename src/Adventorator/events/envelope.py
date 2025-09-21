"""Event envelope helpers for the deterministic ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from Adventorator import models

CANONICAL_JSON_SEPARATORS = (",", ":")

GENESIS_EVENT_TYPE = "campaign.genesis"
GENESIS_PREV_EVENT_HASH = b"\x00" * 32
GENESIS_PAYLOAD: Mapping[str, Any] = {}
GENESIS_PAYLOAD_CANONICAL = b"{}"
GENESIS_PAYLOAD_HASH = hashlib.sha256(GENESIS_PAYLOAD_CANONICAL).digest()
GENESIS_IDEMPOTENCY_KEY = b"\x00" * 16
GENESIS_SCHEMA_VERSION = 1


def canonical_json_bytes(payload: Mapping[str, Any] | None) -> bytes:
    """Encode payload using the provisional canonical policy.

    The full canonical encoder (ordering, NFC normalization, integer-only policy)
    will be delivered in STORY-CDA-CORE-001B. For STORY-CDA-CORE-001A we ensure
    stable key ordering and compact separators to guarantee deterministic hashes
    for simple payloads like the genesis `{}` envelope.
    """

    if payload is None:
        payload = {}
    # Ensure ascii to avoid platform differences until unicode normalization
    # lands with the canonical encoder story.
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=CANONICAL_JSON_SEPARATORS,
        sort_keys=True,
    ).encode("utf-8")


def compute_payload_hash(payload: Mapping[str, Any] | None) -> bytes:
    """Return the SHA-256 digest of the canonical payload representation."""

    return hashlib.sha256(canonical_json_bytes(payload)).digest()


def compute_idempotency_key(
    *,
    campaign_id: int,
    event_type: str,
    execution_request_id: str | None,
    plan_id: str | None,
    payload: Mapping[str, Any] | None,
    replay_ordinal: int,
) -> bytes:
    """Derive a deterministic 16-byte idempotency prefix.

    The eventual ADR-specified composition includes additional executor inputs.
    For this initial substrate we base the prefix on the core identifiers we
    already persist so the uniqueness constraint is enforceable today.
    """

    material_parts: list[bytes] = [
        str(campaign_id).encode("utf-8"),
        event_type.encode("utf-8"),
        (execution_request_id or "").encode("utf-8"),
        (plan_id or "").encode("utf-8"),
        str(replay_ordinal).encode("utf-8"),
        canonical_json_bytes(payload),
    ]
    digest = hashlib.sha256(b"|".join(material_parts)).digest()
    return digest[:16]


@dataclass(slots=True, frozen=True)
class GenesisEvent:
    """Simple data container for the genesis event envelope."""

    campaign_id: int
    scene_id: int | None = None

    def instantiate(self) -> models.Event:
        """Create an ORM instance populated with genesis invariants."""

        now = datetime.now(timezone.utc)
        return models.Event(
            campaign_id=self.campaign_id,
            scene_id=self.scene_id,
            replay_ordinal=0,
            type=GENESIS_EVENT_TYPE,
            event_schema_version=GENESIS_SCHEMA_VERSION,
            world_time=0,
            wall_time_utc=now,
            prev_event_hash=GENESIS_PREV_EVENT_HASH,
            payload_hash=GENESIS_PAYLOAD_HASH,
            idempotency_key=GENESIS_IDEMPOTENCY_KEY,
            actor_id=None,
            plan_id=None,
            execution_request_id=None,
            approved_by=None,
            payload=dict(GENESIS_PAYLOAD),
            migrator_applied_from=None,
        )


__all__ = [
    "GENESIS_EVENT_TYPE",
    "GENESIS_IDEMPOTENCY_KEY",
    "GENESIS_PAYLOAD",
    "GENESIS_PAYLOAD_CANONICAL",
    "GENESIS_PAYLOAD_HASH",
    "GENESIS_PREV_EVENT_HASH",
    "GENESIS_SCHEMA_VERSION",
    "GenesisEvent",
    "canonical_json_bytes",
    "compute_idempotency_key",
    "compute_payload_hash",
]
