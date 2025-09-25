# STORY-CDA-IMPORT-002C — Edge ingestion & temporal validity

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Topology subteam

## Summary
Ingest relationship definitions (`edges/*.json`) that connect previously loaded entities, validate referential integrity, capture provenance, and emit `seed.edge_created` events annotated with temporal validity metadata. Sorting and idempotency rules must mirror entity ingestion while ensuring cross-reference lookups rely on the manifest-approved package data. Edge ingestion cannot proceed without manifest + entity phases succeeding in the same transaction boundary.

## Acceptance Criteria
- Edge schema contract (new `contracts/edges/edge.v1.json` or equivalent) enforces `stable_id`, `type`, `src_ref`, `dst_ref`, and optional validity block; JSON schema rejects undefined edge types.
- Referential validation ensures `src_ref` and `dst_ref` map to known entity stable_ids (from entity phase output); failing edges abort phase with error showing missing reference(s).
- `seed.edge_created` event payload includes temporal validity (start/end event IDs or null) and provenance; passes schema validation with deterministic ordering test across runs.
- ImportLog entries persisted per edge with `{phase="edge", object_type=type, stable_id, file_hash}`; collisions handled like entity ingestion (idempotent skip vs hard fail).
- Negative tests cover missing entity reference, cyclic dependency detection (if required), and mismatched hashes.

## Tasks
- [ ] **TASK-CDA-IMPORT-EDGE-07A — Edge contract authoring.** Create/align JSON schema for edges under `contracts/edges/edge.v1.json` capturing allowed types and validity structure; update contracts README.
- [ ] **TASK-CDA-IMPORT-EDGE-07B — Parser implementation.** Build edge parser using canonical JSON normalization, referencing entity registry for referential checks.
- [ ] **TASK-CDA-IMPORT-EDGE-07C — Validation fixtures/tests.** Add fixtures for valid edges, missing src/dst references, and invalid type; ensure parser returns structured error messages.
- [ ] **TASK-CDA-IMPORT-SEED-08A — Event schema parity.** Verify or add `seed.edge_created` schema and tests comparing emitted payload to contract + runtime data structures.
- [ ] **TASK-CDA-IMPORT-SEED-08B — Ordering/idempotency integration tests.** Run importer up through edge phase twice to assert deterministic ordering, ImportLog contents, and idempotent skip metrics for identical hashes.
- [ ] **TASK-CDA-IMPORT-LOG-09A — ImportLog temporal fields.** Confirm ImportLog (or supplement) can capture validity info where applicable; add migration/test if new columns required.
- [ ] **TASK-CDA-IMPORT-LOG-09B — Transaction rollback coverage.** Write integration test demonstrating failure on missing reference causes entire edge phase rollback (no partial ImportLog or events).

## Definition of Ready
- [x] Entity ingestion outputs (stable_id registry, provenance mapping) accessible as dependency for edge parser. Documented in [edge ingestion readiness evidence](../import/edge-ingestion-readiness.md) and exercised by [`tests/importer/test_edge_readiness.py`](../../../tests/importer/test_edge_readiness.py).
- [x] Edge type taxonomy agreed with rules team; mapping from type to required attributes documented in [`edge-type-taxonomy.md`](../import/edge-type-taxonomy.md) with machine-readable source [`contracts/edges/edge-type-taxonomy.json`](../../../contracts/edges/edge-type-taxonomy.json).
- [x] Fixtures representing multi-phase packages (entities + edges) ready for tests, provided under [`tests/fixtures/import/edge_package`](../../../tests/fixtures/import/edge_package/README.md) and validated by the readiness test suite.

## Definition of Done
- Contracts validated in CI; fixtures demonstrate both success and failure cases.
- Edge importer integrated into pipeline with transactional guard, deterministic ordering, and metrics `importer.edges.created`, `importer.edges.skipped_idempotent` captured.
- Structured logs include counts of edges created/skipped and list of first failure cause; referenced by observability plan.
- Documentation appended to developer guide explaining edge referential validation approach.

## Test Plan
- **Contract tests:** Validate fixtures through contract validator script.
- **Unit tests:** Parser tests covering normalization, referential validation, provenance hash calculation.
- **Integration tests:** Run importer for manifest → entities → edges to confirm ordering, idempotency, rollback on missing reference, and ImportLog accuracy.
- **Temporal validity tests:** Ensure optional validity block (start/end) serializes correctly and rejects invalid ranges (end < start).

## Observability
- Emit structured log summarizing edge ingestion outcomes (counts, validation failures, manifest hash).
- Metrics: `importer.edges.created`, `importer.edges.skipped_idempotent`, `importer.edges.collision` (if separate), with per-phase duration instrumentation to feed finalization story.

## Risks & Mitigations
- **Stale entity registry causing false negatives:** Mitigate by ensuring entity ingest commits before edge phase or shares transaction context.
- **Edge type expansion drift:** Document schema and enforce via contract tests; coordinate with ruleset maintainers for additions.
- **Temporal validity misuse:** Validate start/end semantics with tests; add documentation for optional fields.

## Dependencies
- STORY-CDA-IMPORT-002A manifest registration.
- STORY-CDA-IMPORT-002B entity ingestion (stable_id registry availability).
- ADR-0011 provenance mapping.

## Feature Flags
- `features.importer` gating edge ingestion entry point; ensure disabled state bypasses parsing entirely.

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/edges/edge.v1.json`, `contracts/events/seed/edge-created.v1.json`.
- Tests: `tests/importer/test_edge_parser.py`, `tests/importer/test_edge_seed_events.py`.

## Implementation Notes
- Consider using streaming validation to avoid loading entire edge set into memory for large packages; maintain deterministic ordering via sort keys computed incrementally.
- Leverage referential integrity map produced by entity phase (e.g., dictionary keyed by stable_id) to provide descriptive errors listing missing references.
