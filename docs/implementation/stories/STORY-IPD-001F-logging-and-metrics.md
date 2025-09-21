# STORY-IPD-001F — Logging, metrics, and ActivityLog linkage

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Observability WG

## Summary
Standardize logs and counters for /ask and tagging; integrate with ActivityLog when Phase 6 assets exist.

## Acceptance Criteria
- Structured logs: initiated/completed and rejection reasons; counters like `ask.received`, `ask.failed`, `ask.tags.count`, `kb.lookup.hit/miss`.
- ActivityLog story linkage mirrors AVA Phase 6 patterns; tests assert metric increments.

## Tasks
- [ ] TASK-IPD-LOG-16 — Add structured logging via repo helpers.
- [ ] TASK-IPD-METRIC-17 — Add counters and reset/get helpers in tests.
- [ ] TASK-IPD-ACTLOG-18 — Wire ActivityLog entries when feature enabled.

## Definition of Ready
- Observability acceptance criteria reviewed.

## Definition of Done
- Logging guide references new events and owners.

## Test Plan
- Unit tests for metric increments and presence of key log fields.

## Observability
- Counters: ask.*, kb.*; Structured log events at INFO with keys.
- Traces
	- add span `interactions/ask.handle` with tracing backend.

## Risks & Mitigations
- Over-logging PII: use redaction filters from Story H; review log keys.

## Dependencies
- Story B (/ask handler) and Story H (privacy redaction).

## Feature Flags
- Piggybacks on features.improbability_drive and sub-flags.

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: spans Phases 1, 6
