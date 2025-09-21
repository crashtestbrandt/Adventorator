# ADR-0006 Deterministic Event Envelope & Hash Chain

## Status
Proposed (2025-09-21)

## Metadata
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
 - Idempotency key (first 16 bytes of SHA-256 over length-prefixed components: campaign_id, event_type, execution_request_id, plan_id, replay_ordinal, canonical_payload) prevents duplicate application. Each component is framed as label || 4-byte big-endian length || value to avoid delimiter ambiguity.
- Genesis event `campaign.genesis` has published expected hash.
- DB constraints: unique (campaign_id, replay_ordinal) and (campaign_id, idempotency_key).

## Rationale
Provide tamper evidence, deterministic replay guarantees, and idempotent application to enable future snapshotting, migration safety, and fork reproducibility. Alternatives lacked enforceable integrity or replay determinism.

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

## References
- ADR-0007 Canonical JSON & Numeric Policy
- ADR-0012 Event Versioning & Migration Protocol (future evolution compatibility)
- NIST SP 800-90A (hash algorithm considerations)

## Follow-Up
- Integrate hash chain verification in snapshot restore path.
- Extend to compaction meta-events (reserved).