# STORY-CDA-IMPORT-002E — Lore content chunking & ingestion

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Lore & retrieval team

## Summary
Process lore markdown files with front-matter metadata, chunk content deterministically, capture provenance, and emit `seed.content_chunk_ingested` events ready for retrieval indexing. Enforce audience gating and optional embedding metadata behind feature flags. Ensure hashing and ordering align with manifest index to guarantee reproducible imports per ARCH-CDA-001.

## Acceptance Criteria
- Front-matter schema documented (YAML/JSON) and validated via contract or parser rules: includes `chunk_id`, `title`, `audience`, `tags[]`, optional `embedding_hint` and `provenance` block.
- Chunker splits content deterministically (e.g., by headings or token limits) and produces stable ordering across runs; tests cover newline and Unicode normalization cases.
- Audience enforcement ensures disallowed audience values fail import with clear error; optional embedding metadata only processed when `features.importer_embeddings` (or similar) enabled.
- `seed.content_chunk_ingested` payload includes metadata + provenance, referencing manifest hash and chunk content hash; passes contract validation.
- ImportLog entries recorded per chunk with `{phase="lore", object_type="content_chunk", stable_id=chunk_id, file_hash=content_hash}`; collisions handled similar to other phases.

## Tasks
- [ ] **TASK-CDA-IMPORT-CHUNK-13A — Front-matter schema definition.** Document required/optional front-matter fields, update contracts (e.g., `contracts/content/chunk-front-matter.v1.json`), and add fixtures.
- [ ] **TASK-CDA-IMPORT-CHUNK-13B — Chunker algorithm design.** Specify deterministic chunking strategy (heading boundaries + max token count), implement helper with unit tests covering edge cases (long paragraphs, unicode, code blocks).
- [ ] **TASK-CDA-IMPORT-CHUNK-13C — Hashing & provenance tests.** Compute canonical hash over chunk payload (front-matter + content) and add golden fixtures verifying stability; include Unicode normalization test per epic DoD.
- [ ] **TASK-CDA-IMPORT-SEED-14A — Event schema parity.** Define/verify `seed.content_chunk_ingested` schema under `contracts/events/seed/` with tests ensuring payload matches contract.
- [ ] **TASK-CDA-IMPORT-SEED-14B — Ordering/idempotency integration tests.** Run importer for manifest → lore phase twice to assert deterministic ordering, idempotent skip metrics, and rollback on collision.
- [ ] **TASK-CDA-IMPORT-AUD-15A — Audience enforcement tests.** Add fixtures with invalid/unsupported audience values, missing gating tags, and ensure importer rejects with descriptive errors.
- [ ] **TASK-CDA-IMPORT-AUD-15B — Feature flag gating.** Introduce/validate optional embedding metadata flag; tests assert disabled state ignores embedding field while still hashing consistently.

## Definition of Ready
- Front-matter schema reviewed with narrative design + retrieval stakeholders (see readiness review summary for attendee sign-off and schema field confirmations).【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002E-front-matter-review.md†L1-L35】
- Reference lore files (simple + complex) curated for testing, including non-ASCII characters, available under `tests/fixtures/import/lore/` with README guidance.【F:tests/fixtures/import/lore/README.md†L1-L24】【F:tests/fixtures/import/lore/simple/moonlight-tavern.md†L1-L21】【F:tests/fixtures/import/lore/complex/clockwork-archive.md†L1-L35】
- Decision on optional embedding metadata flag documented (`features.importer_embeddings`, default `false`).【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002E-embedding-flag-decision.md†L1-L24】

## Definition of Done
- Chunker implementation + tests merged with deterministic ordering and Unicode normalization coverage.
- Contracts/fixtures validated via script; documentation updated describing chunking algorithm and provenance mapping.
- Metrics `importer.chunks.ingested`, `importer.chunks.skipped_idempotent`, and `importer.collision` (if reused) registered with tests.
- Structured logs include chunk counts, first failure path, and duration for lore phase.

## Test Plan
- **Contract tests:** Validate front-matter schema fixtures via contract validator.
- **Unit tests:** Chunker behavior, hashing, ordering, Unicode normalization, feature flag gating.
- **Integration tests:** Importer run verifying deterministic event ordering, idempotent skip, collision rollback, and ImportLog contents.
- **CLI/utility tests:** Optionally expose chunk preview command; test ensures consistent output for given file.

## Observability
- Structured logs per file summarizing chunk counts and hash outputs.
- Metrics: `importer.chunks.ingested`, `importer.chunks.skipped_idempotent`, optional histogram for chunk size/duration.

## Risks & Mitigations
- **Non-deterministic chunking due to tokenization:** Mitigate by using deterministic algorithm (e.g., deterministic tokenizer) and golden fixture tests.
- **Audience misconfiguration:** Enforce contract-level enums and include negative fixtures.
- **Unicode normalization causing hash drift:** Covered by tests and canonical normalization helper reuse.

## Dependencies
- Manifest registration (package_id, manifest_hash) for provenance.
- Potential reliance on ontology tags for cross-linking (ensure they are loaded/validated before lore ingestion or cross-check references).
- Feature flag configuration for embedding metadata.

## Feature Flags
- `features.importer` (global gate).
- Potential new `features.importer_embeddings` (documented here; default false until follow-up story).

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/content/chunk-front-matter.v1.json`, `contracts/events/seed/content-chunk-ingested.v1.json`.
- Tests: `tests/importer/test_lore_chunking.py`, `tests/importer/test_lore_seed_events.py`.

## Implementation Notes
- Consider streaming markdown parser to avoid loading large files fully; maintain deterministic ordering by storing tuple `(source_path, chunk_index)`.
- Reuse canonical JSON helper for front-matter serialization to align hashing across languages/tools.
