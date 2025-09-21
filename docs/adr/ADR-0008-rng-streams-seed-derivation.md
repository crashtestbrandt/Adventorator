# ADR-0008 RNG Streams & Seed Derivation

## Status
Proposed (2025-09-21)

## Metadata
Depends On: ADR-0006, ADR-0007  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Randomness must be reproducible for audits, drift detection, and fork equivalence.

## Decision
- Single campaign master seed (128-bit).
- HKDF-SHA256 derivation per event with info: `"AV1|<ruleset_version>|<tool_version>|<stream>|<replay_ordinal_be8>"`.
- Rolls derived deterministically (SHA256(base_seed||i)).
- Record stream metadata + inputs + results in event payload.
- No ambient RNG calls allowed in executor path.

## Rationale
Guarantee reproducible randomness tied to ledger ordering and tool context to support audit, debugging, and rollback.

## Consequences
Pros:
- Full reproducibility.
- Supports multi-stream isolation.

Cons:
- Tool authors must integrate helper explicitly.

## References
- ADR-0006 Event Envelope & Hash Chain
- HKDF (RFC 5869) — derivation method

## Enforcement
- Static analysis to detect `random` / `secrets` misuse.
- Unit tests confirm deterministic roll sequences.

## Follow-Up
- Extend to simulation ticks (phase / turn) when added.
