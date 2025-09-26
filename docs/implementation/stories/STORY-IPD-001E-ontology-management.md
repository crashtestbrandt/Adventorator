# STORY-IPD-001E — Ontology management and versioning

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: In Progress — Schemas present; validator integration pending
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

- [ ] TASK-IPD-VALIDATE-14 — Extend contracts validator with ontology checks
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

- [ ] TASK-IPD-FIXTURES-16 — Validator fixtures
	- Artifacts (new): `tests/fixtures/ontology/`
		- `valid/basic.json` — Minimal valid tags and affordances (multi-item collection)
		- `invalid/missing_fields.json` — Missing required keys
		- `invalid/pattern_violation.json` — Bad `tag_id`/`slug` patterns
		- `invalid/unknown_fields.json` — Extra properties to assert strictness
		- `duplicate/identical.json` — Same ID, identical definition in two files
		- `conflict/different.json` — Same ID, different definition across files
	- Exit criteria: Fixtures load in validator tests and exercise all failure/success modes deterministically.
	- Owner: QA/Contracts WG

- [ ] TASK-IPD-TESTS-17 — Unit tests for ontology validator
	- Code: `tests/test_ontology_validator.py`
	- Coverage:
		- Happy path validates `valid/basic.json` and reports zero errors
		- Invalid files produce precise messages (missing field, pattern, unknown field)
		- Duplicate-identical passes; duplicate-conflict fails with clear reason
		- Ordering determinism (validation independent of filename order)
		- Performance check invokes validator timing helper and asserts presence of metrics/log lines (non-flaky)
	- Exit criteria: Tests pass locally and in CI; failure messages remain stable and useful.
	- Owner: QA/Contracts WG

- [ ] TASK-IPD-DOCS-15 — Ontology guide (migration & consumer mapping)
	- Edits: `contracts/ontology/README.md`
	- Add:
		- Tag migration guidance (version bump etiquette, deprecations, synonyms updates)
		- NLU/planner linkage: how `canonical_affordance` is used, and expectations for Ask→tags mapping
		- "How to run" validator locally (`make quality-artifacts` / `quality-gates`) and interpreting errors
	- Exit criteria: README updated; story and epic link to doc; reviewers sign off.
	- Owner: Ontology/Contracts WG

- [ ] TASK-IPD-CI-18 — CI integration and performance note
	- Ensure existing Make targets are used in CI (no ad-hoc scripts). If CI perf is flaky, capture a local run using a representative machine and attach timing (p95) to the PR description.
	- Exit criteria: CI fails on ontology violations; PR includes p95 evidence (≤ 200ms/file) or justified note.
	- Owner: DevEx/CI

## Definition of Ready
- Parent linkage: This story is linked in EPIC-IPD-001 and references seed event schemas; ADR/architecture references updated as needed.
- Scope clarity: In-scope is schema validation and governance docs; out-of-scope is importer behavior changes (already tested elsewhere).
- Contract-first: `contracts/ontology/tag.v1.json` and `affordance.v1.json` exist and are stable for v1; consumers (NLU/planner) notified of any changes.
- Test strategy: Unit tests for validator, deterministic fixtures, CI gate via Make; importer integration tests remain separate.
- Observability plan: Validator prints minimal timing summary; no runtime metrics required beyond logs.
- Task breakdown: Subtasks above have owners and explicit artifacts with exit criteria.
- Deterministic fixtures prepared under `tests/fixtures/ontology/` to exercise validator (happy/invalid/duplicate/conflict).
- CI integration approach: Use `make quality-artifacts` and `make quality-gates`; failure policy documented in PR template.

### Definition of Ready — Assessment (2025-09-25)

- [x] Parent linkage — Verified: `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md` exists and is referenced here.
- [x] Scope clarity — Verified: Out-of-scope (importer behavior) is explicitly called out; in-scope is validator + docs.
- [x] Contract-first — Verified: `contracts/ontology/tag.v1.json` and `contracts/ontology/affordance.v1.json` present; `contracts/ontology/README.md` documents invariants.
- [x] Test strategy — Verified: Strategy documented in this story; specific tests and fixtures enumerated below.
- [x] Observability plan — Verified: Timing summary requirement captured; no metrics beyond logs.
- [x] Task breakdown — Verified: Tasks and owners listed with exit criteria.
- [x] Deterministic fixtures prepared — Added under `tests/fixtures/ontology/` (valid/invalid/duplicate/conflict).
- [x] CI integration approach — Verified: `Makefile` provides `quality-artifacts` and `quality-gates`; validator script path confirmed.

Blocking items to reach Ready: None.

Pre-Ready actionable deltas (non-invasive, to be addressed on implementation branch):
- Extend `scripts/validate_prompts_and_contracts.py` with ontology checks behind an additive CLI flag (e.g., `--only-ontology`) without breaking existing usage, as described in TASK-IPD-VALIDATE-14.
- Add `tests/test_ontology_validator.py` to exercise fixtures and timing summary (TASK-IPD-TESTS-17).

## Definition of Done
- All acceptance criteria demonstrated via unit tests and CI runs; `make quality-gates` green.
- Contracts versioned; duplicate/conflict policy enforced by validator with stable error messages.
- Documentation refreshed: `contracts/ontology/README.md` includes migration guidance and validator usage.
- Security/perf gates respected: validator p95 ≤ 200ms per typical file (CI run or attached local measurement). No new dependencies beyond `jsonschema` used by existing checks.
- Traceability updated in the epic; PR links this story and includes performance note.

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

## Implementation Assessment — STORY-IPD-001E (2025-09-25)

- Basic Info: Story (STORY-IPD-001E)/branch=main; feature flags=N/A (docs/scripts); affected modules: `contracts/ontology/*.json`, `contracts/events/seed/*`, `scripts/validate_prompts_and_contracts.py`, Makefile targets `quality-artifacts`/`quality-gates`; related tests under `tests/importer/` (ontology ingestion and event schema parity).
- Overall Status: Partial

- Section Results:
	1. Project Guidelines — Status: Partial — Evidence: Makefile target `quality-artifacts` runs `python scripts/validate_prompts_and_contracts.py` (Makefile). No FastAPI/DB changes in scope.
	2. Architecture Designs — Status: Meets — Evidence: Ontology schemas live under `contracts/ontology/` (`tag.v1.json`, `affordance.v1.json`, `README.md`); seed event schemas present under `contracts/events/seed/` (`tag-registered.v1.json`, `affordance-registered.v1.json`).
	3. Story Details — Status: Missing (validator integration) — Evidence: `scripts/validate_prompts_and_contracts.py` lacks ontology validation (no references to `contracts/ontology`, focuses on OpenAPI and manifest fixtures). Task `TASK-IPD-VALIDATE-14` remains unchecked.
	4. Implementation Status — Status: Partial — Evidence: Importer workflow for ontology exists and is tested (`tests/importer/test_ontology_ingestion.py`, `..._event_validation.py`, `..._metrics.py`), but CI quality gate does not yet validate ontology artifacts.
	5. Acceptance Criteria — Status: Partial — Evidence: Schema artifacts present and used by importer tests; CI validator does not enforce them; no recorded p95 runtime for ontology validation; migration guidance for tags is not explicitly documented beyond `contracts/ontology/README.md`.
	6. Contracts & Compatibility — Status: Meets (so far) — Evidence: Versioned schemas (`v1`) exist; event schemas align with importer tests; quality gates run but do not currently fail on ontology schema issues.
	7. Test Strategy — Status: Missing (validator unit tests/fixtures) — Evidence: No `tests/fixtures/ontology/` directory; validator has no unit tests for ontology round-trips.

- Risks/Compatibility Notes:
	- Without validator coverage, ontology drift or JSON mistakes may land undetected; duplicate/conflict policies are enforced only at import-time tests, not at artifact submission time.
	- Performance budget (p95 ≤ 200ms per file) is unmeasured and may regress without a lightweight timing check.

- Required Updates (actionable):
	- Implement `TASK-IPD-VALIDATE-14`: Extend `scripts/validate_prompts_and_contracts.py` to:
		- Locate ontology files under `contracts/ontology/` and validate each tag/affordance entry against `tag.v1.json`/`affordance.v1.json` using `jsonschema`.
		- Emit clear, actionable errors on invalid fields; treat unknown properties as failures.
		- Optionally measure validation runtime per file and print a short summary to aid p95 checks.
	- Add deterministic fixtures for validator tests under `tests/fixtures/ontology/`:
		- `valid/*.json`, `invalid/*.json`, `duplicate/*.json` (idempotent), `conflict/*.json` (hash mismatch on same ID) sized to exercise validation without external deps.
	- Add unit tests for the validator (e.g., `tests/test_ontology_validator.py`) covering valid/invalid/duplicate/conflict cases and ordering determinism.
	- CI integration: ensure `make quality-artifacts` (and `quality-gates`) fail on ontology validation errors; note any performance measurement in PR description if CI timing is flaky.
	- Documentation: augment `contracts/ontology/README.md` with tag migration guidance and NLU/planner tag usage notes; link this story and EPIC.

- References: Makefile (`quality-artifacts`, `quality-gates`), `scripts/validate_prompts_and_contracts.py` (no ontology checks yet), `contracts/ontology/{tag.v1.json, affordance.v1.json, README.md}`, `contracts/events/seed/{tag-registered.v1.json, affordance-registered.v1.json}`, tests in `tests/importer/`.
