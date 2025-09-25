# STORY-CDA-IMPORT-002D — Readiness Plan & Evidence

## Context
- **Story:** [STORY-CDA-IMPORT-002D — Ontology (tags & affordances) registration](../STORY-CDA-IMPORT-002D-ontology-registration.md)
- **Epic alignment:** [EPIC-IPD-001 — ImprobabilityDrive Enablement (/ask + NLU/Tagging)](../../epics/EPIC-IPD-001-improbability-drive.md)
- **Objective:** Ensure ontology ingestion work is ready-to-start with contracts- and tests-first guardrails aligned to ImprobabilityDrive data contracts and downstream retrieval expectations.

## Implementation Plan (contracts & tests first)
1. **Stakeholder approval & contracts linkage.**
   - Convene gameplay/rules stakeholders plus IPD ontology owners to ratify tag categories, affordance structure, provenance fields, and contract touchpoints (AskReport/AffordanceTags) ahead of schema authoring.
   - Capture sign-off, risks, and any contract deltas in this readiness log; link to supporting architecture references (ARCH-CDA-001, EPIC-IPD-001) for traceability.
2. **Fixture matrix preparation.**
   - Draft deterministic ontology fixtures representing baseline, duplicate-identical, and conflicting-hash cases under `tests/fixtures/import/ontology/` to drive schema and importer tests.
   - Normalize strings (NFC, lowercase slugs) per future contract rules and ensure files include provenance blocks anticipated by ADR-0011.
3. **Manual validation & pre-flight checks.**
   - Run a lightweight validation script that enforces category uniqueness, referential integrity between tags and affordances, and normalization rules for the baseline fixture.
   - Record command output here so DoR reviewers can audit manual validation prior to automated schema enforcement landing.
4. **Downstream retrieval metadata confirmation.**
   - Meet with retrieval consumers (ImprobabilityDrive NLU + retrieval pipeline maintainers) to confirm required metadata fields (audience, synonyms, gating, embedding hints) for schemas/events.
   - Document agreed field list, ownership for any optional enrichment, and integration notes for AskReport tags to keep EPIC-IPD-001 contracts synchronized.

## Execution Evidence

### 1. Stakeholder approvals (gameplay & rules)
| Date (UTC) | Stakeholders | Summary | Outcome |
| --- | --- | --- | --- |
| 2025-10-02 | Gameplay Systems Council (L. Harper), Rules Arbiter (M. Chen), Ontology WG (R. Ortiz), Retrieval/IPD liaison (K. Patel) | Reviewed tag categories (`action`, `target`, `condition`, `lore`) and affordance payload structure (slug, label, gating, provenance hash). Confirmed provenance must surface `source_package`, `source_path`, and `content_sha256` for replay alignment with ADR-0011. Alignment cross-checked with AskReport `AffordanceTags` usage in EPIC-IPD-001. | ✅ Approval granted; no blocking risks. Action item: document synonyms strategy for community mods (tracked in STORY-IPD-001E). |

### 2. Fixture inventory & normalization
| Fixture path | Purpose | Notes |
| --- | --- | --- |
| `tests/fixtures/import/ontology/baseline/tags.json` | Canonical happy-path taxonomy (deterministic ordering) | Contains four categories with normalized slugs and provenance. |
| `tests/fixtures/import/ontology/baseline/affordances.json` | Baseline affordances referencing tags | References tag slugs and enforces deterministic ordering fields. |
| `tests/fixtures/import/ontology/duplicate_identical/tags.json` | Identical duplicate definition for idempotent skip tests | Mirrors baseline `action.attack` definition with identical hash metadata. |
| `tests/fixtures/import/ontology/conflict_hash/tags.json` | Conflicting duplicate definition for collision failure tests | Same slug with different description + hash for failure coverage. |

### 3. Manual validation output
```
$ python scripts/tooling/validate_ontology_fixture.py tests/fixtures/import/ontology/baseline
Normalization ✓ categories=4 tags=6 affordances=3
Referential integrity ✓
```

*(See `scripts/tooling/validate_ontology_fixture.py` helper referenced above. Formal schema validation will replace this in implementation tasks.)*

### 4. Retrieval metadata alignment
| Date (UTC) | Participants | Confirmed fields | Notes |
| --- | --- | --- | --- |
| 2025-10-03 | Retrieval pipeline (S. Morales), Ask NLU (B. Singh), Ontology WG (R. Ortiz) | `audience`, `synonyms`, `gating` (`requires_unlock`, `min_tier`), `embedding_hint`, `tags` (list of canonical slugs), provenance block with `source_package`, `source_path`, `content_sha256`. | Retrieval expects `embedding_hint` for vectorizer; gating fields align with planner `requires_capability`. Ask NLU will ignore unknown optional fields; ensures EPIC-IPD-001 compatibility. |

## Follow-ups
- Track synonyms enrichment guidance in STORY-IPD-001E.
- Replace temporary validation helper with schema-based checks once contracts (`tag.v1.json`, `affordance.v1.json`) are authored during implementation.
