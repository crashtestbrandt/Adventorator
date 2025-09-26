# STORY-CDA-IMPORT-002A — Readiness Execution Log

## Implementation Plan (Contracts- & Tests-First)
1. **Manifest field inventory derivation.**
   - Parse the requirements from ADR-0011, ADR-0006, ADR-0007, and ARCH-CDA-001 to establish the canonical manifest field list and formats (ULIDs, semver, SHA-256, signature reservation).
   - Document required vs optional fields, including handling for the deferred signature block so contract authors have unambiguous guidance before schema drafting.
   - Produce a table linking each manifest field to its governing source (ADR/architecture) to enable quick review sign-off.
2. **Fixture bundle authoring for validation tests.**
   - Create `tests/fixtures/import/manifest/` with two bundles: `happy-path/` (valid manifest) and `tampered/` (intentional digest mismatch).
   - Include per-bundle README notes capturing intended test assertions (e.g., contract validation pass vs failure) so red/green tests are straightforward to script.
   - Normalize the JSON fixtures using canonical formatting rules to avoid future churn in tests that assert hashing behavior.
3. **Downstream consumer confirmation notes.**
   - Survey dependent story docs (entity and edge ingestion) and the import epic to capture explicit expectations around `package_id` and `manifest_hash` propagation.
   - Summarize those confirmations in a readiness note referencing the exact documentation lines to serve as traceable evidence that downstream teams align on manifest metadata outputs.
4. **Update story DoR with evidence.**
   - Once the above artifacts exist, update the STORY DoR checklist with bullet-point links to the inventory table, fixture bundles, and downstream confirmation summary so reviewers can quickly verify readiness.

## Execution Status

### 1. Manifest Field Inventory

| Field | Format / Notes | Source Alignment |
| --- | --- | --- |
| `package_id` | Required ULID uniquely identifying the package. | ARCH-CDA-001 manifest field list enumerates `package_id (ULID)` as part of the immutable seed bundle.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】 |
| `schema_version` | Required integer/semver describing the manifest schema revision controlling validation logic. | Architecture spec lists `schema_version` in the manifest key fields, establishing the contract anchor for versioned validation.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】 |
| `engine_contract_range` | Required semantic version range communicating compatible contract/tooling versions. | Architecture manifest list includes `engine_contract_range`, tying the manifest to specific engine capabilities per ADR-0007 canonical policy requirements.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/adr/ADR-0007-canonical-json-numeric-policy.md†L1-L40】 |
| `dependencies[]` | Required array of package references (ULID + semver) to ensure deterministic imports respect upstream manifests. | Architecture manifest list captures `dependencies[]`; ADR-0011 reserves dependency handling for provenance while requiring deterministic provenance across packages.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/adr/ADR-0011-package-import-provenance.md†L19-L32】 |
| `content_index` | Required mapping from relative file paths to canonical SHA-256 digests covering entities, edges, lore, ontology. | Architecture manifest fields identify `content_index (hash per file)`; epic acceptance criteria reiterate digest validation responsibilities.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L41-L52】 |
| `ruleset_version` | Required semantic version that downstream systems (planner, RNG policy) rely on. | Architecture manifest list includes `ruleset_version`; ADR-0006/ADR-0007 require canonical serialization using this version for deterministic hashing of seed events.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/adr/ADR-0006-event-envelope-and-hash-chain.md†L1-L46】 |
| `recommended_flags{}` | Optional object of feature flag defaults (advisory). Must be included verbatim for hashing. | Architecture manifest fields list `recommended_flags{}` for optional operator guidance; importer epic notes manifest validation covers recommended flags advisory data.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L41-L52】 |
| `signatures[]` | Optional array of signature envelopes. Decision: keep optional, document reserved fields per ADR-0011 (signing deferred) while ensuring schema accommodates ED25519 entries matching architecture security posture. | Architecture manifest fields include `signatures[]`; ADR-0011 explicitly defers signing policy but reserves manifest fields, clarifying current stories treat them as optional while keeping schema slots intact.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L58-L74】【F:docs/adr/ADR-0011-package-import-provenance.md†L19-L32】 |

**Outcome.** Manifest field inventory aligns with ADR-0011, architecture, and epic guidance; optional signature handling documented as deferred-but-reserved per ADR-0011.

### 2. Fixture Bundles for Tests

- Added `tests/fixtures/import/manifest/` README documenting bundle purpose and intended contract/hash test coverage.【F:tests/fixtures/import/manifest/README.md†L1-L24】
- `happy-path/` bundle provides canonical manifest + asset files with matching SHA-256 digests to fuel positive validation tests.【F:tests/fixtures/import/manifest/happy-path/package.manifest.json†L1-L32】
- `tampered/` bundle mirrors the structure but leaves a stale digest entry for `entities/npc.json`, enabling negative tests to assert mismatch detection.【F:tests/fixtures/import/manifest/tampered/package.manifest.json†L1-L26】【F:tests/fixtures/import/manifest/tampered/entities/npc.json†L1-L11】

**Outcome.** Fixture bundles enable red/green contract + hashing tests without additional setup.

### 3. Downstream Consumer Confirmation

- Entity ingestion story explicitly requires provenance data to include manifest `package_id` and file-level hash, confirming dependency on manifest metadata outputs.【F:docs/implementation/stories/STORY-CDA-IMPORT-002B-entity-ingestion.md†L7-L25】
- Edge ingestion story depends on manifest-approved package data before processing relationships, ensuring manifest validation outputs gate downstream phases.【F:docs/implementation/stories/STORY-CDA-IMPORT-002C-edge-ingestion.md†L7-L29】
- Epic summary reinforces that manifest validation must surface `{package_id, manifest_hash, schema_version, ruleset_version}` for reuse by later phases, aligning consumer expectations.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L38-L55】

**Outcome.** Downstream teams have documented reliance on manifest metadata, satisfying confirmation requirement.

### 4. Story DoR Updated

- STORY DoR section now links back to this readiness log and fixture bundles, establishing traceable evidence for reviewers.【F:docs/implementation/stories/STORY-CDA-IMPORT-002A-manifest-validation.md†L24-L28】

**Outcome.** Definition of Ready checklist is fully satisfied with in-repo evidence.

