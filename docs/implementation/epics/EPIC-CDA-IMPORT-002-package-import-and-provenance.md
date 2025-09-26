# EPIC-CDA-IMPORT-002 — Package Import & Provenance

**Objective.** Implement deterministic, auditable campaign package import: manifest validation, ordered ingestion of entities/edges/ontology/content chunks, synthetic `seed.*` events emission, and provenance recording enabling full replay & lineage guarantees.

**Owner.** Campaign Data / Content Pipeline working group (importer, persistence, ontology, retrieval, contracts).

**Key risks.** Non-deterministic iteration leading to divergent replays, incomplete provenance (missing file hashes), collision handling ambiguity for `stable_id`, and drift between on-disk package artifacts and recorded ledger events.

**Linked assets.**
- [ARCH-CDA-001 — Campaign Data & Deterministic World State Architecture](../../architecture/ARCH-CDA-001-campaign-data-architecture.md)
- [ADR-0011 — Package Import Provenance](../../adr/ADR-0011-package-import-provenance.md)
- [ADR-0006 — Event Envelope & Hash Chain](../../adr/ADR-0006-event-envelope-and-hash-chain.md) (for synthetic seed events)
- AIDD governance: [DoR/DoD Guide](../dor-dod-guide.md)

**Definition of Ready.** Stories must additionally provide:
- Manifest JSON schema (version, dependencies, content index, signatures) reviewed against ADR-0011.
- Deterministic ordering specification (tuple sort key: `(kind, stable_id)` plus secondary path tie-breaker) documented.
- Collision policy decisions enumerated (same `stable_id` + different `file_hash` ⇒ hard fail; identical hash ⇒ idempotent skip) with negative test plan.
- List of synthetic event types to be emitted (`seed.manifest.validated`, `seed.entity_created`, `seed.edge_created`, `seed.tag_registered`, `seed.content_chunk_ingested`, `seed.import.complete`) with schema references or placeholders.
- Provenance field mapping table (entity/edge/chunk → {package_id, source_path, file_hash}).
- Rollback strategy (imports transactional per phase; re-run yields identical ledger segment or aborts cleanly).

**Definition of Done.**
- Importer module implements phased pipeline (manifest → entities → edges → ontology → lore → finalize) with transactional boundaries and idempotent re-entry.
- Synthetic seed events emitted deterministically with stable replay_ordinal assignment and canonical payload hashing.
- Provenance recorded: ImportLog table populated with sequence_no, phase, object_type, stable_id, file_hash, action, timestamp, manifest_hash.
- Collision tests assert correct failure path & message content (includes conflicting stable_id and hash deltas).
- Replay test: Fresh DB + imported package → derived `state_digest` stable across two consecutive imports (no duplicate ledger events beyond first attempt).
- Structured logging includes per-phase counts and manifest hash; metrics registered: `importer.entities.created`, `importer.edges.created`, `importer.tags.registered`, `importer.chunks.ingested`, `importer.collision`, `importer.duration_ms` (histogram).
- Feature flag (e.g., `features.importer`) governs activation; disabled path leaves legacy/manual seeding unmodified.
- Quality gates green; golden manifest & sample content fixtures committed.
- Documentation (developer guide or architecture appendix) explains phase ordering, failure semantics, and provenance guarantees.

---

## Stories

### STORY-CDA-IMPORT-002A — Manifest validation & package_id registration
*Epic linkage:* Establishes trusted seed manifest and genesis for subsequent phases.

Implementation plan: [STORY-CDA-IMPORT-002A — Manifest validation & package_id registration](/docs/implementation/stories/STORY-CDA-IMPORT-002A-manifest-validation.md)

- **Summary.** Validate `package.manifest.json` (schema_version, engine_contract_range, content_index hashes, signatures) and record package row + synthetic `seed.manifest.validated` event.
- **Acceptance criteria.**
  - Manifest schema JSON in `contracts/package/` validated by existing script or extended checker.
  - Invalid schema_version or missing file hash fails with descriptive error.
  - Event payload includes canonical subset: `{package_id, manifest_hash, schema_version, ruleset_version}`.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-MAN-01` — Manifest schema + validator.
  - [ ] `TASK-CDA-IMPORT-HASH-02` — Manifest hashing + test.
  - [ ] `TASK-CDA-IMPORT-SEED-03` — Emit `seed.manifest.validated` event.
- **DoR.**
  - Manifest fields list stabilized (ADR alignment).
- **DoD.**
  - Negative tests: missing field, tampered hash.

### STORY-CDA-IMPORT-002B — Entity ingestion & synthetic events
*Epic linkage:* Deterministically loads entity definitions with provenance & seed events.

Implementation plan: [STORY-CDA-IMPORT-002B — Entity ingestion & synthetic events](/docs/implementation/stories/STORY-CDA-IMPORT-002B-entity-ingestion.md)

- **Summary.** Parse entity files, validate stable_id uniqueness, record provenance, emit `seed.entity_created` events in sorted order.
- **Acceptance criteria.**
  - Sort order deterministic; test demonstrates consistent event ordering across runs.
  - Payload includes: `stable_id, kind, name, tags[], affordances[], provenance{package_id, source_path, file_hash}`.
  - Collision (same stable_id different hash) aborts phase; identical hash skip counts toward idempotency metric.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-ENT-04` — Entity parser & validation.
  - [ ] `TASK-CDA-IMPORT-PROV-05` — Provenance capture & ImportLog entries.
  - [ ] `TASK-CDA-IMPORT-SEED-06` — Emit entity seed events + ordering test.
- **DoR.**
  - Entity file schema agreed & documented.
- **DoD.**
  - Collision failure test implemented.

### STORY-CDA-IMPORT-002C — Edge ingestion & temporal validity
*Epic linkage:* Adds relational topology with validity metadata.

Implementation plan: [STORY-CDA-IMPORT-002C — Edge ingestion & temporal validity](/docs/implementation/stories/STORY-CDA-IMPORT-002C-edge-ingestion.md)

- **Summary.** Ingest edge definitions (contains, adjacent_to, member_of, bound_by_rule) and emit `seed.edge_created` events.
- **Acceptance criteria.**
  - Validation ensures referenced entities exist (fail fast otherwise).
  - Payload includes `stable_id, type, src_ref, dst_ref, provenance{...}`.
  - ImportLog entries reflect edges with phase tagging.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-EDGE-07` — Edge parser & referential validation.
  - [ ] `TASK-CDA-IMPORT-SEED-08` — Emit edge seed events.
  - [ ] `TASK-CDA-IMPORT-LOG-09` — ImportLog persistence test.
- **DoR.**
  - Edge file schema stable.
- **DoD.**
  - Referential failure test present.

### STORY-CDA-IMPORT-002D — Ontology (tags & affordances) registration
*Epic linkage:* Seeds controlled vocabulary before dependent features (retrieval, predicate gating).

Implementation plan: [STORY-CDA-IMPORT-002D — Ontology (tags & affordances) registration](/docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md)

- **Summary.** Parse ontology files, register tags/affordances, emit `seed.tag_registered` events.
- **Acceptance criteria.**
  - Duplicate tag with same hash idempotent; differing definition fails import.
  - Payload: `tag_id, category, version, provenance{...}`.
  - Metrics: `importer.tags.registered` increments per unique registration.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-ONTO-10` — Ontology parser & validation.
  - [ ] `TASK-CDA-IMPORT-SEED-11` — Emit tag seed events.
  - [ ] `TASK-CDA-IMPORT-METRIC-12` — Metrics & tests.
- **DoR.**
  - Ontology schema accepted.
- **DoD.**
  - Duplicate conflict test implemented.

### STORY-CDA-IMPORT-002E — Lore content chunking & ingestion
*Epic linkage:* Provides retrieval-ready modular content with provenance.

Implementation plan: [STORY-CDA-IMPORT-002E — Lore content chunking & ingestion](/docs/implementation/stories/STORY-CDA-IMPORT-002E-lore-chunking.md)

- **Summary.** Chunk markdown lore with front-matter, register `ContentChunk` rows, emit `seed.content_chunk_ingested` events.
- **Acceptance criteria.**
  - Audience enforcement fields (`audience`) captured; optional embedding metadata gated behind flag.
  - Payload includes `chunk_id, title, audience, tags[], source_path, content_hash`.
  - Deterministic chunk ordering test ensures stable event sequence.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-CHUNK-13` — Chunker implementation & hash.
  - [ ] `TASK-CDA-IMPORT-SEED-14` — Emit content chunk seed events.
  - [ ] `TASK-CDA-IMPORT-AUD-15` — Audience enforcement tests.
- **DoR.**
  - Front-matter schema frozen.
- **DoD.**
  - Unicode normalization test for content hashing.

### STORY-CDA-IMPORT-002F — Finalization & ImportLog consolidation
*Epic linkage:* Closes import transaction and asserts replay invariants.

Implementation plan: [STORY-CDA-IMPORT-002F — Finalization & ImportLog consolidation](/docs/implementation/stories/STORY-CDA-IMPORT-002F-finalization.md)

- **Summary.** Emit `seed.import.complete` event summarizing counts, finalize ImportLog, and run post-import replay sanity (fold to state_digest).
- **Acceptance criteria.**
  - Summary event payload: `{entity_count, edge_count, tag_count, chunk_count, manifest_hash}`.
  - Post-import fold produces deterministic `state_digest`; stored for downstream snapshot reference.
  - Metric `importer.duration_ms` recorded (start → finalize).
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-SUM-16` — Import completion event & counts.
  - [ ] `TASK-CDA-IMPORT-FOLD-17` — Fold & state_digest verification test.
  - [ ] `TASK-CDA-IMPORT-METRIC-18` — Duration metric + structured log.
- **DoR.**
  - Digest computation helper available (or stub planned in CORE epic).
- **DoD.**
  - Replay test passes; structured log shows counts.

### STORY-CDA-IMPORT-002G — Idempotent re-run & rollback tests
*Epic linkage:* Validates resilience and re-entrant design.

Implementation plan: [STORY-CDA-IMPORT-002G — Idempotent re-run & rollback tests](/docs/implementation/stories/STORY-CDA-IMPORT-002G-idempotent-rerun.md)

- **Summary.** Ensure repeated import of the same package produces no additional seed events (or clearly deduplicated) and partial failures leave no inconsistent state.
- **Acceptance criteria.**
  - Second import run yields zero new entity/edge/tag/chunk seed events; ImportLog notes idempotent outcomes.
  - Simulated failure mid-phase (entity collision) rolls back transaction; no partial events persisted.
  - Metrics include `importer.idempotent` counter.
- **Tasks.**
  - [ ] `TASK-CDA-IMPORT-RERUN-19` — Re-run test & assertion.
  - [ ] `TASK-CDA-IMPORT-FAIL-20` — Failure injection harness.
  - [ ] `TASK-CDA-IMPORT-METRIC-21` — Idempotent metric registration.
- **DoR.**
  - Failure cases enumerated (collision, missing dependency file, invalid YAML/JSON).
- **DoD.**
  - Harness logs scenario & outcome.

---

## Traceability Log

| Artifact | Description |
| --- | --- |
| [STORY-CDA-IMPORT-002A](/docs/implementation/stories/STORY-CDA-IMPORT-002A-manifest-validation.md) | Manifest validation plan, contracts, and deterministic hashing tasks. |
| [STORY-CDA-IMPORT-002B](/docs/implementation/stories/STORY-CDA-IMPORT-002B-entity-ingestion.md) | Entity ingestion ordering, provenance, and seed event plan. |
| [STORY-CDA-IMPORT-002C](/docs/implementation/stories/STORY-CDA-IMPORT-002C-edge-ingestion.md) | Edge ingestion referential validation and ImportLog coverage. |
| [STORY-CDA-IMPORT-002D](/docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md) | Ontology/taxonomy ingestion plan with duplicate handling. |
| [STORY-CDA-IMPORT-002E](/docs/implementation/stories/STORY-CDA-IMPORT-002E-lore-chunking.md) | Lore chunking, audience enforcement, and provenance hashing plan. |
| [STORY-CDA-IMPORT-002F](/docs/implementation/stories/STORY-CDA-IMPORT-002F-finalization.md) | Import finalization, state digest, and metrics instrumentation plan. |
| [STORY-CDA-IMPORT-002G](/docs/implementation/stories/STORY-CDA-IMPORT-002G-idempotent-rerun.md) | Idempotent rerun & rollback validation plan. |

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | https://github.com/crashtestbrandt/Adventorator/issues/188 | EPIC-CDA-IMPORT-002 master issue. |
| Architecture | ../../architecture/ARCH-CDA-001-campaign-data-architecture.md | Sections 3.1, 3.2, 9 reference importer & seed events. |
| ADR-0011 | ../../adr/ADR-0011-package-import-provenance.md | Provenance + ImportLog model. |
| ADR-0006 | ../../adr/ADR-0006-event-envelope-and-hash-chain.md | Event emission & payload hashing for seed events. |

Update the table as GitHub issues are created to preserve AIDD traceability.
