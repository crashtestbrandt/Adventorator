# ADR-0009 Capability & Approval Enforcement

## Status
Proposed (2025-09-21)

## Metadata
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Need permission boundaries (players vs GM vs system) and optional human-in-loop approvals for sensitive event types.

## Decision
- Roles, capabilities, role_capabilities, actor_role_assignments tables.
- Tool → required_capabilities mapping.
- Executor guards event emission; DB CHECK enforces approved_by presence when requires_approval.
- Denies deferred (future explicit override layer).
- Minimal seeded roles: player (limited), gm (superset), system (restricted internal operations).

## Rationale
Introduce least-privilege gating and optional approval workflow to prevent unauthorized or premature state mutations.

## Consequences
Pros:
- Clear least privilege model.
- Audit trail of approvals.

Cons:
- Additional schema & join overhead.

## References
- ADR-0006 Event Envelope & Hash Chain (approval recorded in events)
- Principle of Least Privilege (Saltzer & Schroeder, 1975)

## Follow-Up
- Add negative authorization layer (denies) post-MVP.
- Health check validating role baseline.