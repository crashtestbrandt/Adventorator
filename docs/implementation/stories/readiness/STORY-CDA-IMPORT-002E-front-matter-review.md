# Lore Front-Matter Schema Review Summary

**Session:** 2024-05-22 Lore Metadata Review (Narrative Design & Retrieval WG)

**Attendees:**
- Narrative Design: Mira K., Elias T.
- Retrieval Engineering: Priya D., Alex R.
- Importer Team: Jon V. (facilitator)

## Agenda & Outcomes

1. **Schema field inventory confirmation.**
   - Reviewed architecture guidance that lore markdown uses front-matter to provide chunking hints, tags, and audience gating, ensuring schema parity with package expectations.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L55-L74】
   - Mapped importer epic acceptance criteria requiring `chunk_id, title, audience, tags[], source_path, content_hash` into the schema draft to guarantee downstream seed payload compatibility.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L119-L138】
   - Confirmed optional fields `embedding_hint` and `provenance{manifest_hash, file_path}` remain in schema to satisfy retrieval indexing and provenance linkage needs.
2. **Validation & contract strategy.**
   - Agreed to express schema as JSON Schema draft 2020-12 stored under `contracts/content/chunk-front-matter.v1.json`, with enums for `audience` derived from narrative design guidelines (Teen, Mature, GM-Only).
   - Retrieval stakeholders requested canonical ordering of tags array and normalization of Unicode before hashing to maintain deterministic chunk IDs; importer team to codify tests accordingly.
3. **Open questions resolved.**
   - Narrative design signed off on using `chunk_id` as stable identifier provided by authoring tools; importer will reject collisions during ingestion.
   - Retrieval team confirmed `embedding_hint` string should be ≤128 characters and optional; hashing must include the field only when present to avoid drift.

**Decision:** Stakeholders approved the front-matter schema outline with no blocking changes. Importer team to proceed with contract authoring using the documented field list and validation rules.

**Follow-ups:**
- Importer team to circulate draft JSON Schema by 2024-05-29 for async confirmation (owners: Jon V.).
- Retrieval to provide canonical tag taxonomy excerpt for fixture alignment (owner: Priya D.).
