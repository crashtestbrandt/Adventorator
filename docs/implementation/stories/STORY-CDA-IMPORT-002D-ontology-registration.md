# STORY-CDA-IMPORT-002D — Ontology (tags & affordances) registration

Epic: [EPIC-CDA-IMPORT-002 — Package Import & Provenance](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
Status: Planned
Owner: Campaign Data / Content Pipeline WG — Ontology + retrieval alignment team

## Summary
Load ontology definitions for tags and affordances from package artifacts (`ontology/tags.json`, `ontology/affordances.json` or similar), validate taxonomy consistency, register them in persistence with provenance, and emit `seed.tag_registered` (and affordance variants if applicable) events. Ensure deterministic ordering and idempotent replays, gating duplicates vs conflicting definitions per ADR-0011. Metrics must account for new registrations and idempotent skips.

Fixture scope clarification: The ontology files exercised by importer integration tests reside within package-oriented directories under `tests/fixtures/import/manifest/.../ontologies/` to preserve manifest hash determinism for replay validation. Validator governance fixtures (including intentionally invalid/duplicate/conflict examples) live separately under `tests/fixtures/ontology/` (STORY-IPD-001E) and MUST NOT be moved into the package fixture tree. This separation prevents pathological test data from polluting canonical package manifests.

## Acceptance Criteria
- Ontology schema contracts exist for tags and affordances (`contracts/ontology/tag.v1.json`, `contracts/ontology/affordance.v1.json`); validator rejects missing category/version, invalid slug formats, or mismatched relationships.
- Importer enforces deterministic ordering (e.g., `(category, tag_id, source_path)`) and records ImportLog entries per ontology item with provenance.
- Duplicate tag with identical hash is treated as idempotent skip; conflicting hash triggers hard failure with descriptive message.
- `seed.tag_registered` (and `seed.affordance_registered` if emitted) payloads include tag/affordance metadata plus provenance and pass schema validation tests.
- Metrics `importer.tags.registered`, `importer.tags.skipped_idempotent`, `importer.affordances.registered` increment appropriately; tests assert counters.

## Tasks
- [ ] **TASK-CDA-IMPORT-ONTO-10A — Contract inventory & creation.** Review existing ontology contracts; author or update schemas for tag/affordance definitions including provenance block; document in contracts README.
- [ ] **TASK-CDA-IMPORT-ONTO-10B — Parser & normalization.** Implement loader that merges ontology files, validates taxonomy invariants (parent-child relationships, category uniqueness), and normalizes strings (NFC, lowercase slugs as required).
- [ ] **TASK-CDA-IMPORT-ONTO-10C — Validation fixtures/tests.** Add fixtures for valid taxonomy, duplicate identical definition, and conflicting definition; tests assert correct handling.
- [ ] **TASK-CDA-IMPORT-SEED-11A — Event schema parity.** Verify/create event schema for `seed.tag_registered` (and optional affordance event) under `contracts/events/seed/`; add tests ensuring payload matches contract + runtime models.
- [ ] **TASK-CDA-IMPORT-SEED-11B — Ordering/idempotency tests.** Integration tests verifying deterministic ordering, idempotent skip metrics, and rollback on conflicting definition.
- [ ] **TASK-CDA-IMPORT-METRIC-12A — Metric registration.** Wire metrics for tags/affordances ingestion and add unit tests verifying counter increments + labels (e.g., category).
- [ ] **TASK-CDA-IMPORT-METRIC-12B — Structured logging.** Ensure logs capture counts, duplicates, conflicts with manifest hash for correlation.

## Definition of Ready
- ✅ Ontology data model scope (tag categories, affordance structure) documented for importer planning with links to supporting architecture references.【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002D-ontology-registration-readiness.md†L12-L39】
- ✅ Fixtures representing taxonomy variations prepared and validated manually for baseline, including baseline, idempotent duplicate, and conflicting definitions with transcripted checks.【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002D-ontology-registration-readiness.md†L12-L64】【F:tests/fixtures/import/ontology/README.md†L1-L16】
- ✅ Retrieval metadata requirements (audience, synonyms, gating) recorded so schema work can encode the expected fields before implementation begins.【F:docs/implementation/stories/readiness/STORY-CDA-IMPORT-002D-ontology-registration-readiness.md†L31-L39】

## Definition of Done
- Contracts validated; contract validator integrated with new schemas.
- Parser + importer integration tests demonstrate deterministic ordering, idempotent skip, collision failure, and metrics/logging coverage.
- Documentation updated (developer guide or ontology README) summarizing ingestion behavior and conflict policy.
- Observability story receives metric/log references for dashboards.

## Test Plan
- **Contract tests:** Validate ontology fixtures via contract validator script.
- **Unit tests:** Parser tests for normalization, taxonomy invariants, duplicate/conflict detection.
- **Integration tests:** Importer runs verifying ordering, idempotent skip metrics, collision failure rollback.
- **Regression tests:** Golden hash comparisons for identical duplicates to ensure idempotency detection remains stable.

## Observability
- Structured logs summarizing ontology ingestion results and first conflict details.
- Metrics: `importer.tags.registered`, `importer.tags.skipped_idempotent`, `importer.affordances.registered`, `importer.affordances.skipped_idempotent` (if applicable).

## Risks & Mitigations
- **Taxonomy drift vs retrieval expectations:** Mitigate by aligning contracts with retrieval requirements and documenting synonyms/reserved fields.
- **Duplicate detection false positives:** Use canonical normalization before hashing and include tests for casing/whitespace variations.
- **Affordance gating mistakes:** Validate required relationships (e.g., tag references) via tests.

## Dependencies
- Manifest + entity ingestion for package context.
- ADR-0011 provenance mapping; ARCH-CDA-001 ontology description.
- Potential coordination with retrieval pipeline on how tags feed embedding indexing.

## Feature Flags
- Governed by `features.importer`; consider secondary flag if ontology ingestion needs independent rollout (document if introduced).

## Traceability
- Epic: [EPIC-CDA-IMPORT-002](/docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md)
- Contracts: `contracts/ontology/tag.v1.json`, `contracts/ontology/affordance.v1.json`, `contracts/events/seed/tag-registered.v1.json`.
- Tests: `tests/importer/test_ontology_ingestion.py`.

## Alignment analysis — IMPORT ↔ CDA CORE and IPD
- Canonical JSON and hashing (CDA CORE): Tag and affordance definitions must be normalized with the canonical JSON policy before hashing so duplicates vs conflicts are evaluated deterministically across environments.
- Idempotency v2 composition (CDA CORE): `seed.tag_registered` (and affordance) events should derive idempotency keys from stable definition digests and identifiers, excluding transient fields; repeated imports must not create new envelopes for identical definitions.
- Deterministic ordering (CDA CORE): Establish and test a stable iteration order across categories/tags to guarantee consistent `replay_ordinal` and event sequences.
- IPD alignment (ontology consumers): Ensure field names and semantics match the IPD-side models that consume tags/affordances (e.g., NLU/tagging and predicate gating). Provide a contract parity test or mapping doc if names differ.
- Feature flag policy (AIDD/IPD): Keep importer default-disabled and cover disabled-path tests; document any sub-flag if ontology can roll out independently.

## Implementation Notes
- Cache previously seen tag hashes in-memory per import to avoid repeated disk hashing; maintain deterministic iteration order when writing ImportLog entries.
- For affordances referencing ruleset versions, reuse manifest `ruleset_version` to assert compatibility.
