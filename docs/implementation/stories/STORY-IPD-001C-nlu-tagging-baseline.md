# STORY-IPD-001C — NLU and tagging scaffold (rule-based baseline)

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: NLU/Ontology WG

## Summary
Implement a deterministic, rule-based parser for action, actor, object/target refs, plus AffordanceTags extraction from a small ontology; include entity normalization hooks. This story owns the initial token/stopword heuristic; no external NLP.

## Acceptance Criteria
- Deterministic parsing with seeded examples; no network calls.
- Tag extraction maps to ontology IDs; unrecognized tokens surfaced as `unknown:*` tags.
- Unit tests cover varied phrasing and edge cases (empty/ambiguous).
- Implementation avoids external NLP libraries (e.g., spaCy) per current decision; strictly rule-based and offline.

## Tasks
- [ ] TASK-IPD-NLU-07 — Rule-based parser for IntentFrame fields.
- [ ] TASK-IPD-TAGS-08 — AffordanceTags extractor with ontology lookups.
- [ ] TASK-IPD-TEST-09 — Fixture-driven tests with golden outputs.
- [ ] TASK-IPD-DOC-10 — Document normalization rules and examples in docs/dev/.

## Definition of Ready
- Ontology MVP defined; normalization rules agreed.

## Definition of Done
- Parser/extractor documented with examples and limitations.

## Test Plan
- Deterministic unit tests with paraphrases; ambiguity surfaced in structured fields.
- Fixtures live under `tests/fixtures/ask/`; seed ontology under `contracts/ontology/`.

## Observability
- Optional debug logs behind a dev flag; no new metrics required in this story.

## Risks & Mitigations
- Overfitting rules: keep coverage broad; add fixtures iteratively.

## Dependencies
- ADR-0005 (contracts/flags/rollout)
- Story E (ontology) may run in parallel for seed ontology.
- Story D (KB adapter) for future normalization enhancements.

## Feature Flags
- features.improbability_drive (gates behavior)
- features.ask_nlu_rule_based (default=true)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 2 — NLU & Tagging Scaffold (Deterministic)
