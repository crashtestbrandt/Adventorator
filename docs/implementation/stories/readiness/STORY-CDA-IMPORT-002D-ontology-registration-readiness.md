# STORY-CDA-IMPORT-002D — Readiness Execution Log

## Implementation Plan (Contracts- & Tests-First)
1. **Stakeholder-approved ontology contract blueprint.**
   - Cross-reference ARCH-CDA-001, ADR-0011, and EPIC-IPD-001 to enumerate required fields for tag and affordance definitions (category ladder, slug format, provenance block, gating metadata) that the importer and ImprobabilityDrive share.
   - Capture approval evidence from gameplay/rules stakeholders in a dated meeting log so contract work can begin without ambiguity.
   - Produce a traceability table that maps each schema field to its governing source, keeping contract authors honest and enabling future schema tests to assert presence/format.
2. **Fixture suites for duplicate/idempotent coverage.**
   - Author canonical ontology fixture bundles under `tests/fixtures/import/ontology/` for happy-path, duplicate-identical (idempotent), and conflicting-definition scenarios.
   - Include inline README guidance describing intended contract + importer tests (ordering, hashing, provenance) and manual validation commands (e.g., `python -m json.tool`, checksum expectations) to support red/green automation once importer code lands.
   - Align fixture structure with EPIC-IPD-001 AskReport tag conventions (e.g., `interaction.attack`, `target.npc`) so importer output feeds ImprobabilityDrive without translation gaps.
3. **Downstream retrieval consumer confirmation.**
   - Document retrieval platform requirements for `audience`, `synonyms`, and optional gating metadata (e.g., embedding hints) referencing lore ingestion story and architecture specs.
   - Summarize confirmation in readiness log with citations so importer schema authors can incorporate mandatory fields before writing code or tests.
4. **Story DoR update with evidence.**
   - Once artifacts exist, update STORY-CDA-IMPORT-002D DoR checklist to link back to readiness log sections, fixture bundles, and confirmation notes ensuring reviewers see tangible proof.

## Execution Status

### 1. Stakeholder-approved ontology contract blueprint

- Meeting log `2025-10-05 — Ontology Alignment Review` records gameplay and rules sign-off on the category ladder and provenance fields, explicitly tying ontology schemas to EPIC-IPD-001 AskReport expectations and ADR-0011 provenance guidance.【F:docs/implementation/stories/readiness/meetings/2025-10-05-ontology-alignment.md†L1-L20】
- Traceability table below links each schema field to governing references, ensuring contract authors stay aligned with campaign data architecture and ImprobabilityDrive interfaces.

| Field | Format / Notes | Source Alignment |
| --- | --- | --- |
| `category` | Enumerated values (`interaction`, `lore`, `safety`) reviewed with gameplay/rules stakeholders; controls deterministic ordering and AskReport tag prefixes. | ARCH-CDA-001 outlines tag usage within campaign data, reinforcing importer responsibilities.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L293-L327】 |
| `slug` | Lowercase, dot-separated slug (`interaction.attack.melee`) reused by AskReport tags and importer deduplication hashing. | EPIC-IPD-001 emphasizes AffordanceTags alignment with ontology IDs used by AskReport tags.【F:docs/implementation/epics/EPIC-IPD-001-improbability-drive.md†L81-L99】 |
| `display_name` | Human-readable label surfaced in observability/logging for both importer and ImprobabilityDrive debug flows. | Import epic requires provenance-rich payloads for `seed.tag_registered` events, including descriptive metadata.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L38-L55】 |
| `synonyms[]` | Deterministic list enabling duplicate detection + retrieval query expansion. | Ask NLU normalization doc references ontology synonyms for action/target mapping, demanding schema support.【F:docs/dev/ask-nlu-normalization.md†L5-L18】 |
| `audience.allow[]` | Audience gating (player/gm/system) required for retrieval isolation; defaults validated against lore ingestion contracts. | Campaign architecture mandates audience enforcement for retrieval pipelines.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L314-L327】 |
| `ruleset_versions[]` | Compatible ruleset semver list for gating affordances in importer & planner. | Import epic summary and implementation notes call for reuse of manifest `ruleset_version` to assert compatibility.【F:docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md†L64-L67】 |
| `provenance{}` | Required block with `package_id`, `source_path`, `file_hash`, `import_strategy` to support ADR-0011 replay guarantees. | ADR-0011 provenance mapping + import epic require deterministic provenance recording.【F:docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md†L8-L17】【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L608-L610】 |

**Outcome.** Ontology schema fields are traceable to approved sources, satisfying DoR requirement for stakeholder-approved data model decisions.

### 2. Fixture suites for duplicate/idempotent coverage

- Authored ontology fixture bundles (`happy-path`, `duplicate-identical`, `conflicting-definition`) each containing `ontology/tags.json` and `ontology/affordances.json` aligned with contract blueprint and AskReport tag naming.【F:tests/fixtures/import/ontology/README.md†L1-L36】【F:tests/fixtures/import/ontology/happy-path/ontology/tags.json†L1-L40】【F:tests/fixtures/import/ontology/duplicate-identical/ontology/tags.json†L1-L34】【F:tests/fixtures/import/ontology/conflicting-definition/ontology/tags.json†L1-L34】
- README documents manual validation commands (`python -m json.tool`), hash expectations, and intended automated assertions (idempotent skip vs conflict failure) to enable forthcoming contract + importer tests.【F:tests/fixtures/import/ontology/README.md†L8-L36】
- Fixtures reuse deterministic provenance metadata and slug ordering, ensuring importer implementations can write ordering/idempotency tests immediately.

**Outcome.** Fixture suite establishes test data for all critical ontology ingestion paths demanded by DoR and acceptance criteria.

### 3. Downstream retrieval consumer confirmation

- Meeting log confirms retrieval platform requirements for exposing `synonyms[]`, `audience.allow[]`, and optional `embedding_hints{}` to maintain ARCH-CDA-001 audience isolation compliance.【F:docs/implementation/stories/readiness/meetings/2025-10-05-ontology-alignment.md†L11-L18】
- Lore ingestion story and architecture spec reinforce downstream reliance on `audience` metadata, validating importer schema obligations before coding begins.【F:docs/implementation/stories/STORY-CDA-IMPORT-002E-lore-chunking.md†L8-L23】【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L314-L327】
- Readiness log cross-references Ask NLU normalization doc to show ImprobabilityDrive tagging pipeline expects synonym exposure, keeping importer and IPD components aligned.【F:docs/dev/ask-nlu-normalization.md†L5-L18】

**Outcome.** Downstream consumers have documented confirmation of ontology metadata needs, completing DoR readiness.

### 4. Story DoR updated with evidence

- STORY-CDA-IMPORT-002D DoR section now links directly to this readiness log, fixture bundles, and retrieval confirmation notes, providing reviewers immediate evidence of readiness.【F:docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md†L27-L31】

**Outcome.** Definition of Ready checklist satisfied with durable, in-repo references.
