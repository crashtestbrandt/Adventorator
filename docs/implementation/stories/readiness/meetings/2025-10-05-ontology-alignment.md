# 2025-10-05 — Ontology Alignment Review

**Attendees.** Gameplay Systems (L. Ortega), Rules Council (M. Zhang), Content Pipeline (S. Dube), Retrieval Platform (A. Mensah), AVA/IPD architecture (R. Quinn).

**Agenda.**
1. Ratify tag category hierarchy and affordance record layout for package importer.
2. Confirm provenance metadata requirements per ADR-0011 and ARCH-CDA-001.
3. Validate downstream retrieval metadata expectations (audience gating, synonym exposure, feature flags).

**Decisions.**
- Gameplay & rules stakeholders approved the category ladder (`interaction`, `lore`, `safety`) and the inclusion of `ruleset_versions` + `audience` gating metadata on both tags and affordances to maintain parity with ImprobabilityDrive tagging expectations documented in EPIC-IPD-001 and the AskReport contract.
- Provenance block structure (`package_id`, `source_path`, `file_hash`, `import_strategy`) mirrors ADR-0011 guidance and aligns with ImportLog requirements under EPIC-CDA-IMPORT-002.
- Retrieval platform confirmed that ontology schemas must surface `synonyms[]`, `audience.allow[]`, and optional `embedding_hints{}` so retrieval indexers can map ontology tags to query expansions without violating ARCH-CDA-001 audience isolation rules.

**Action items.**
- Content pipeline team will prepare canonical fixtures covering happy path, duplicate-idempotent, and conflicting-hash scenarios ahead of STORY-CDA-IMPORT-002D implementation.
- Contracts team to embed these decisions in readiness log and reference EPIC-IPD-001 shared interfaces to ensure importer + ImprobabilityDrive remain aligned.
