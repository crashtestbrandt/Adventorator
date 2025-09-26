# STORY-IPD-001F — Logging, metrics, and ActivityLog linkage

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Partially Done (not properly initiated)
Owner: Observability WG

## Summary
Standardize logs and counters for /ask and tagging; integrate with ActivityLog when Phase 6 assets exist.

## Acceptance Criteria
- Structured logs: initiated/completed and rejection reasons; counters like `ask.received`, `ask.failed`, `ask.tags.count`, `kb.lookup.hit/miss`.
- ActivityLog story linkage mirrors AVA Phase 6 patterns; tests assert metric increments.
- Ask audit record persistence path is gated by `features.activity_log` and applies redaction per Story H when enabled.

## Tasks
- [x] TASK-IPD-LOG-16 — Add structured logging via repo helpers. (Present in `/ask` flow and KB adapter)
- [x] TASK-IPD-METRIC-17 — Add counters and reset/get helpers in tests. (ask.*, kb.* counters exist; tests assert increments)
- [ ] TASK-IPD-ACTLOG-18 — Wire ActivityLog entries when feature enabled. (Pending; add behind `features.activity_log`)

## Definition of Ready
- Observability acceptance criteria reviewed.
- Alignment with CDA observability taxonomy documented (reusing `events.*` patterns where applicable when events enable later).

## Definition of Done
- Logging guide references new events and owners.
- ActivityLog linkage added behind flag with tests and redaction compliance notes.
- Metrics documented in observability guide with budget expectations and alerting hints.

## Test Plan
- Unit tests for metric increments and presence of key log fields.

## Observability
- Counters: ask.*, kb.*; Structured log events at INFO with keys.
- Traces
	- add span `interactions/ask.handle` with tracing backend.

Note on status: This story was not formally initiated; metrics/logging were implemented opportunistically alongside other work. ActivityLog linkage and tracing remain open.

## Risks & Mitigations
- Over-logging PII: use redaction filters from Story H; review log keys.

## Dependencies
- Story B (/ask handler) and Story H (privacy redaction).

## Feature Flags
- Piggybacks on features.improbability_drive and sub-flags.

## Traceability
---

Note: Portions of this story (structured logs, counters) were started alongside Stories B/C/D without formal initiation. This document updates status and clarifies the remaining ActivityLog linkage work.

## Alignment analysis — IPD↔CDA (embedded)

- Adopt CDA event observability patterns (e.g., chain tip, idempotency) when events are enabled; for now keep `/ask` observability isolated and privacy‑safe.
- Epic: EPIC-IPD-001
- Implementation Plan: spans Phases 1, 6
