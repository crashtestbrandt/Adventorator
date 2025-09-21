# STORY-IPD-001B — /ask command handler and responder

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Interactions/Responder WG

## Summary
Add `/ask` handler using registry decorators and responder abstraction; wire config gating and minimal observability stubs. No NLU/tagging logic in this story; that lands in Story C.

## Acceptance Criteria
- `/ask` available behind `features.ask` and `features.improbability_drive`.
- When disabled, returns a clear “disabled” message; no behavior change to existing commands.
- When enabled, accepts input and returns an ephemeral acknowledgement (no action/target inference in this story).
- Handler lives alongside existing interaction handlers, using `@slash_command` and `inv.responder.send(...)` as per AGENTS.md.

## Tasks
- [ ] TASK-IPD-HANDLER-04 — Implement `/ask` handler with config gating and responder usage.
- [ ] TASK-IPD-OBS-05 — Add structured logs and counters (e.g., `ask.received`, `ask.ask_report.emitted`).
- [ ] TASK-IPD-TEST-06 — Web CLI and Discord tests for enabled/disabled behavior.
 - [ ] TASK-IPD-DOC-07 — Add developer docs for how to enable/disable flags and verify observability.

## Definition of Ready
- Command name/UX reviewed; strings added to prompts/localization if needed.

## Definition of Done
- Tests confirm flag gating and output consistency.

## Test Plan
- CLI/Discord integration tests validating outputs and lack of side effects when disabled.
- Observability unit tests for counter increments.

## Observability
- Logs: ask.initiated, ask.completed, ask.failed
- Metrics: ask.received, ask.ask_report.emitted, ask.failed
 - Consider adding a correlation/request_id field consistent with ActivityLog patterns.

## Risks & Mitigations
- User confusion: return concise summaries; feature flag off by default.

## Dependencies
- ADR-0005 (contracts/flags/rollout) and Story A (contracts/flags) are in place.

## Feature Flags
- features.improbability_drive
- features.ask

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 1 — /ask Handler & Observability
