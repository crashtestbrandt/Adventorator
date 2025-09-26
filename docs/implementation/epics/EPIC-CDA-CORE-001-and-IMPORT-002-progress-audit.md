# EPIC-CDA-CORE-001 & EPIC-CDA-IMPORT-002 Progress Validation

## Methodology
- Reviewed canonical event substrate code (`events/envelope.py`), canonical JSON encoder, importer phases, and migrations to verify implementation against epic acceptance criteria.【F:src/Adventorator/events/envelope.py†L1-L420】【F:src/Adventorator/canonical_json.py†L1-L179】【F:migrations/versions/cda001a0001_event_envelope_upgrade.py†L118-L360】【F:src/Adventorator/importer.py†L1-L2050】
- Inspected targeted automated tests covering canonical JSON, hash chain verification, idempotency keys, importer workflow, and idempotent rerun guarantees.【F:tests/test_event_envelope_story_cda_core_001a.py†L1-L74】【F:tests/test_event_idempotency_unique_constraint.py†L1-L73】【F:tests/test_hash_chain_verification.py†L1-L297】【F:tests/test_idempotency_key_v2.py†L1-L177】【F:tests/importer/test_integration_complete_workflow.py†L1-L247】【F:tests/importer/test_importer_idempotency.py†L1-L200】
- Executed focused pytest suites validating both epics end-to-end (ledger substrate + importer pipeline).【5ca5d4†L1-L2】【3ef81e†L1-L3】

## EPIC-CDA-CORE-001 — Deterministic Event Substrate

### Envelope substrate (Story 001A)
- Alembic migration materializes the full deterministic event envelope with required columns, unique constraints, trigger-based replay ordinal enforcement, and legacy data backfill.【F:migrations/versions/cda001a0001_event_envelope_upgrade.py†L144-L329】 Tests assert genesis invariants and replay ordinal gap rejection.【F:tests/test_event_envelope_story_cda_core_001a.py†L1-L74】
- Duplicate idempotency keys raise constraint violations, closing HR-001.【F:tests/test_event_idempotency_unique_constraint.py†L1-L73】

### Canonical serialization & payload hashing (Story 001B)
- Dedicated canonical JSON encoder enforces UTF-8 NFC normalization, lexicographic ordering, null elision, and integer-only numeric policy; helper hashes canonical bytes.【F:src/Adventorator/canonical_json.py†L1-L172】 Tests cover golden fixtures and policy enforcement (referenced above).
- Envelope helpers delegate to canonical encoder to guarantee deterministic payload hashing and envelope digests.【F:src/Adventorator/events/envelope.py†L30-L97】

### Hash chain computation & verification (Story 001C)
- `verify_hash_chain` traverses ordered events, compares stored prev hashes, logs structured mismatches, increments `events.hash_mismatch`, and raises `HashChainMismatchError` on corruption.【F:src/Adventorator/events/envelope.py†L220-L298】 Test suite injects faults and validates metrics/log hooks.【F:tests/test_hash_chain_verification.py†L1-L297】
- Chain tip accessor fetches latest ordinal/hash for replay bookkeeping.【F:src/Adventorator/events/envelope.py†L300-L329】 Observability tests confirm exposure.【F:tests/test_observability_cda_core_001e.py†L1-L206】

### Idempotency key evolution (Story 001D)
- `compute_idempotency_key_v2` implements ADR composition (plan, campaign, type, tool, ruleset, canonical args) with length-prefix framing and explicit `None` sentinel.【F:src/Adventorator/events/envelope.py†L133-L187】
- Test suites verify determinism, distinctness from v1, collision fuzzing, and retry harness scenarios (see referenced tests and importer usage at seed emission).【F:tests/test_idempotency_key_v2.py†L1-L177】【F:tests/test_retry_storm_harness.py†L120-L315】
- Executor prototype demonstrates v2 reuse path, awaiting integration with production executor (note TODO for metrics increment).【F:src/Adventorator/executor_prototype.py†L1-L191】

### Observability & metrics (Story 001E)
- Structured logging helpers emit chain tip, ordinal, campaign, idempotency key hex, and optional latency; counters increment `events.applied` and reuse metrics, while histograms proxy latency recording.【F:src/Adventorator/events/envelope.py†L331-L401】
- Metrics module provides reusable counter/histogram helpers and dedicated functions for conflict/reuse accounting.【F:src/Adventorator/metrics.py†L10-L86】 Observability tests exercise logging and counter increments.【F:tests/test_observability_cda_core_001e.py†L1-L206】

### Outstanding gaps / risks
- Executor integration still prototype-only; production path must adopt v2 keys, log reuse, and increment metrics (referenced TODO).【F:src/Adventorator/executor_prototype.py†L70-L105】
- Migration exposes length-prefixed idempotency computation but importer/emitter still emit placeholder envelopes lacking replay ordinals; importer integration must wire into ledger before declaring full DoD.【F:migrations/versions/cda001a0001_event_envelope_upgrade.py†L209-L216】【F:src/Adventorator/importer.py†L326-L344】

## EPIC-CDA-IMPORT-002 — Package Import & Provenance

### Manifest validation & provenance (Story 002A)
- `ManifestPhase.validate_and_register` enforces feature flag, invokes schema validation, computes manifest hash, assembles seed event payload, and prepares ImportLog metadata; rollback instrumentation records failures.【F:src/Adventorator/importer.py†L264-L324】 Tests ensure invalid manifests raise descriptive errors via contract fixtures.【F:tests/importer/test_contract_validation.py†L1-L210】
- Placeholder emitter returns deterministic envelope stub pending ledger wiring, aligning with current substrate readiness.【F:src/Adventorator/importer.py†L326-L344】

### Entity ingestion & seed events (Story 002B)
- Entity phase enforces deterministic ordering (`kind`, `stable_id`, `source_path`), schema validation, canonical content hashing, provenance augmentation, idempotent collision handling, ImportLog entry creation, and metrics/log emission.【F:src/Adventorator/importer.py†L420-L533】 Seed events include provenance, optional traits/props, and schema validation before emission.【F:src/Adventorator/importer.py†L621-L652】
- Integration test covers manifest→entity pipeline, verifying payload determinism and ImportLog sequencing.【F:tests/importer/test_integration_complete_workflow.py†L1-L247】

### Edge ingestion & temporal validity (Story 002C)
- Edge phase validates taxonomy constraints, referential integrity against known entities, content index hashes, deterministic ordering, collision detection with metrics, and provenance tagging before seed event creation.【F:src/Adventorator/importer.py†L656-L880】 Dedicated tests cover schema enforcement, provenance, and metric behavior.【F:tests/importer/test_edge_parser.py†L1-L210】【F:tests/importer/test_edge_seed_events.py†L1-L220】

### Ontology & lore phases (Stories 002D/002E)
- Ontology and lore helpers (not excerpted above) follow similar patterns—schema validation, provenance tagging, deterministic ordering, and metrics/histogram instrumentation. Tests confirm duplicate handling, content hashing, and audience enforcement per ADR-0011.【F:src/Adventorator/importer.py†L900-L1808】【F:tests/importer/test_ontology_ingestion.py†L1-L240】【F:tests/importer/test_state_digest.py†L1-L210】

### Finalization, state digest, and idempotent reruns (Stories 002F/002G)
- `FinalizationPhase` computes per-phase counts, state digest, duration histogram, structured logs, and import summary event; detects idempotent reruns by aggregating skipped counters and records provenance in ImportLog summary.【F:src/Adventorator/importer.py†L1811-L2003】
- `run_full_import_with_database` orchestrates all phases, persists events/import logs, enforces feature flags, and supports reruns via `ImporterRunContext`. End-to-end tests demonstrate identical state digests, stable ImportLog ordering, and replay ordinal stability across reruns.【F:src/Adventorator/importer.py†L2036-L2498】【F:tests/importer/test_importer_idempotency.py†L1-L200】

### Outstanding gaps / risks
- Seed event emitters still return placeholders with `replay_ordinal=None`; integration with deterministic ledger is pending, blocking full provenance replay guarantees.【F:src/Adventorator/importer.py†L326-L344】【F:src/Adventorator/importer.py†L1917-L1932】
- Metrics tagging relies on logging tags because counter backend lacks label support; ensure downstream observability requirements accept this interim approach.【F:src/Adventorator/importer.py†L24-L80】
- Importer idempotent counter currently inferred from skipped counts; explicit DB check prior to rerun could tighten detection (see idempotency test commentary).【F:tests/importer/test_importer_idempotency.py†L136-L160】

## Summary
- Core ledger substrate meets migration, canonicalization, hash-chain verification, idempotency helper, and observability requirements, with executor wiring outstanding before production enablement.
- Importer pipeline implements manifest validation through finalization with deterministic ordering, provenance capture, and state digest verification; ledger/seed event integration remains the primary open dependency to achieve full replay guarantees.
- Targeted automated suites pass, providing regression coverage for both epics’ critical paths (see Methodology test executions).【5ca5d4†L1-L2】【3ef81e†L1-L3】
