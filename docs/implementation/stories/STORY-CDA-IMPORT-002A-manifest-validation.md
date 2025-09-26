# STORY-CDA-IMPORT-002A — Manifest validation & package_id registration

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Importer strike team

## Summary
Validate and register an immutable campaign package manifest before any entity ingestion. Establish the canonical JSON schema contract, deterministic hashing inputs, and synthetic `seed.manifest.validated` event emission tied to provenance guarantees from [ADR-0011](../../adr/ADR-0011-package-import-provenance.md) and the canonical envelope policy in [ADR-0006](../../adr/ADR-0006-event-envelope-and-hash-chain.md). All downstream phases will reuse the manifest's `package_id`, hash, and ordering metadata.

## Acceptance Criteria
- Manifest JSON schema captures all required fields (`package_id`, `schema_version`, `engine_contract_range`, `dependencies[]`, `content_index{}`, `ruleset_version`, `signatures[]?`, `recommended_flags{}`) with canonical formats (ULID, semver, SHA-256 hex) and is committed under `contracts/package/` with validation script coverage.
- Validation CLI (extend existing contracts validator) rejects manifests missing hashes or containing mismatched digests; failure output enumerates offending paths.
- Deterministic manifest hash computation normalizes JSON (UTF-8 NFC, sorted keys, no insignificant whitespace) and stores the resulting digest alongside manifest metadata for reuse by later phases.
- Synthetic `seed.manifest.validated` event payload matches `{package_id, manifest_hash, schema_version, ruleset_version}` and passes existing event schema checks; replay_ordinal assignment test proves deterministic emission.
- ImportLog records manifest phase entry with provenance tuple `{phase="manifest", object_type="package", stable_id=package_id, file_hash=manifest_hash}`.

## Tasks
- [ ] **TASK-CDA-IMPORT-MAN-01A — Contract authoring & review.** Draft `contracts/package/manifest.v1.json` covering required fields, numeric/string formats, and optional sections; hold review with ontology + persistence maintainers to confirm alignment with ARCH-CDA-001 data shapes.
- [ ] **TASK-CDA-IMPORT-MAN-01B — Validator integration.** Extend `scripts/validate_contracts.py` (or sibling tooling) to include manifest schema validation, with failing samples demonstrating descriptive messaging; wire into CI quality gates.
- [ ] **TASK-CDA-IMPORT-HASH-02A — Canonical serialization helper.** Implement manifest hashing utility reusing canonical JSON policy from ADR-0007; include unit tests for ordering, whitespace, and Unicode normalization edge cases.
- [ ] **TASK-CDA-IMPORT-HASH-02B — Golden manifest fixtures.** Create positive and tampered manifest fixtures under `tests/fixtures/import/manifest/` to drive hashing + validation tests; include expected digest text files.
- [ ] **TASK-CDA-IMPORT-SEED-03A — Synthetic event contract.** Define event schema (if absent) for `seed.manifest.validated` under `contracts/events/seed/` and add parity tests ensuring payload serialization matches schema.
- [ ] **TASK-CDA-IMPORT-SEED-03B — Event emission harness.** Implement importer phase stub that emits the manifest seed event, records ImportLog, and is exercised by deterministic replay tests (idempotent re-run ensures identical event envelope).
- [ ] **TASK-CDA-IMPORT-SEED-03C — Feature flag guardrails.** Ensure `features.importer` gating covers manifest validation invocation and add configuration documentation for operators.

## Definition of Ready
- Manifest field inventory approved against ADR-0011, including decisions on optional signature block handling. ✅ Documented in the readiness log inventory table covering required/optional fields and ADR alignment.【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002A-manifest-validation-readiness.md†L5-L33】
- Sample package bundle (happy path + intentionally corrupted) checked into fixtures to drive red/green tests. ✅ `tests/fixtures/import/manifest/` now provides happy-path and tampered bundles with README usage guidance.【F:tests/fixtures/import/manifest/README.md†L1-L24】【F:tests/fixtures/import/manifest/happy-path/package.manifest.json†L1-L32】【F:tests/fixtures/import/manifest/tampered/package.manifest.json†L1-L26】
- Downstream consumers (entity ingest, edge ingest) confirm expected manifest metadata outputs (package_id, manifest_hash) for dependency planning. ✅ Confirmation captured via documented references to entity and edge ingestion stories plus epic summary.【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002A-manifest-validation-readiness.md†L35-L43】

## Definition of Done
- Contract validation and hashing unit tests green in CI with golden fixtures.
- Negative test cases (missing hash, schema_version mismatch, Unicode normalization differences) produce deterministic failure messages captured in docs.
- Structured logging / metrics for manifest phase scoped and handed to observability story (no-op acceptable here but plan documented).
- Story documentation cross-links imported manifest schema in contracts README.

## Test Plan
- **Contract tests:** Run `scripts/validate_contracts.py` against new manifest schema + fixtures (expected pass/fail recorded).
- **Unit tests:** Add `tests/importer/test_manifest_validation.py` covering success, missing field, mismatched hash, Unicode, idempotent re-run.
- **Event emission tests:** Replay importer phase twice ensuring identical event_idempotency key and ImportLog entries (use database transaction fixtures).
- **CLI integration tests:** (Optional) Add `pytest` invocation for manifest validation command to assert CLI exit codes and messaging.

## Observability
- Capture manifest phase start/end structured logs with manifest hash, package_id, and validation duration.
- Register preliminary `importer.manifest.valid` counter (increments on success) to align with epic-level metrics once pipeline wiring lands.

## Risks & Mitigations
- **Schema drift:** Mitigate via golden fixtures + schema parity test tied to contracts CI.
- **Hash mismatch false positives:** Mitigate by reusing canonical JSON helper and documenting normalization rules.
- **Event payload divergence:** Mitigate via contract-first event schema and serialization round-trip tests.

## Dependencies
- ADR-0006 Event envelope hashing.
- ADR-0007 Canonical JSON policy.
- ADR-0011 Manifest provenance requirements.
- Existing ImportLog table definition (validate fields or extend as necessary).

## Feature Flags
- `features.importer` (default=false) must gate manifest validation activation.

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/package/manifest.v1.json` (new).
- Tests: `tests/importer/test_manifest_validation.py`, `tests/fixtures/import/manifest/*`.

## Alignment analysis — IMPORT ↔ CDA CORE and IPD
- Canonical JSON and hashing (CDA CORE): Manifest normalization and hash computation MUST reuse the canonical JSON policy (UTF-8 NFC, sorted keys, integer-only numerics) from ADR-0007 to ensure parity with ledger hashing. Golden vectors should prove that semantically equivalent inputs produce identical digests.
- Idempotency v2 composition (CDA CORE): Synthetic `seed.manifest.validated` events must compute idempotency keys using the v2 policy that excludes volatile fields (for example, replay_ordinal or execution context IDs). Event payloads should be stable given the same manifest, producing identical envelopes across re-runs.
- Deterministic ordering (CDA CORE): If multiple manifest-related events ever occur (e.g., multi-file manifests), define and test a deterministic sort key. For the single-manifest case, assert a fixed `replay_ordinal` and stable envelope hash between runs.
- Feature flag policy (AIDD/IPD): Ensure `features.importer` defaults to false in config and tests assert the disabled path is a no-op. Any dev-only exceptions must be documented alongside rollback guidance.
- Observability alignment (IPD/CDA): Use structured logging and metric helpers already present in the repo; emit a minimal counter for successful validations and ensure failure logs do not leak full manifest contents (only stable IDs and hashes).

## Implementation Notes
- Leverage existing hash chain helper from event ledger (if available) to ensure consistent SHA-256 outputs.
- Consider storing manifest hash in ImportLog for faster debugging (subject to schema review in importer finalization story).
