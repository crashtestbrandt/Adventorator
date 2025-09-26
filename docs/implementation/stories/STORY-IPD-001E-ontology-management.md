# STORY-IPD-001E — Ontology management and versioning

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Partially Done (not properly initiated)
Owner: Ontology/Contracts WG

## Summary
Define ontology files under `contracts/` or `prompts/` with versioning, validation script, and governance.

## Acceptance Criteria
- Ontology schema and linter in place; changes validated via CI script (`scripts/validate_prompts_and_contracts.py`).
- Tags referenced by NLU and planner documented with migration guidance.
 - Performance budget: Ontology validator completes within p95 ≤ 200ms for a typical medium-sized ontology file on CI hardware (or a recorded measurement is captured in the PR description if CI perf is not deterministic). This measures the validator's schema-check runtime, not NLU translation latency.

## Tasks
- [x] TASK-IPD-ONTO-13 — Author ontology schema and seed ontology. (Artifacts present under `contracts/ontology/` including `seed-v0_1.json`, `tag.v1.json`, `affordance.v1.json`.)
- [ ] TASK-IPD-VALIDATE-14 — Extend validation script to include ontology checks. (Pending; `scripts/validate_prompts_and_contracts.py` currently does not validate ontology artifacts.)
- [x] TASK-IPD-DOCS-15 — Author ontology guide under docs/architecture or docs/dev. (See `contracts/ontology/README.md`.)

## Definition of Ready
- Taxonomy scope is documented (categories, invariants, and expected affordance relationships) and aligned across related project plans (ontology, NLU, planner).
- Versioning approach is specified (e.g., `v1` schemas, seed `v0_1` support) with migration guidance drafted.
- Validation rules and failure modes are enumerated (duplicate handling, conflicts, normalization) consistent with repo governance.
- Deterministic fixtures prepared for happy/conflict cases under `tests/fixtures/ontology/` (or equivalent), sized to exercise the validator without adding external dependencies.
- CI integration approach for the validator is outlined (invocation path and failure conditions documented).

## Definition of Done
- CI runs ontology validation as part of the contracts/prompt checks; failures are actionable with clear messages.
- Ontology artifacts under `contracts/ontology/` validate cleanly (seed and example files); normalization and conflict policies are documented.
- Developer guide updated (location/format, versioning, invariants, failure handling, and how to run the validator locally).
- Measured performance recorded: p95 ≤ 200ms per typical medium-sized ontology file on CI hardware, or a PR note includes a recorded local measurement if CI timing is unreliable.
- Story links updated in the EPIC and traceability references.

## Test Plan
- Validator unit tests; schema round-trip for sample ontology files (valid/invalid/duplicate/conflict).
- Integration: CI job invokes `scripts/validate_prompts_and_contracts.py` and fails on ontology violations.
- Performance check (validator): capture p95 ≤ 200ms for validating a representative ontology file on CI hardware.
	- Clarification: this measures ontology validator runtime, not NLU translation; NLU parsing performance is covered in Stories B/C.
	- If CI timing is flaky, attach a recorded measurement from a representative developer machine in the PR.

## Observability
- None; governance docs updated.

## Risks & Mitigations
- Tag churn: require versioning and migration notes with each change.

Note on status: This story was not formally initiated; partial implementation resulted from cross-work to unblock NLU baselines and contract placement, leaving validator integration pending.

## Dependencies
- Story C (tagging) consumers; validation script in scripts/.

## Feature Flags
- N/A (docs and scripts)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 4 — Ontology Management & Validation
