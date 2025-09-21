# ADR-0010 Snapshot & Fork Lineage (No Merge)

## Status
Proposed (2025-09-21)

## Metadata
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Need branching for “what-if” / GM rehearsal without complexity of merges.

## Decision
- Fork = new campaign initialized from snapshot.
- Branch lineage via parent_snapshot_id chain; no merge support.
- replay_ordinal resets in fork.
- Snapshots store state_digest + events_hash_chain_tip + logical_snapshot_hash.

## Rationale
Provide safe, auditable experimentation branches without complexity of merge conflict resolution.

## Consequences
Pros:
- Simplifies audit logic.
- Avoids merge conflicts complexity.

Cons:
- Duplicate storage for divergent forks.
- No automated reconciliation.

## References
- ADR-0006 Event Envelope & Hash Chain (snapshot tip)
- ADR-0012 Event Versioning & Migration Protocol

## Follow-Up
- Evaluate cherry-pick meta-events when use-case volume justifies.