# Ontology import fixtures

These fixtures support STORY-CDA-IMPORT-002D readiness and importer tests.

- `taxonomy_valid.json` — Baseline taxonomy covering multiple categories, synonyms, gating metadata, and ImprobabilityDrive intent hints.
- `taxonomy_duplicate_identical.json` — Duplicate tag entries with identical definitions to exercise idempotent skip behavior.
- `taxonomy_conflict.json` — Conflicting tag entries (different ruleset version and synonym set) to exercise collision detection.

Manual validation checklist (2025-02-21):

1. Loaded each file with `python -m json.tool` to confirm JSON structure.
2. Verified canonical slug normalization (`slug` fields lowercase hyphenated) and categories align with `action` / `target` expectations from the ImprobabilityDrive contracts.
3. Confirmed gating metadata includes `audience` and `requires_feature` fields needed by retrieval and planner consumers.
4. Confirmed provenance block present to align with ADR-0011 replay guarantees.

Validation script transcript is stored in `/docs/implementation/stories/readiness/STORY-CDA-IMPORT-002D-ontology-registration-readiness.md`.
