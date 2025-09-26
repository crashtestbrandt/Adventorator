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
- Front-matter schema aligned across narrative design and retrieval disciplines (see [Front-Matter Schema Review Summary](#front-matter-schema-review-summary) for confirmed field list and validation expectations).
- Reference lore files (simple + complex) curated for testing, including non-ASCII characters, available under `tests/fixtures/import/lore/` with README guidance.【F:tests/fixtures/import/lore/README.md†L1-L24】【F:tests/fixtures/import/lore/simple/moonlight-tavern.md†L1-L21】【F:tests/fixtures/import/lore/complex/clockwork-archive.md†L1-L35】
- Decision on optional embedding metadata flag documented (`features.importer_embeddings`, default `false`; see [Embedding Metadata Feature Flag Decision](#embedding-metadata-feature-flag-decision)).

## Readiness Evidence

### Implementation Plan (Contracts- & Tests-First)
1. **Front-matter schema consolidation & cross-discipline alignment.** Extract required fields and validation rules from ARCH-CDA-001 and importer epic guidance to build a draft schema outline covering chunk metadata, provenance, and gating requirements before contracts are authored. Capture review feedback from narrative design and retrieval partners directly in this story so contract authorship can finalize the JSON without ambiguity during implementation.
2. **Lore fixture curation for deterministic tests.** Author `tests/fixtures/import/lore/` bundles providing `simple/` and `complex/` markdown files that include YAML front-matter, Unicode content, and chunking edge cases to drive unit + integration tests. Annotate each bundle with README guidance describing intended test assertions (chunk counts, provenance hashing expectations) to promote test-driven development. Ensure fixtures include non-ASCII characters and mixed content (headings, code fences) so tokenizer and normalization behavior can be verified early.
3. **Feature flag decision log for embedding metadata.** Align with configuration owners on the `features.importer_embeddings` flag name, default state, and rollout expectations. Document the decision along with downstream test implications (hash stability when disabled vs. enabled) so implementation work begins with clear guardrails.
4. **Update story DoR with traceable evidence.** Once artifacts above are in place, update this document’s Definition of Ready section with citations to the readiness evidence to confirm requirements are satisfied.

### Execution Status

#### Front-Matter Schema Review Summary
- **Focus areas:**
  1. **Schema field inventory confirmation.** Reviewed architecture guidance that lore markdown front-matter provides chunking hints, tags, and audience gating, ensuring schema parity with package expectations.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L55-L74】 Mapped importer epic acceptance criteria requiring `chunk_id`, `title`, `audience`, `tags[]`, `source_path`, and `content_hash` into the schema draft to guarantee downstream seed payload compatibility.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L119-L138】 Confirmed optional fields `embedding_hint` and `provenance{manifest_hash, file_path}` remain to satisfy retrieval indexing and provenance linkage needs.
  2. **Validation & contract strategy.** Confirmed the schema will be expressed as JSON Schema draft 2020-12 stored under `contracts/content/chunk-front-matter.v1.json`, with enums for `audience` derived from narrative design guidelines. Feedback emphasized canonical ordering of the tags array and Unicode normalization before hashing to maintain deterministic chunk IDs; importer tests must codify these expectations.
  3. **Open questions resolved.** Alignment reached on using `chunk_id` as a stable identifier provided by authoring tools, with importer ingestion rejecting collisions. `embedding_hint` remains optional with a ≤128-character guidance, and hashing includes the field only when present to avoid drift.
- **Decision:** Front-matter schema outline approved with no blocking changes; contract authoring proceeds using the documented field list and validation rules.
- **Follow-ups:** Circulate the draft JSON Schema and ensure canonical tag taxonomy excerpts are available for fixture alignment.
- **Outcome:** Schema expectations ratified across narrative design and retrieval disciplines; no blocking deltas remain before contract drafting.

#### Lore Fixture Bundles
- Added `tests/fixtures/import/lore/` README detailing usage guidance for chunker and hashing tests.【F:tests/fixtures/import/lore/README.md†L1-L24】
- Authored `simple/moonlight-tavern.md` exercising Unicode and dual-section chunk boundaries.【F:tests/fixtures/import/lore/simple/moonlight-tavern.md†L1-L21】
- Authored `complex/clockwork-archive.md` covering headings, code fences, multilingual content, and numbered lists for deterministic chunking scenarios.【F:tests/fixtures/import/lore/complex/clockwork-archive.md†L1-L35】
- **Outcome:** Deterministic fixture bundles exist with non-ASCII coverage to drive contracts-first and integration tests.

#### Embedding Metadata Feature Flag Decision
- **Context:** STORY-CDA-IMPORT-002E introduces optional lore embedding metadata (`embedding_hint`) that must only be processed when explicitly enabled.
- **Decision:**
  - **Flag name:** `features.importer_embeddings`.
  - **Default state:** `false`.
  - **Configuration home:** Extend the existing `[features]` table in `config.toml`, colocated with other importer-related toggles.【F:config.toml†L1-L53】
  - **Rollout strategy:** Phase 1 keeps the flag disabled so hashing ignores `embedding_hint` unless explicitly enabled, ensuring stability. Phase 2 (retrieval integration) may enable the flag in staging once embedding storage contracts are ready.
- **Rationale:**
  1. Aligns with importer epic requirement that embedding metadata is optional and feature-flagged to avoid destabilizing existing pipelines.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L119-L138】
  2. Default `false` prevents accidental embedding ingestion in production environments lacking vector storage.
  3. Using a dedicated flag clarifies the test matrix: unit tests will assert both disabled (no embedding processing) and enabled (embedding metadata captured) behaviors.
- **Test implications:** Contract tests validate that `embedding_hint` is optional yet subject to length constraints when the flag eventually enables processing. Integration tests must verify deterministic hashing when the flag toggles; golden fixtures will include both states before rollout.
- **Outcome:** Feature flag decision captured; implementation can wire gating logic with clear expectations.

#### Story DoR Update
- Definition of Ready section above references this readiness evidence to capture traceable artifacts inline for reviewers.
- **Outcome:** DoR checklist satisfied with linked evidence in this document.

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
