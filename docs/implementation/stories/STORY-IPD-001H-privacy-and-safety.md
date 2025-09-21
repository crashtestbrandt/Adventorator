# STORY-IPD-001H — Privacy, redaction, and safety

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Privacy/Safety WG

## Summary
Implement PI/PII redaction for logs, bounded context windows, and configurable retention.

## Acceptance Criteria
- Redaction in logs enabled by default; opt-out documented.
- Size/time limits configurable; violations logged and rejected safely.

## Tasks
- [ ] TASK-IPD-PRIV-21 — Redaction filters for logs and AskReport persistence.
- [ ] TASK-IPD-LIMITS-22 — Enforce input size/time bounds with metrics.
- [ ] TASK-IPD-TEST-23 — Tests for redaction and bounds.

## Definition of Ready
- Redaction policy approved; bounds defined.

## Definition of Done
- Redaction filters applied in observability and storage paths; tests green.

## Test Plan
- Unit tests for redaction of PII-like tokens and limit enforcement.

## Observability
- Metrics for limit violations and redaction occurrences (counts only, not content).

## Risks & Mitigations
- Over-redaction: provide allowlist and thorough tests.

## Dependencies
- Story F (observability hooks) and Story B (/ask handler).

## Feature Flags
- Inherits from features.improbability_drive; specific toggles may be added if needed.

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 6 — Privacy/Redaction & Operational Hardening
