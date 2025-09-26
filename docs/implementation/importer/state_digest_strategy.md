# Importer State Digest Strategy

## Purpose

This note captures the readiness decision for STORY-CDA-IMPORT-002F regarding
how the importer will compute the deterministic `state_digest`. The intent is to
lock the algorithm ahead of implementation and confirm that supporting helpers
and fixtures are available.

## Algorithm Decision

- Follow ARCH-CDA-001 guidance: the digest is derived from a canonical ordering
  of `(phase, stable_id, content_hash)` tuples. 【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L118-L149】
- Reuse the repository-wide canonical JSON hasher introduced in STORY-CDA-CORE-001B
  (`Adventorator.canonical_json.compute_canonical_hash`). 【F:src/Adventorator/canonical_json.py†L159-L188】
- Serialize the components as `{"state_components": [...]}` and hash the
  canonical representation to produce a 64-character hex digest. The helper is
  exercised by `tests/importer/test_importer_context.py::test_context_digest_matches_manual_hash`.
  【F:tests/importer/test_importer_context.py†L79-L102】

## Component Ordering

1. Manifest summary — package_id + manifest_hash.
2. Entity phase — each entity's `stable_id` + provenance `file_hash`.
3. Edge phase — each edge `stable_id` + provenance `file_hash`.
4. Ontology phase — tag and affordance identifiers with their provenance
   hashes.
5. Lore phase — chunk identifiers with chunk content hashes.

Entries are sorted lexicographically by `(phase, stable_id, content_hash)` before
hashing to ensure deterministic output across platforms.

## Supporting Utilities

- `ImporterRunContext` aggregates the above components, deduplicates ImportLog
  entries, and exposes `compute_state_digest()`. 【F:src/Adventorator/importer_context.py†L68-L208】
- Unit and golden tests prove the helper and fixtures:
  - Context aggregation and hashing parity. 【F:tests/importer/test_importer_context.py†L12-L102】
  - Golden fixture replay validating the stored digest.
    【F:tests/importer/test_state_digest_fixture.py†L1-L55】

## Fixture Baseline

`tests/fixtures/import/manifest/happy-path/state_digest.txt` records the
expected digest for the canonical package fixture. The fixture now contains
manifest, entity, edge, ontology, and lore assets that satisfy all importer
phase validators. 【F:tests/fixtures/import/manifest/happy-path/state_digest.txt†L1-L1】

These assets unblock STORY-CDA-IMPORT-002F by ensuring the fold helper design
and test harnesses have deterministic inputs.
