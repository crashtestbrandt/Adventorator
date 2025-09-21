# ADR-0006 Deterministic Event Envelope & Hash Chain

Status: Proposed  
Date: 2025-09-21  
Related Architecture: ARCH-CDA-001, ARCH-AVA-001  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Legacy events lacked a canonical serialization, deterministic ordering guarantees, or tamper-evident chaining. Auditability and replay fidelity require an immutable, verifiable event ledger.

## Decision
Adopt an extended event envelope:
- Dense `replay_ordinal` (unique, gap-free per campaign).
- Hash chain: `prev_event_hash` (32 zero bytes for genesis) + `payload_hash` (SHA-256 canonical JSON).
- Canonical JSON (see ADR-0007) for payload hashing.
- Idempotency key (first 16 bytes of composite SHA-256) prevents duplicate application.
- Genesis event `campaign.genesis` has published expected hash.
- DB constraints: unique (campaign_id, replay_ordinal) and (campaign_id, idempotency_key).

## Consequences
Pros:
- Strong tamper evidence.
- Deterministic replay enables reproducible state_digest.
- Natural audit boundary for snapshot cuts.

Cons:
- Slight storage overhead (hash fields).
- Requires strict encoder discipline.

## Alternatives Rejected
- Relying on auto-increment IDs (not gap-free).
- Soft hash logging (no enforcement) — insufficient integrity guarantees.

## Compliance / Enforcement
- Alembic migration adds fields & constraints.
- Trigger enforces dense replay_ordinal.
- CI test: hash chain continuity + genesis hash match.

## Follow-Up
- Integrate hash chain verification in snapshot restore path.
- Extend to compaction meta-events (reserved).