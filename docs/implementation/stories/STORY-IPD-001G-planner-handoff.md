# STORY-IPD-001G — Planner integration handoff (AskReport → Plan)

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Planner WG

## Summary
When enabled, planner accepts AskReport; otherwise use existing inputs. Add adapters and parity tests.

## Acceptance Criteria
- Adapter maps AskReport to current planner inputs with no behavioral regressions.
- Feature flag gates the new path; preview/apply parity tests pass.

## Tasks
- [ ] TASK-IPD-ADAPT-19 — Implement AskReport → planner adapter.
- [ ] TASK-IPD-INTEG-20 — Integration tests around roll/check/attack intents.

## Definition of Ready
- Test fixtures prepared.

## Definition of Done
- Zero-diff confirmed in preview output.

## Test Plan
- Golden parity tests comparing legacy vs AskReport-adapted planner inputs.

## Observability
- Counters for adapter path usage, gated by feature flags.

## Risks & Mitigations
- Hidden regressions: broaden fixture coverage and add smoke runs.

## Dependencies
- Story A (contracts) and Story B (/ask handler) deliverables.

## Feature Flags
- features.ask_planner_handoff (default=false)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 5 — Planner Handoff

---

## Alignment analysis — IPD↔CDA (embedded)

- When enabling planner handoff, compute candidate idempotency key v2 inputs early (plan_id, tool_name, ruleset_version, args_json) to be ready for CDA integration; do not persist until CDA events are enabled.
