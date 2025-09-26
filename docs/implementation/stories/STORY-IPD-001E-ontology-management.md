# STORY-IPD-001E — Ontology management and versioning

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: In Progress — Validator + ontology unit tests implemented; docs (migration) & CI perf evidence pending
DoR Status: Ready (all prerequisites satisfied)
Owner: Ontology/Contracts WG

## Summary
Define ontology files under `contracts/` or `prompts/` with versioning, validation script, and governance.

Fixture separation note: Validator-focused fixtures live under `tests/fixtures/ontology/` (this story) and intentionally include invalid, duplicate, and conflict cases. They MUST remain separate from package import fixtures under `tests/fixtures/import/manifest/.../ontologies/` which model coherent, hash-stable bundles for the CDA importer stories (e.g., STORY-CDA-IMPORT-002D). Do not merge these directories; mixing would pollute manifest hash determinism and undermine negative test isolation.

## Acceptance Criteria
- Contract-first validator in place: Ontology artifacts under `contracts/ontology/` validate via `scripts/validate_prompts_and_contracts.py` and the Make target `make quality-artifacts`; failures are clear and actionable.
- Schema conformance: Each tag and affordance (from collections in `ontology/*.json`) validates against `contracts/ontology/tag.v1.json` and `contracts/ontology/affordance.v1.json` respectively. Unknown fields are rejected.
- Duplicate/conflict policy enforced at validation-time:
	- Identical duplicate definitions for the same `tag_id`/`affordance_id` across files are treated as idempotent (pass); conflicting definitions fail with a descriptive diff/hash hint.
- NLU/planner usage documented: Tags and canonical affordance mappings referenced by IPD are documented with migration guidance in `contracts/ontology/README.md`.
- CI integration: Quality gates (`make quality-gates`) execute ontology validation; PRs fail if any ontology violations are present.
- Performance budget: Validator schema-check runtime per typical medium-sized ontology file meets p95 ≤ 200ms on CI hardware, or the PR includes a recorded local measurement if CI timing is not deterministic. Measurement targets the validator only (not NLU translation).

## Implementation Plan (granular, test- and contract-first)

- [x] TASK-IPD-ONTO-13 — Schemas and seed artifacts
	- Artifacts: `contracts/ontology/tag.v1.json`, `contracts/ontology/affordance.v1.json`, legacy `seed-v0_1.json`, `contracts/ontology/README.md`
	- Exit criteria: Schemas present and referenced by importer tests; README outlines scope and invariants.
	- Owner: Ontology/Contracts WG

- [x] TASK-IPD-VALIDATE-14 — Extend contracts validator with ontology checks (DONE)
	- Code: `scripts/validate_prompts_and_contracts.py`
	- Subtasks:
		- [ ] DISCOVERY — Enumerate `contracts/ontology/**/*.json` excluding README; support files structured as collections: `{ "version": <semver-or-int>, "tags": [...], "affordances": [...] }`.
		- [ ] SCHEMA-VALIDATION — For each tag in `tags[]` validate against `tag.v1.json`; for each affordance in `affordances[]` validate against `affordance.v1.json` using `jsonschema`.
		- [ ] STRICTNESS — Enforce `additionalProperties=false` semantics at the validator layer; flag unknown fields with precise paths (e.g., `ontology/combat.json: tags[0].unknown_field`).
		- [ ] DUPLICATES — Collect by `tag_id`/`affordance_id` across all ontology files:
			- If identical after canonical JSON (exclude provenance-like/transient fields), treat as idempotent and optionally log a note.
			- If differing, emit a hard error that includes a brief diff or content hash mismatch note (e.g., SHA-256 of canonical payload).
		- [ ] PERF — Time per-file validation and print a compact summary (`ontology.validate.ms_p95`, count, file list truncated) to aid budget verification.
		- [ ] CLI-ERGONOMICS — Add optional flags (`--only-contracts` already exists). Do not break current CLI. Consider `--only-ontology` for local dev convenience.
	- Exit criteria: `make quality-artifacts` fails on ontology schema violations, duplicates, or conflicts; messages are actionable.
	- Owner: Tools/Contracts WG

- [x] TASK-IPD-FIXTURES-16 — Validator fixtures (DONE: directories valid/ invalid/ duplicate/ conflict/ plus README added)
	- Artifacts (new): `tests/fixtures/ontology/`
		- `valid/basic.json` — Minimal valid tags and affordances (multi-item collection)
		- `invalid/missing_fields.json` — Missing required keys
		- `invalid/pattern_violation.json` — Bad `tag_id`/`slug` patterns
		- `invalid/unknown_fields.json` — Extra properties to assert strictness
		- `duplicate/identical.json` — Same ID, identical definition in two files
		- `conflict/different.json` — Same ID, different definition across files
	- Exit criteria: Fixtures load in validator tests and exercise all failure/success modes deterministically.
	- Owner: QA/Contracts WG

- [x] TASK-IPD-TESTS-17 — Unit tests for ontology validator (DONE)
	- Code: `tests/test_ontology_validator.py`
	- Coverage:
		- Happy path (ephemeral collection) passes
		- Invalid aggregated collection produces precise schema/field errors
		- Duplicate-identical idempotent; duplicate-conflict emits conflict error
		- Ordering determinism (stable output ignoring timing line)
		- Timing summary presence asserted (dynamic values excluded)
	- Exit criteria: Tests pass locally; CI pending overall suite green (manifest hash issues external to ontology scope).
	- Owner: QA/Contracts WG

- [x] TASK-IPD-DOCS-15 — Ontology guide (migration & consumer mapping) (DONE: governance + workflow + migration log added)
	- Edits: `contracts/ontology/README.md`
	- Add:
		- Tag migration guidance (versioning, deprecation, synonyms policy) — COMPLETE
		- NLU/planner linkage & canonical affordance expectations — COMPLETE
		- Validator usage & timing capture instructions — COMPLETE
		- Change workflow & migration note template — COMPLETE
		- Migration Log initialized with benchmark entry — COMPLETE
	- Exit criteria: README governance sections finalized; migration log present; story updated (this change); reviewer sign-off pending PR.
	- Owner: Ontology/Contracts WG

- [ ] TASK-IPD-CI-18 — CI integration and performance note (NOT STARTED)
	- Ensure existing Make targets are used in CI (no ad-hoc scripts). If CI perf is flaky, capture a local run using a representative machine and attach timing (p95) to the PR description.
	- Exit criteria: CI fails on ontology violations; PR includes p95 evidence (≤ 200ms/file) or justified note.
	- Owner: DevEx/CI

## Definition of Ready (Consolidated Assessment — 2025-09-25)
- [x] Parent linkage: Linked in EPIC-IPD-001; ADR/architecture references present.
- [x] Scope clarity: Validator + governance docs in scope; importer behavior explicitly out-of-scope here.
- [x] Contract-first: `contracts/ontology/tag.v1.json` & `affordance.v1.json` exist and stable for v1.
- [x] Test strategy: Deterministic fixtures + planned unit tests enumerated; integration tests remain separate.
- [x] Observability plan: Timing summary (no runtime metrics) defined.
- [x] Task breakdown: Subtasks with owners & exit criteria documented above.
- [x] Fixtures: `tests/fixtures/ontology/` (valid/invalid/duplicate/conflict) prepared.
- [x] CI integration approach: Uses `make quality-artifacts` / `quality-gates` once validator extended.

Current readiness status: Ready (no blocking items). Pending implementation work is tracked directly in remaining open tasks (notably TASK-IPD-VALIDATE-14, TASK-IPD-TESTS-17, TASK-IPD-DOCS-15, TASK-IPD-CI-18).

## Definition of Done
- All acceptance criteria demonstrated via unit tests and CI runs; `make quality-gates` green.
- Contracts versioned; duplicate/conflict policy enforced by validator with stable error messages.
- Documentation refreshed: `contracts/ontology/README.md` includes migration guidance and validator usage.
- Security/perf gates respected: validator p95 ≤ 200ms per typical file (CI run or attached local measurement). No new dependencies beyond `jsonschema` used by existing checks.
- Traceability updated in the epic; PR links this story and includes performance note.

### Definition of Done — Assessment (2025-09-26 Update)
- All acceptance criteria / `make quality-gates` green: PARTIAL — Ontology validator + unit tests complete; unrelated manifest hash mismatches currently block overall green.
	- Next: Repair/regenerate manifest fixture hashes (importer scope) to unblock full gate.
- Contracts versioned & duplicate/conflict policy enforced: DONE — Validator enforces; backlog: replace Python hash() with stable SHA-256 digest in conflict messages.
- Documentation (migration & usage): DONE — Governance, workflow, canonical affordance policy, validator usage, migration log & template finalized.
- Performance evidence: PARTIAL — Synthetic medium benchmark (`__synthetic_medium_benchmark.json` + existing file, 25 total items) produced summary: avg_ms≈96.41 (per-file average) with p95_ms < 200ms. Further scale-up optional; current result within budget.
- Traceability & performance note in PR: PARTIAL — Story updated; PR summary will need timing & checklist mapping.

Summary: DONE (policy enforcement, documentation); PARTIAL (green gates, perf evidence, PR traceability). Remaining order: perf measurement refinement -> manifest hash fix (external) -> PR evidence.

## Test Plan
- Unit tests: `tests/test_ontology_validator.py`
	- Validate good/bad/duplicate/conflict fixtures under `tests/fixtures/ontology/` with precise path-reported errors.
	- Assert strictness (unknown fields rejected) and ordering determinism.
	- Exercise timing helper and assert presence of timing summary output.
- CI integration: `make quality-artifacts` and `make quality-gates` run in CI; pipeline fails on any ontology validation error.
- Performance: Capture and report p95 ≤ 200ms/file for a representative medium ontology file; if CI is noisy, record a local measurement and include it in the PR.
	- Note: This measures validator schema-check only, not NLU translation (covered by other stories).

## Observability
- None; governance docs updated.

## Risks & Mitigations
- Tag churn: require versioning and migration notes with each change.
- Drift between importer tests and validator: Keep event schemas and ontology schemas aligned; add a periodic doc note to cross-verify `contracts/events/seed/*` vs ontology schemas.
- False positives due to strictness: Provide clear guidance and examples in README; allow explicit `metadata` nesting for extensions while keeping top-level strict.

Note on status: This story was not formally initiated; partial implementation resulted from cross-work to unblock NLU baselines and contract placement, leaving validator integration pending.

## Dependencies
- Story C (tagging) consumers; validation script in scripts/.

## Feature Flags
- N/A (docs and scripts)

## Traceability
Artifacts and references:
- Epic: `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md`
- Validator: `scripts/validate_prompts_and_contracts.py`
- Contracts: `contracts/ontology/tag.v1.json`, `contracts/ontology/affordance.v1.json`, `contracts/events/seed/tag-registered.v1.json`, `contracts/events/seed/affordance-registered.v1.json`
- Make targets: `quality-artifacts`, `quality-gates`
- Tests (importer): `tests/importer/test_ontology_ingestion.py`, `tests/importer/test_ontology_event_validation.py`, `tests/importer/test_ontology_metrics.py`
- Tests (to add): `tests/test_ontology_validator.py`, fixtures under `tests/fixtures/ontology/`

---

Note: This story was partially started (seed files committed) without formal initiation. This document now reflects the current In Progress state and codifies the remaining steps to complete validation and governance.

## Alignment analysis — IPD↔CDA (embedded)

- Ensure ontology registration in CDA importer (seed `seed.tag_registered` events) lines up with tags used in IPD; validation script should cross-check usage.
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 4 — Ontology Management & Validation

## Implementation Assessment — STORY-IPD-001E (2025-09-26)

- Basic Info: Story (STORY-IPD-001E)/branch=main; feature flags=N/A (docs/scripts); affected: `contracts/ontology/*.json`, `contracts/events/seed/*`, `scripts/validate_prompts_and_contracts.py`, Make targets `quality-artifacts`/`quality-gates`; tests: importer + validator unit tests.
- Overall Status: Improved (ontology validator + unit tests merged; external manifest hash drift blocks global green)

- Section Results:
	1. Project Guidelines — Status: Meets — Evidence: Existing Make targets reused; no ad-hoc scripts added.
	2. Architecture Designs — Status: Meets — Evidence: Ontology schemas live under `contracts/ontology/` (`tag.v1.json`, `affordance.v1.json`, `README.md`); seed event schemas present under `contracts/events/seed/` (`tag-registered.v1.json`, `affordance-registered.v1.json`).
	3. Story Details — Status: Updated — Evidence: Validator now enumerates ontology files, validates entries, detects duplicates/conflicts, emits timing summary.
	4. Implementation Status — Status: Improved — Evidence: Ontology validation active; overall gate failure due to manifest hash mismatch (external to ontology scope).
	5. Acceptance Criteria — Status: Partially Met — Evidence: Validation + unit tests done; migration guidance & perf evidence pending.
	6. Contracts & Compatibility — Status: Meets (so far) — Evidence: Versioned schemas (`v1`) exist; event schemas align with importer tests; quality gates run but do not currently fail on ontology schema issues.
	7. Test Strategy — Status: Met — Evidence: `tests/fixtures/ontology/` plus unit tests cover valid/invalid/duplicate/conflict + ordering & timing.

- Risks/Compatibility Notes:
	- Manifest hash drift (import fixtures) currently blocks full green; unrelated to ontology but masks integrated gate results.
	- Conflict message uses Python `hash()` (non-stable); reproducibility improvement pending (SHA-256 digest).
	- Missing migration guidance risks inconsistent tag/affordance evolution & ad-hoc deprecations.

- Required Updates (actionable):
	- Augment `contracts/ontology/README.md` with migration & evolution guidance (draft added; finalize examples & template usage).
	- Record representative medium ontology p95 timing and place result in PR performance note.
	- Swap conflict hash to SHA-256 for deterministic diff hints.
	- Repair manifest fixture hashes to allow full `make quality-gates` success.

- References: Makefile (`quality-artifacts`, `quality-gates`), `scripts/validate_prompts_and_contracts.py` (no ontology checks yet), `contracts/ontology/{tag.v1.json, affordance.v1.json, README.md}`, `contracts/events/seed/{tag-registered.v1.json, affordance-registered.v1.json}`, tests in `tests/importer/`.
