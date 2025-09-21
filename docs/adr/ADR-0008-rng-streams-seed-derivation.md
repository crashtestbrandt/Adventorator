# ADR-0008 RNG Streams & Seed Derivation

Status: Proposed  
Date: 2025-09-21  
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

## Consequences
Pros:
- Full reproducibility.
- Supports multi-stream isolation.

Cons:
- Tool authors must integrate helper explicitly.

## Enforcement
- Static analysis to detect `random` / `secrets` misuse.
- Unit tests confirm deterministic roll sequences.

## Future
- Extend to simulation ticks (phase / turn) when added.
