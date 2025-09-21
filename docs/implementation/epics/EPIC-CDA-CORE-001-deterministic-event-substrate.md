# EPIC-CDA-CORE-001 — Deterministic Event Substrate

**Objective.** Establish the canonical, append-only event substrate (envelope, canonical JSON, hash chain, idempotency, replay ordinal guarantees) required for all downstream Campaign Data Architecture capabilities (importer, executor, snapshots, migrations).

**Owner.** Campaign Data / Engine working group (persistence, executor, rules, observability, contracts).

**Key risks.** Serialization drift across platforms, silent hash chain corruption, improper idempotency key collisions, and premature schema expansion without contract governance.

**Linked assets.**
- [ARCH-CDA-001 — Campaign Data & Deterministic World State Architecture](../../architecture/ARCH-CDA-001-campaign-data-architecture.md)
- [ADR-0006 — Event Envelope & Hash Chain](../../adr/ADR-0006-event-envelope-and-hash-chain.md)
- [ADR-0007 — Canonical JSON & Numeric Policy](../../adr/ADR-0007-canonical-json-numeric-policy.md)
- AIDD governance: [DoR/DoD Guide](../dor-dod-guide.md)

**Definition of Ready.** Stories must additionally provide:
- Enumerated envelope field list (final names, types, nullability) validated against ADR-0006.
- Canonical JSON policy conformance checklist (key ordering, null omission, integer-only) referencing ADR-0007.
- Test vector plan (golden inputs/outputs + negative cases for floats / key ordering / unicode normalization).
- Idempotency key composition string frozen (exact concatenation order documented) with collision risk assessment.
- Observability specification (metrics + structured log fields) for chain tip, replay ordinal, conflict, and idempotency reuse.

**Definition of Done.**
- Alembic migration(s) adding/altering `events` table with all envelope columns, constraints, and indexes merged.
- Canonical encoder module + golden test vectors committed; cross-run determinism test passes (at least two platform seeds in CI matrix if available).
- Hash chain continuity tests validate `prev_event_hash` correctness and genesis hash constant matches ADR-0006.
- Idempotency key logic exposes helper producing stable 16-byte prefix; retry storm test shows single persisted event.
- Structured logging emits chain tip hash, replay_ordinal, state placeholder (future digest), idempotency_key, and applies conflict outcome format.
- Metrics registered: `events.applied`, `events.conflict`, `events.hash_mismatch`, `events.idempotent_reuse` (names documented in observability guide).
- Lint / type / test quality gates green; no floats or NaN allowed anywhere in payload path (tests enforce rejection).
- Documentation (architecture appendix or module docstring) explains encoder invariants and rollback strategy.

---

## Stories

### STORY-CDA-CORE-001A — Event envelope migration & constraints ([#189](https://github.com/crashtestbrandt/Adventorator/issues/189))
*Epic linkage:* Creates physical substrate (schema & DB invariants) enabling deterministic chain.

- **Summary.** Introduce `events` table (or evolve existing) with full envelope columns, replay ordinal trigger/constraint, hash chain fields, idempotency uniqueness, and necessary indexes.
- **Acceptance criteria.**
  - Migration adds columns: `campaign_id`, `event_id` PK, `replay_ordinal` (gap-free trigger), `event_type`, `event_schema_version`, `world_time`, `wall_time_utc`, `prev_event_hash` (BINARY/bytea 32), `payload_hash` (BINARY/bytea 32), `idempotency_key` (BINARY/bytea 16), `actor_id`, `plan_id`, `execution_request_id`, `approved_by`, `payload` (JSONB), `migrator_applied_from` (nullable int), plus supporting FKs.
  - Unique constraints: `(campaign_id, replay_ordinal)`, `(campaign_id, idempotency_key)`.
  - Trigger enforces dense `replay_ordinal` per campaign.
  - Genesis insertion test validates zeroed `prev_event_hash` and hash match with ADR constant.
- **Tasks.**
  - [ ] `TASK-CDA-CORE-MIG-01` — Author Alembic migration for envelope & constraints.
  - [ ] `TASK-CDA-CORE-TRIG-02` — Implement replay ordinal trigger & test.
  - [ ] `TASK-CDA-CORE-GEN-03` — Genesis event creation utility & test verifying hash.
- **DoR.**
  - Final column spec reviewed vs ADR-0006 field list.
  - Hash algorithm (SHA-256) library choice confirmed.
- **DoD.**
  - Migration reversible; downgrade removes new columns and trigger.
  - Tests cover duplicate idempotency key rejection.

### STORY-CDA-CORE-001B — Canonical JSON encoder & golden vectors ([#190](https://github.com/crashtestbrandt/Adventorator/issues/190))
*Epic linkage:* Ensures payload hashing & idempotency rely on stable serialization.

- **Summary.** Implement canonical encoder enforcing ordering, null elision, UTF-8 NFC normalization, integer-only numeric policy; generate deterministic hash.
- **Acceptance criteria.**
  - Encoder outputs identical byte sequence for logically equivalent inputs across runs.
  - Unicode composed/decomposed forms produce identical hashes (test with accented examples).
  - Float presence triggers explicit ValueError with guidance.
  - Golden vector fixtures (min 10) committed with precomputed hashes; CI test verifies no drift.
- **Tasks.**
  - [ ] `TASK-CDA-CORE-ENC-04` — Implement canonical encoder & hash helper.
  - [ ] `TASK-CDA-CORE-VECT-05` — Add golden vector fixtures & test.
  - [ ] `TASK-CDA-CORE-UNICODE-06` — Unicode normalization regression test.
- **DoR.**
  - Fixture schema & naming convention agreed.
  - Negative case list enumerated (floats, NaN, key reordering, null retention attempts).
- **DoD.**
  - Encoder documented with invariants and rollback note.
  - All golden vectors hashed & reviewed.

### STORY-CDA-CORE-001C — Hash chain computation & verification ([#191](https://github.com/crashtestbrandt/Adventorator/issues/191))
*Epic linkage:* Secures tamper-evident event history.

- **Summary.** Integrate hash chain update logic in event creation path; supply verification routine and mismatch alert hook.
- **Acceptance criteria.**
  - On insert, `payload_hash = sha256(canonical_payload)`, `prev_event_hash` references prior event’s `payload_hash` (genesis zeroes).
  - Verification routine traverses chain; mismatch test simulates corruption and raises defined exception / logs metric.
  - Metric `events.hash_mismatch` increments on detection; structured log event includes offending ordinal & expected hash.
- **Tasks.**
  - [ ] `TASK-CDA-CORE-CHAIN-07` — Chain computation logic & insert integration.
  - [ ] `TASK-CDA-CORE-VERIFY-08` — Verification routine & unit test with injected fault.
  - [ ] `TASK-CDA-CORE-OBS-09` — Metric + structured log wiring for mismatches.
- **DoR.**
  - Chain mismatch severity classification defined (alert vs warn).
- **DoD.**
  - Fault injection test ensures detection path executed.
  - Observability guide updated with mismatch handling.

### STORY-CDA-CORE-001D — Idempotency key generation & collision tests ([#192](https://github.com/crashtestbrandt/Adventorator/issues/192))
*Epic linkage:* Prevents duplicate event emission on network/client retries.

- **Summary.** Provide helper constructing 16-byte key prefix per ADR composition spec; integrate into executor stub for early reuse; test retry storms.
- **Acceptance criteria.**
  - Deterministic composition: `SHA256(plan_id || campaign_id || event_type || tool_name || ruleset_version || canonical(args_json))[:16]`.
  - Retry loop (≥10 simulated retries) produces one stored row; subsequent attempts return existing event metadata object.
  - Collision fuzz test (random inputs N=10k) yields zero observed collisions (document expected probability).
- **Tasks.**
  - [ ] `TASK-CDA-CORE-IDEMP-10` — Idempotency helper implementation.
  - [ ] `TASK-CDA-CORE-RETRY-11` — Retry storm test harness.
  - [ ] `TASK-CDA-CORE-FUZZ-12` — Collision fuzz test & report.
- **DoR.**
  - Composition order finalized & documented.
- **DoD.**
  - Helper reused by executor prototype (story linkage).
  - Fuzz test artifacts stored (log or markdown summary).

### STORY-CDA-CORE-001E — Observability & metric taxonomy ([#193](https://github.com/crashtestbrandt/Adventorator/issues/193))
*Epic linkage:* Supplies foundational telemetry for subsequent epics (executor, snapshots, importer).

- **Summary.** Register counters/histograms, structured log fields; expose chain tip inspection API for verification jobs.
- **Acceptance criteria.**
  - Metrics present: `events.applied`, `events.conflict` (placeholder until executor), `events.idempotent_reuse`, `events.hash_mismatch`, latency histogram `event.apply.latency_ms` (stub timing instrumentation).
  - Structured logs include: event_id, replay_ordinal, chain_tip_hash, idempotency_key_hex, plan_id (if provided), execution_request_id (if provided).
  - Chain tip endpoint/function returns last (replay_ordinal, payload_hash).
- **Tasks.**
  - [ ] `TASK-CDA-CORE-METRIC-13` — Register metrics & document names.
  - [ ] `TASK-CDA-CORE-LOG-14` — Add structured logging integration.
  - [ ] `TASK-CDA-CORE-TIP-15` — Chain tip accessor & test.
- **DoR.**
  - Metric names vetted vs existing observability taxonomy.
- **DoD.**
  - Logging & metrics guides updated.
  - Basic latency timing test recorded.

---

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | https://github.com/crashtestbrandt/Adventorator/issues/187 | EPIC-CDA-CORE-001 master issue. |
| Architecture | ../../architecture/ARCH-CDA-001-campaign-data-architecture.md | Sections 3.2, 5, 6, 14 reference substrate. |
| ADR-0006 | ../../adr/ADR-0006-event-envelope-and-hash-chain.md | Envelope fields & chain rules. |
| ADR-0007 | ../../adr/ADR-0007-canonical-json-numeric-policy.md | Serialization invariants. |

Update the table as GitHub issues are created to preserve AIDD traceability.
