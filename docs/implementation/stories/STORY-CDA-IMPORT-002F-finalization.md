# STORY-CDA-IMPORT-002F — Finalization & ImportLog consolidation

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Import lifecycle group

## Summary
Finalize the multi-phase importer by emitting `seed.import.complete`, consolidating ImportLog entries, computing deterministic `state_digest`, and instrumenting duration metrics. This story ensures transactional boundaries wrap the full pipeline and verifies replay invariants using golden manifests per ARCH-CDA-001 and ADR-0006 hash chain policy.

## Acceptance Criteria
- `seed.import.complete` event payload summarises entity/edge/tag/chunk counts, manifest hash, and any optional warnings; contract validated under `contracts/events/seed/import-complete.v1.json`.
- ImportLog consolidation step records final sequence numbers and ensures no gaps across phases; tests cover ordering and manifest hash persistence.
- Deterministic state fold computes `state_digest` identical across consecutive imports on a clean database; stored snapshot reference available for downstream use.
- Metric `importer.duration_ms` recorded via histogram/timer covering start→finalize; structured logs include counts and digest.
- Replay integration test runs full importer twice asserting no duplicate ledger events beyond first run (idempotency) and matching `state_digest`.

## Tasks
- [ ] **TASK-CDA-IMPORT-SUM-16A — Event schema authoring.** Define/verify `seed.import.complete` schema and add parity tests ensuring payload serialization matches contract.
- [ ] **TASK-CDA-IMPORT-SUM-16B — Completion event implementation.** Implement importer finalization step computing counts from prior phases, emitting event, and writing ImportLog summary row.
- [ ] **TASK-CDA-IMPORT-FOLD-17A — Fold helper design.** Specify deterministic fold algorithm leveraging existing projection reducers; document canonical ordering and hashing strategy.
- [ ] **TASK-CDA-IMPORT-FOLD-17B — Fold verification tests.** Add integration test using golden manifest to compute `state_digest` twice (fresh DB vs rerun) and assert equality; include failure test when data intentionally mutated.
- [ ] **TASK-CDA-IMPORT-METRIC-18A — Duration metric instrumentation.** Add timer/histogram around importer run; include unit/integration tests verifying metrics emission with fake clock.
- [ ] **TASK-CDA-IMPORT-METRIC-18B — Structured logging coverage.** Ensure final log message contains counts, manifest hash, digest, and run duration; test via logger capture.
- [ ] **TASK-CDA-IMPORT-SUM-16C — ImportLog audit closure.** Verify sequence numbers contiguous; add test ensuring ImportLog summary row references manifest hash and final digest for traceability.

## Definition of Ready
- ✅ Entity, edge, ontology, and lore phases produce counts + provenance info accessible via importer context via `ImporterRunContext.summary_counts()` with aggregation tests exercising all phase outputs. 【F:src/Adventorator/importer_context.py†L122-L208】【F:tests/importer/test_importer_context.py†L13-L138】
- ✅ Decision on `state_digest` hashing algorithm documented (reuse from ARCH-CDA-001) and helper availability confirmed in the state digest strategy note and canonical hash helper tests. 【F:docs/implementation/importer/state_digest_strategy.md†L1-L38】【F:src/Adventorator/canonical_json.py†L159-L188】【F:tests/importer/test_importer_context.py†L141-L164】
- ✅ Golden manifest fixtures available for full pipeline testing, including baseline expected digest validated by the new golden test. 【F:tests/fixtures/import/manifest/happy-path/state_digest.txt†L1-L1】【F:tests/importer/test_state_digest_fixture.py†L1-L62】

## Definition of Done
- Completion event contract validated; importer finalization emits event with deterministic payload and idempotent behavior.
- Fold tests pass using golden fixtures; mutated data test demonstrates detection (mismatched digest triggers failure/log alert).
- Metrics/logging integrated; observability doc updated with importer completion dashboard notes.
- ImportLog contains contiguous sequence entries across phases + summary row; documentation updated to describe layout.

## Test Plan
- **Contract tests:** Validate `seed.import.complete` schema via contract validator.
- **Integration tests:** Full pipeline run covering manifest through lore, verifying counts, ImportLog ordering, digest equality, idempotent re-run, and metric/log outputs.
- **Failure injection tests:** Modify ledger or content between runs to ensure digest mismatch detection surfaces explicit error.
- **Performance tests:** Measure importer duration metric with synthetic package to confirm instrumentation overhead acceptable.

## Observability
- Metrics: `importer.duration_ms` (histogram/timer) recorded; optionally `importer.phase_duration_ms{phase}` derived from earlier stories.
- Structured logs: final summary with counts, manifest hash, digest, run_id.

## Risks & Mitigations
- **Digest mismatch false positives:** Document canonical ordering/hashing; reuse canonical serialization helper and include golden fixtures.
- **Long-running imports skew metrics:** Provide sampling or quantile-based histogram; document how to interpret.
- **ImportLog gaps due to concurrency:** Ensure importer runs single-threaded per campaign; tests cover gap detection.

## Dependencies
- Completion of preceding phases (manifest, entity, edge, ontology, lore) with accessible counts.
- ADR-0006, ADR-0011 for provenance and hashing guidance.
- Database schema support for ImportLog summary row (may require migration).

## Feature Flags
- `features.importer` gating full pipeline execution; finalization should short-circuit when flag disabled (tests confirm no events emitted).

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/events/seed/import-complete.v1.json`.
- Tests: `tests/importer/test_importer_finalization.py`, `tests/importer/test_state_digest.py`.

## Alignment analysis — IMPORT ↔ CDA CORE and IPD
- Canonical JSON and hashing (CDA CORE): The `state_digest` fold must reuse canonical serialization policies to ensure the digest is stable and reproducible. Document and test any tie-breakers for fold ordering.
- Idempotency v2 composition (CDA CORE): `seed.import.complete` event should be idempotent given identical prior phases, with the same envelope and idempotency key across reruns.
- Hash chain integrity (CDA CORE): Verify that a rerun on a clean database produces the same hash chain tip; on idempotent rerun, no new events should append to the chain.
- Feature flag policy (AIDD/IPD): Confirm importer remains default-disabled; finalization should be a no-op when disabled.
- Observability alignment: Ensure duration metric integrates with repo metrics helpers and structured logs match observability conventions.

## Implementation Notes
- Consider storing computed digest + manifest hash in dedicated table for snapshot seeding; align with ARCH-CDA-001 snapshot guidance.
- Use database transaction to wrap finalization; on failure, roll back completion event and ImportLog summary to maintain consistency.
