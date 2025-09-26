# STORY-IPD-001E — Ontology management and versioning

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: In Progress
Owner: Ontology/Contracts WG

## Summary
Define ontology files under `contracts/` or `prompts/` with versioning, validation script, and governance.

## Acceptance Criteria
- Ontology schema and linter in place; changes validated via CI script (`scripts/validate_prompts_and_contracts.py`).
- Tags referenced by NLU and planner documented with migration guidance.

## Tasks
- [x] TASK-IPD-ONTO-13 — Author ontology schema and seed ontology. (Seed present under `contracts/ontology/seed-v0_1.json`; schema artifacts exist under `contracts/ontology/*.json`)
- [ ] TASK-IPD-VALIDATE-14 — Extend validation script to include ontology checks. (Pending integration into `scripts/validate_prompts_and_contracts.py`)
- [ ] TASK-IPD-DOCS-15 — Author ontology guide under docs/architecture or docs/dev.

## Definition of Ready
- Stakeholders aligned on taxonomy scope.
- Cross-epic alignment defined with CDA importer ontology registration (CDA-IMPORT-002D) to prevent drift.

## Definition of Done
- CI runs ontology validation; docs linked here.
- Ontology references in NLU/tagging are versioned and validated against the schema.

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
---

Note: This story was partially started (seed files committed) without formal initiation. This document now reflects the current In Progress state and codifies the remaining steps to complete validation and governance.

## Alignment analysis — IPD↔CDA (embedded)

- Ensure ontology registration in CDA importer (seed `seed.tag_registered` events) lines up with tags used in IPD; validation script should cross-check usage.
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 4 — Ontology Management & Validation
