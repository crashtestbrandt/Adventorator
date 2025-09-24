"""Event envelope helpers for the deterministic ledger."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from Adventorator import models
from Adventorator.canonical_json import (
    canonical_json_bytes as canonical_json_bytes_full,
)
from Adventorator.canonical_json import (
    compute_canonical_hash,
)

CANONICAL_JSON_SEPARATORS = (",", ":")

GENESIS_EVENT_TYPE = "campaign.genesis"
GENESIS_PREV_EVENT_HASH = b"\x00" * 32
GENESIS_PAYLOAD: Mapping[str, Any] = {}
GENESIS_PAYLOAD_CANONICAL = b"{}"
GENESIS_PAYLOAD_HASH = hashlib.sha256(GENESIS_PAYLOAD_CANONICAL).digest()
GENESIS_IDEMPOTENCY_KEY = b"\x00" * 16
GENESIS_SCHEMA_VERSION = 1


def canonical_json_bytes(payload: Mapping[str, Any] | None) -> bytes:
    """Encode payload using the canonical policy from ADR-0007.

    This function now uses the full canonical encoder implementing:
    - UTF-8 NFC Unicode normalization
    - Lexicographic key ordering
    - Null field elision
    - Integer-only numeric policy (rejects floats/NaN)
    - Compact separators

    For STORY-CDA-CORE-001B, this replaces the provisional implementation
    used in STORY-CDA-CORE-001A while maintaining backward compatibility
    for simple payloads like the genesis `{}` envelope.
    """
    # Use the full canonical encoder from the dedicated module
    return canonical_json_bytes_full(payload)


def compute_payload_hash(payload: Mapping[str, Any] | None) -> bytes:
    """Return the SHA-256 digest of the canonical payload representation."""

    return hashlib.sha256(canonical_json_bytes(payload)).digest()


def compute_envelope_hash(
    *,
    campaign_id: int,
    scene_id: int | None,
    replay_ordinal: int,
    event_type: str,
    event_schema_version: int,
    world_time: int,
    wall_time_utc: datetime,
    prev_event_hash: bytes,
    payload_hash: bytes,
    idempotency_key: bytes,
) -> bytes:
    """Hash the full immutable envelope fields.

    This binds the chain to the entire prior envelope instead of only the
    payload hash. The canonical ordering below must remain stable.
    NOTE: Not yet persisted; integration occurs in STORY-CDA-CORE-001A step 2.
    """

    # Compose a canonical, delimiter-robust binary representation.
    # Use length-prefix framing to avoid ambiguity.
    parts: list[bytes] = []

    def add(label: str, value_bytes: bytes):
        # label|len|value for forward compatibility / debugging
        parts.append(label.encode("utf-8"))
        parts.append(len(value_bytes).to_bytes(4, "big", signed=False))
        parts.append(value_bytes)

    add("campaign_id", str(campaign_id).encode("utf-8"))
    add("scene_id", ("" if scene_id is None else str(scene_id)).encode("utf-8"))
    add("replay_ordinal", str(replay_ordinal).encode("utf-8"))
    add("event_type", event_type.encode("utf-8"))
    add("schema_version", str(event_schema_version).encode("utf-8"))
    add("world_time", str(world_time).encode("utf-8"))
    # Use ISO format with 'Z' for UTC determinism
    add("wall_time_utc", wall_time_utc.replace(tzinfo=timezone.utc).isoformat().encode("utf-8"))
    add("prev_event_hash", prev_event_hash)
    add("payload_hash", payload_hash)
    add("idempotency_key", idempotency_key)

    return hashlib.sha256(b"".join(parts)).digest()


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

    # Length-prefixed binary framing to avoid delimiter collision ambiguity.
    components: list[tuple[str, bytes]] = [
        ("campaign_id", str(campaign_id).encode("utf-8")),
        ("event_type", event_type.encode("utf-8")),
        ("execution_request_id", (execution_request_id or "").encode("utf-8")),
        ("plan_id", (plan_id or "").encode("utf-8")),
        ("replay_ordinal", str(replay_ordinal).encode("utf-8")),
        ("payload", canonical_json_bytes(payload)),
    ]
    framed: list[bytes] = []
    for label, value in components:
        framed.append(label.encode("utf-8"))
        framed.append(len(value).to_bytes(4, "big", signed=False))
        framed.append(value)
    digest = hashlib.sha256(b"".join(framed)).digest()
    return digest[:16]


def compute_idempotency_key_v2(
    *,
    plan_id: str | None,
    campaign_id: int,
    event_type: str,
    tool_name: str | None,
    ruleset_version: str | None,
    args_json: Mapping[str, Any] | None,
) -> bytes:
    """Derive a deterministic 16-byte idempotency key per STORY-CDA-CORE-001D.

    Implements the ADR-specified composition for true retry collapse:
    SHA256(plan_id || campaign_id || event_type || tool_name ||
           ruleset_version || canonical(args_json))[:16]

    This composition excludes replay_ordinal and execution_request_id to enable
    proper idempotency - the same logical operation should produce the same key
    regardless of retry attempts.

    Args:
        plan_id: Unique plan identifier (nullable for non-planned events)
        campaign_id: Campaign identifier
        event_type: Event type string
        tool_name: Name of the tool being executed (nullable)
        ruleset_version: Version of ruleset being used (nullable)
        args_json: Canonical JSON-serializable arguments (nullable)

    Returns:
        16-byte deterministic key prefix
    """
    # Length-prefixed binary framing to avoid delimiter collision ambiguity.
    # Order follows acceptance criteria specification.

    # Special handling for args_json to distinguish None from empty dict
    if args_json is None:
        args_bytes = b"<null>"  # Sentinel value for None
    else:
        args_bytes = canonical_json_bytes(args_json)

    components: list[tuple[str, bytes]] = [
        ("plan_id", (plan_id or "").encode("utf-8")),
        ("campaign_id", str(campaign_id).encode("utf-8")),
        ("event_type", event_type.encode("utf-8")),
        ("tool_name", (tool_name or "").encode("utf-8")),
        ("ruleset_version", (ruleset_version or "").encode("utf-8")),
        ("args_json", args_bytes),
    ]
    framed: list[bytes] = []
    for label, value in components:
        framed.append(label.encode("utf-8"))
        framed.append(len(value).to_bytes(4, "big", signed=False))
        framed.append(value)
    digest = hashlib.sha256(b"".join(framed)).digest()
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


class HashChainMismatchError(Exception):
    """Raised when hash chain verification detects corruption."""

    def __init__(self, ordinal: int, expected_hash: bytes, actual_hash: bytes):
        self.ordinal = ordinal
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Hash mismatch at ordinal {ordinal}: "
            f"expected {expected_hash.hex()[:16]}, got {actual_hash.hex()[:16]}"
        )


def verify_hash_chain(events: list) -> dict[str, Any]:
    """Verify hash chain integrity for a list of events.

    Args:
        events: List of Event model instances ordered by replay_ordinal

    Returns:
        dict: Verification summary with counts and status

    Raises:
        HashChainMismatchError: When a hash mismatch is detected
    """
    from Adventorator.action_validation.logging_utils import log_event
    from Adventorator.metrics import inc_counter

    if not events:
        return {"verified_count": 0, "status": "success", "chain_length": 0}

    # Sort by replay_ordinal to ensure proper chain traversal
    events = sorted(events, key=lambda e: e.replay_ordinal)

    expected_prev_hash = GENESIS_PREV_EVENT_HASH
    verified_count = 0

    for event in events:
        # Check that prev_event_hash matches expected value
        if event.prev_event_hash != expected_prev_hash:
            # Log structured mismatch event
            log_event(
                "event",
                "chain_mismatch",
                campaign_id=event.campaign_id,
                replay_ordinal=event.replay_ordinal,
                expected_hash=expected_prev_hash.hex()[:16],
                actual_hash=event.prev_event_hash.hex()[:16],
                event_type=event.type,
            )

            # Increment mismatch metric
            inc_counter("events.hash_mismatch")

            # Raise exception with details
            raise HashChainMismatchError(
                ordinal=event.replay_ordinal,
                expected_hash=expected_prev_hash,
                actual_hash=event.prev_event_hash,
            )

        # Compute the envelope hash of this event for the next iteration
        expected_prev_hash = compute_envelope_hash(
            campaign_id=event.campaign_id,
            scene_id=event.scene_id,
            replay_ordinal=event.replay_ordinal,
            event_type=event.type,
            event_schema_version=event.event_schema_version,
            world_time=event.world_time,
            wall_time_utc=event.wall_time_utc,
            prev_event_hash=event.prev_event_hash,
            payload_hash=event.payload_hash,
            idempotency_key=event.idempotency_key,
        )

        verified_count += 1

    return {"verified_count": verified_count, "status": "success", "chain_length": len(events)}


async def get_chain_tip(session, campaign_id: int) -> tuple[int, bytes] | None:
    """Get the current chain tip for a campaign.

    Args:
        session: Database session
        campaign_id: Campaign identifier

    Returns:
        tuple: (replay_ordinal, payload_hash) of the latest event,
               or None if no events exist
    """
    from sqlalchemy import select

    from Adventorator import models

    # Get the event with the highest replay_ordinal for this campaign
    stmt = (
        select(models.Event.replay_ordinal, models.Event.payload_hash)
        .where(models.Event.campaign_id == campaign_id)
        .order_by(models.Event.replay_ordinal.desc())
        .limit(1)
    )
    # Execute and fetch first row efficiently
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        return None
    # Row supports tuple access; avoid attribute overhead
    return int(row[0]), row[1]


def log_event_applied(
    *,
    event_id: int,
    campaign_id: int,
    replay_ordinal: int,
    event_type: str,
    idempotency_key: bytes,
    payload_hash: bytes,
    plan_id: str | None = None,
    execution_request_id: str | None = None,
    latency_ms: float | None = None,
) -> None:
    """Log structured event application with required metadata.

    This emits the structured log format specified in the acceptance criteria
    for STORY-CDA-CORE-001E observability.
    """
    from Adventorator.action_validation.logging_utils import log_event
    from Adventorator.metrics import inc_counter

    # Required structured log fields per acceptance criteria
    log_data = {
        "event_id": event_id,
        "replay_ordinal": replay_ordinal,
        "chain_tip_hash": payload_hash.hex()[:16],  # First 16 chars for readability
        "idempotency_key_hex": idempotency_key.hex(),
        "event_type": event_type,
        "campaign_id": campaign_id,
    }

    # Optional fields
    if plan_id:
        log_data["plan_id"] = plan_id
    if execution_request_id:
        log_data["execution_request_id"] = execution_request_id
    if latency_ms is not None:
        log_data["latency_ms"] = latency_ms

    # Log structured event
    log_event("event", "applied", **log_data)

    # Increment metrics
    inc_counter("events.applied")

    if latency_ms is not None:
        # Record latency in histogram (simplified - just record the value)
        # In a real system this would use proper histogram buckets
        inc_counter("event.apply.latency_ms", int(latency_ms))


def log_idempotent_reuse(
    *,
    event_id: int,
    campaign_id: int,
    idempotency_key: bytes,
    plan_id: str | None = None,
) -> None:
    """Log when an event creation was skipped due to idempotency."""
    from Adventorator.action_validation.logging_utils import log_event
    from Adventorator.metrics import inc_counter

    log_event(
        "event",
        "idempotent_reuse",
        event_id=event_id,
        campaign_id=campaign_id,
        idempotency_key_hex=idempotency_key.hex(),
        plan_id=plan_id,
    )

    inc_counter("events.idempotent_reuse")


__all__ = [
    "GENESIS_EVENT_TYPE",
    "GENESIS_IDEMPOTENCY_KEY",
    "GENESIS_PAYLOAD",
    "GENESIS_PAYLOAD_CANONICAL",
    "GENESIS_PAYLOAD_HASH",
    "GENESIS_PREV_EVENT_HASH",
    "GENESIS_SCHEMA_VERSION",
    "GenesisEvent",
    "HashChainMismatchError",
    "canonical_json_bytes",
    "compute_canonical_hash",
    "compute_idempotency_key",
    "compute_idempotency_key_v2",
    "compute_payload_hash",
    "compute_envelope_hash",
    "verify_hash_chain",
    "get_chain_tip",
    "log_event_applied",
    "log_idempotent_reuse",
]
