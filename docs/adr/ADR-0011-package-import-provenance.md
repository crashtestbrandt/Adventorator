# ADR-0011 Package Import Provenance & Origin Metadata

Status: Proposed  
Date: 2025-09-21  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Imported content must be traceable to immutable source files for reproducibility and trust.

## Decision
- Each entity/edge/chunk stores provenance: {package_id, source_path, file_hash}.
- ImportLog records ordered deterministic steps (phase, object_type, stable_id).
- Collision (same stable_id, different hash) hard-fails import.
- Synthetic seed events mirror functional seed state (ImportLog for audit detail).
- Signing & dependency resolution deferred but manifest fields reserved.

## Consequences
Pros:
- Enables diffing across forks.
- Assures integrity checks.

Cons:
- Slight storage overhead.

## Follow-Up
- Transparency log & signature policy ADR once registry introduced.