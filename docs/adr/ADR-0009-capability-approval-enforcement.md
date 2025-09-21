# ADR-0009 Capability & Approval Enforcement

Status: Proposed  
Date: 2025-09-21  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Need permission boundaries (players vs GM vs system) and optional human-in-loop approvals for sensitive event types.

## Decision
- Roles, capabilities, role_capabilities, actor_role_assignments tables.
- Tool → required_capabilities mapping.
- Executor guards event emission; DB CHECK enforces approved_by presence when requires_approval.
- Denies deferred (future explicit override layer).
- Minimal seeded roles: player (limited), gm (superset), system (restricted internal operations).

## Consequences
Pros:
- Clear least privilege model.
- Audit trail of approvals.

Cons:
- Additional schema & join overhead.

## Follow-Up
- Add negative authorization layer (denies) post-MVP.
- Health check validating role baseline.