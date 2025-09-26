# STORY-CDA-IMPORT-002B — Entity ingestion & synthetic events

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Entity ingestion squad

## Summary
Deterministically ingest entity definitions (`entities/*.json`), enforce `stable_id` uniqueness, capture provenance per [ADR-0011](../../adr/ADR-0011-package-import-provenance.md), and emit `seed.entity_created` events conforming to ledger expectations outlined in [ARCH-CDA-001](../../architecture/ARCH-CDA-001-campaign-data-architecture.md). Ordering must be stable between runs using `(kind, stable_id, source_path)` sort keys, and idempotent replays must skip entities with identical file hashes while recording metrics for collisions.

## Acceptance Criteria
- Entity parser reads canonical schema (align with contract or define new `contracts/entities/entity.v1.json`) and rejects documents lacking required fields (`stable_id`, `kind`, `name`, `tags[]`, `affordances[]`, provenance hints).
- Importer sorts entities deterministically and persists ImportLog entries per entity `{phase="entity", object_type=kind, stable_id, file_hash}` prior to event emission.
- `seed.entity_created` payload mirrors runtime entity representation (minus runtime-only fields) and passes contract validation; event order stable across replays (test proven).
- Collision detection surfaces explicit error differentiating "hash mismatch" (hard fail) vs "identical hash" (idempotent skip) and increments respective metrics.
- Provenance data attached to both ImportLog and event payload matches manifest `package_id` plus file-level hash; unit tests assert fidelity.

## Tasks
- [ ] **TASK-CDA-IMPORT-ENT-04A — Entity contract alignment.** Confirm existing ontology/entity schemas or author `contracts/entities/entity.v1.json`; document differences from runtime ORM models.
- [ ] **TASK-CDA-IMPORT-ENT-04B — Parser implementation.** Build parser that loads entity files, validates against schema, normalizes text (UTF-8 NFC), and collects deterministic sort key tuples.
- [ ] **TASK-CDA-IMPORT-ENT-04C — Validation tests.** Add fixture coverage for missing required fields, invalid tag references, and malformed JSON; ensure errors reference precise file path + field.
- [ ] **TASK-CDA-IMPORT-PROV-05A — Provenance hashing helper.** Compute per-file SHA-256 over canonical JSON and store alongside parsed entity; include golden hash fixtures for regression.
- [ ] **TASK-CDA-IMPORT-PROV-05B — ImportLog persistence spec.** Extend/confirm ImportLog model fields to hold entity provenance, add migration/tests if schema gaps exist.
- [ ] **TASK-CDA-IMPORT-SEED-06A — Synthetic event contract parity.** Define/verify `seed.entity_created` JSON schema under `contracts/events/seed/`; add tests comparing event payload vs schema + runtime Pydantic model.
- [ ] **TASK-CDA-IMPORT-SEED-06B — Ordering & idempotency tests.** Implement pytest verifying deterministic event ordering across two importer runs and idempotent skip path with metrics assertions.
- [ ] **TASK-CDA-IMPORT-SEED-06C — Collision failure harness.** Simulate stable_id collision with differing file_hash to assert transaction rollback and emitted error instrumentation.

## Definition of Ready
- Entity file schema ratified with ontology and gameplay stakeholders (list of required/optional fields agreed).
- Sample entity bundle (including duplicates, collisions, invalid tags) available under fixtures.
- Database schema review complete to confirm ImportLog + Entity tables expose required columns for provenance.

## Definition of Done
- All new/updated contracts documented in `contracts/README.md` with validation steps.
- Parser + importer unit/integration tests demonstrate deterministic ordering, idempotent skip, and collision rollback.
- Metrics `importer.entities.created`, `importer.collision`, and `importer.entities.skipped_idempotent` registered with baseline tests verifying increments.
- Structured logs show per-entity ingestion summary (counts, first error) and are referenced in observability plan.

## Test Plan
- **Schema/contract tests:** Validate entity JSON fixtures against schema using contract validator script.
- **Unit tests:** Parser-focused tests verifying normalization, ordering, provenance hashing, and error reporting.
- **Integration tests:** Run importer phase twice to assert deterministic replay and idempotent skip metrics; include database rollback scenario for collision.
- **Property-based tests (optional):** Hypothesis-driven stable_id uniqueness to catch unusual ordering or whitespace variations.

## Observability
- Emit structured logs per batch summarizing counts, collision details, and manifest hash for correlation.
- Metrics: `importer.entities.created`, `importer.entities.skipped_idempotent`, `importer.collision` with histogram on per-entity duration (to feed finalization story metrics).

## Risks & Mitigations
- **Schema divergence from runtime models:** Mitigate by generating runtime model snapshots and comparing via tests.
- **Large bundle performance:** Mitigate with streaming parser and profiling in integration tests.
- **Partial failures leaving state:** Ensure transactional boundaries per phase and integration tests covering rollback path.

## Dependencies
- STORY-CDA-IMPORT-002A manifest hash + package_id registration.
- ADR-0011 provenance mapping.
- ImportLog schema availability (update in finalization story if extended fields needed).

## Feature Flags
- Controlled via `features.importer`; entity ingestion logic should early-return when disabled (tests confirm no side effects).

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/entities/entity.v1.json` (new or updated), `contracts/events/seed/entity-created.v1.json` (expected).
- Tests: `tests/importer/test_entity_parser.py`, `tests/importer/test_entity_seed_events.py`.

## Implementation Notes
- Maintain consistent sort key by capturing original relative path; include as tiebreaker for identical `(kind, stable_id)` combos (should only occur in error cases, but ensures deterministic ordering).
- Consider caching manifest metadata in parser context object to avoid redundant disk reads.
