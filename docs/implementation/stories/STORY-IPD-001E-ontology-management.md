# STORY-IPD-001E — Ontology management and versioning

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Ontology/Contracts WG

## Summary
Define ontology files under `contracts/` or `prompts/` with versioning, validation script, and governance.

## Acceptance Criteria
- Ontology schema and linter in place; changes validated via CI script (`scripts/validate_prompts_and_contracts.py`).
- Tags referenced by NLU and planner documented with migration guidance.

## Tasks
- [ ] TASK-IPD-ONTO-13 — Author ontology schema and seed ontology.
- [ ] TASK-IPD-VALIDATE-14 — Extend validation script to include ontology checks.
- [ ] TASK-IPD-DOCS-15 — Author ontology guide under docs/architecture or docs/dev.

## Definition of Ready
- Stakeholders aligned on taxonomy scope.

## Definition of Done
- CI runs ontology validation; docs linked here.

## Test Plan
- Validator unit tests; schema round-trip for sample ontology files.

## Observability
- None; governance docs updated.

## Risks & Mitigations
- Tag churn: require versioning and migration notes with each change.

## Dependencies
- Story C (tagging) consumers; validation script in scripts/.

## Feature Flags
- N/A (docs and scripts)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 4 — Ontology Management & Validation
