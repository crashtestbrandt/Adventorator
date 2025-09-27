# STORY-CDA-IMPORT-002G — Idempotent re-run & rollback tests

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Reliability & QA team

## Summary
Validate importer resilience by exercising repeated runs of the same package, failure injection mid-phase, and transactional rollback guarantees. Confirm metrics, logs, and ImportLog entries accurately reflect idempotent skips and rolled-back operations. This story codifies replay determinism mandated by ARCH-CDA-001 and ADR-0011.

## Acceptance Criteria
- Second import run using identical package emits no new entity/edge/tag/chunk events; tests assert unchanged replay_ordinal sequence and ImportLog entries annotated as idempotent skips.
- Failure injection harness simulates mid-phase collision and missing dependency file, asserting transaction rollback leaves no partial events or ImportLog rows.
- Metrics include `importer.idempotent` counter and per-phase rollback counters; structured logs capture scenario + outcome with manifest hash correlation.
- Documentation records recovery playbook for operators (retry guidance, log interpretation).

## Tasks
- [ ] **TASK-CDA-IMPORT-RERUN-19A — Replay baseline test.** Implement integration test running full importer twice on clean DB, asserting event counts, ImportLog state, metrics, and `state_digest` equality.
- [ ] **TASK-CDA-IMPORT-RERUN-19B — Ledger hash chain verification.** Extend test to check hash chain tip unchanged after second run and that idempotent path does not append events.
- [ ] **TASK-CDA-IMPORT-FAIL-20A — Failure injection harness.** Build utility enabling targeted failure scenarios (entity collision, missing file, invalid YAML) triggered during import phases.
- [ ] **TASK-CDA-IMPORT-FAIL-20B — Transaction rollback tests.** Use harness to assert DB state, ImportLog, and metrics remain unchanged post-failure; include log assertions for rollback notice.
- [ ] **TASK-CDA-IMPORT-METRIC-21A — Metrics instrumentation.** Register `importer.idempotent` and `importer.rollback` counters; add tests verifying increments with failure scenarios.
- [ ] **TASK-CDA-IMPORT-METRIC-21B — Observability docs update.** Document new metrics/log patterns in observability guide and importer runbook.
- [ ] **TASK-CDA-IMPORT-RERUN-19C — CLI/automation support.** Provide script or Make target to execute idempotency regression suite for operators/CI.

## Definition of Ready
- ✅ Prior stories deliver deterministic importer pipeline with accessible manifest hash, counts, and metrics hooks, covered by `ImporterRunContext`, golden digest regression, and importer metrics suites. 【F:src/Adventorator/importer_context.py†L1-L189】【F:tests/importer/test_importer_context.py†L13-L138】【F:tests/importer/test_state_digest_fixture.py†L21-L62】【F:src/Adventorator/importer.py†L276-L318】【F:tests/importer/test_entity_metrics.py†L18-L136】
- ✅ Golden manifest fixture available for baseline re-run tests; corrupted fixtures prepared for failure injection scenarios. 【F:tests/fixtures/import/manifest/README.md†L7-L21】【F:tests/fixtures/import/manifest/happy-path/state_digest.txt†L1-L1】【F:tests/fixtures/import/manifest/tampered/entities/npc.json†L1-L11】【F:tests/fixtures/import/manifest/collision-test/entities/npc1.json†L1-L7】
- ✅ Rollback expectations are codified in the importer phases: entity, edge, and lore handlers hard-fail on stable-ID or hash divergence after incrementing collision metrics, emit phase-complete logs, and avoid ImportLog writes, with regression tests asserting collision runs leave creation counters at zero. ADR-0011 anchors the deterministic ImportLog ordering relied upon for rerun assertions. 【F:src/Adventorator/importer.py†L276-L318】【F:src/Adventorator/importer.py†L565-L643】【F:src/Adventorator/importer.py†L1474-L1519】【F:tests/importer/test_entity_metrics.py†L93-L136】【F:tests/importer/test_edge_metrics.py†L95-L129】【F:tests/test_lore_chunking.py†L833-L867】【F:docs/adr/ADR-0011-package-import-provenance.md†L12-L16】

## Definition of Done
- Idempotent re-run tests pass in CI; failure injection scenarios produce expected metrics/logs and leave database clean.
- Runbook updated with retry procedures, log signatures, and metric alerting thresholds.
- Observability dashboards (if applicable) annotated with idempotent/rollback counters.
- Importer CLI/automation documented for QA/regression runs.

## Test Plan
- **Integration tests:** Automated importer rerun test verifying zero new events/ImportLog entries; failure injection tests covering collision, missing file, invalid schema.
- **Hash chain verification:** Assert ledger hash tip unchanged after rerun using helper from ADR-0006 implementation.
- **Metric/log capture tests:** Use instrumentation capture to ensure expected counters/log lines emitted for idempotent and rollback scenarios.
- **Manual validation:** Document operator steps to simulate failure and confirm rollback (optional but recommended).

## Observability
- Metrics: `importer.idempotent`, `importer.rollback`, per-phase counters reused from earlier stories.
- Structured logs: include scenario identifier, manifest hash, affected phase, outcome (idempotent, rollback, failure reason).

## Risks & Mitigations
- **Flaky integration tests due to timing:** Use deterministic fixtures and control time/IDs in tests.
- **Incomplete rollback coverage:** Expand harness scenarios iteratively; document gaps for follow-up.
- **Operator confusion interpreting metrics/logs:** Provide runbook updates and sample queries/dashboard references.

## Dependencies
- All prior importer phases implemented with deterministic ordering and metrics hooks.
- Failure injection hooks or ability to monkeypatch importer pipeline safely (design with persistence team).
- Observability documentation baseline (from earlier stories) to extend.

## Feature Flags
- `features.importer` (global); ensure rerun harness respects flag states in tests.

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Tests: `tests/importer/test_importer_idempotency.py`, `tests/importer/test_importer_rollback.py`.

## Alignment analysis — IMPORT ↔ CDA CORE and IPD
- Hash chain integrity (CDA CORE): Rerun tests must assert that the ledger hash chain tip and all envelope hashes remain unchanged for identical inputs, confirming no new events are appended.
- Idempotency v2 policy (CDA CORE): Ensure idempotency key computation excludes volatile fields; fixtures should demonstrate identical keys and envelopes on repeat imports.
- Deterministic ordering (CDA CORE): Validate that replay_ordinal sequences remain consistent across reruns; deviations should fail tests with clear diffs.
- Observability alignment (IPD): Counters for idempotent paths and rollbacks should use established metrics helpers; logs must avoid leaking raw content paths beyond stable IDs and hashes.
- Feature flag policy (AIDD/IPD): Confirm disabled importer leads to a pure no-op in rerun tests; enabled path demonstrates idempotent behavior.

## Implementation Notes
- Consider running rerun tests using database transaction snapshots to speed up repeated runs.
- Provide CLI harness to intentionally corrupt file between runs to validate detection/rollback messaging.
