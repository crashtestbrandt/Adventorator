# Ontology Contracts

This folder contains JSON Schema contracts for ontology definitions used in campaign package imports.

## Schema Files

### Tag Definitions
- **`tag.v1.json`** - Schema for ontology tag definitions including:
  - Category classification (action, target, modifier, trait)
  - Slug normalization (lowercase, hyphenated)
  - Synonyms for natural language processing
  - Audience gating (player, gm, system)
  - Ruleset version requirements
  - Metadata including canonical affordance references

### Affordance Definitions  
- **`affordance.v1.json`** - Schema for affordance definitions including:
  - Category classification (combat, environment, social, magic, exploration)
  - Applies-to relationships with tags or entities
  - Gating rules with audience and feature requirements
  - ImprobabilityDrive integration metadata

## Import Pipeline Integration

The ontology registration system processes `ontology/*.json` files during package import:

1. **File Processing**: All JSON files in ontology directories are processed in deterministic order
2. **Validation**: Each tag and affordance is validated against the corresponding schema
3. **Normalization**: Slugs are normalized to lowercase-hyphenated format, synonyms to lowercase
4. **Duplicate Detection**: Identical definitions (by canonical JSON hash) are treated as idempotent skips
5. **Conflict Handling**: Different definitions with same ID trigger hard import failure
6. **Provenance Recording**: Each item is recorded in ImportLog with file hash and source path
7. **Event Emission**: `seed.tag_registered` and `seed.affordance_registered` events are emitted

## Conflict Policy

Following ADR-0011 provenance requirements:

- **Identical duplicates**: Idempotent skip with `importer.*.skipped_idempotent` metric
- **Conflicting definitions**: Hard failure with descriptive error showing hash mismatch
- **Hash computation**: Uses canonical JSON encoding excluding provenance metadata

## Taxonomy Invariants

The importer validates basic taxonomy consistency:

- Category uniqueness within (category, tag_id) combinations
- Affordance references to existing tags generate warnings (not errors) for flexibility
- Unicode NFC normalization per ADR-0007

## Event Schema Parity

Seed events match the ontology schema structure with additional fields:
- `version` from package manifest
- `provenance` block with package_id, source_path, file_hash

See `contracts/events/seed/tag-registered.v1.json` and `affordance-registered.v1.json` for complete event schemas.

## Legacy Files

- **`seed-v0_1.json`** - Legacy seed data used by ask_nlu (deprecated for new imports)
- **`seed.json`** - Backward compatibility file (deprecated)

New ontology definitions should use the v1 schema format for package import integration.

## Migration & Evolution Guidance

Authoritative governance rules for evolving ontology definitions. All changes MUST follow this process.

### Versioning & Deprecation
- Additive changes (new tags / affordances, extra synonyms, metadata descriptions) DO NOT require a schema version bump.
- Breaking changes (renaming `tag_id`, altering category semantics, removing required fields) are DISALLOWED in-place:
  - Create a new tag/affordance with the desired semantics.
  - Mark the predecessor deprecated (once `deprecated` field is introduced) and add its slug to the successor's synonyms.
- Synonyms are append-only; removal requires a documented Migration Note demonstrating harm in keeping it.
- Future `deprecated: true` field (planned) will trigger:
  - Validator warning if referenced by new affordances.
  - Planner ignore unless explicitly configured for legacy support.

### Canonical Affordance Mapping
- Tags used in planner / ImprobabilityDrive flows SHOULD include `metadata.canonical_affordance` referencing an affordance id.
- If multiple affordances drive the same planner intent, pick one canonical; others MAY later declare `aliases` (future enhancement).
- Omit the canonical reference only if the tag is purely descriptive or passive.

### Change Proposal Workflow
1. Open a PR updating ontology JSON and append a Migration Log entry (see below).
2. Run validator locally:
  - `make quality-artifacts ARGS="--only-ontology"`
3. Ensure no duplicate/conflict errors; if re-defining an existing id identically, confirm intent (idempotent).
4. Capture timing summary for PR (performance traceability).
5. Request review from Ontology/Contracts WG (at least one reviewer).
6. Merge only after Migration Log entry is approved.

### Migration Note Template
```
Date: YYYY-MM-DD
Change Type: Add | Deprecate | Metadata | Synonyms | Affordance
Files: [list]
Summary: <short description>
Impact: <planner | importer | NLU>
Backward Compatibility: <why safe>
Follow-up: <cleanup or removal date>
```

### Validator Usage
Quick ontology-only validation:
```
make quality-artifacts ARGS="--only-ontology"
```
Full gates:
```
make quality-gates
```
Example timing output (values illustrative):
```
ontology.validate summary: files=3 items=120 avg_ms=4.12 p95_ms=6.30
```

### Planned Enhancements
- Deprecation field with validator warning semantics
- Aggregated ontology metrics (counts by category, deprecated ratio)
- Migration Log auto-extraction script
- Affordance alias support with canonical reference verification

## Migration Log
| Date | Change Type | Files | Summary | Impact | Backward Compatibility | Follow-up |
|------|-------------|-------|---------|--------|------------------------|-----------|
| 2025-09-26 | Add | `__synthetic_medium_benchmark.json` | Added synthetic benchmark collection for validator perf evidence | Validator perf tracking | Does not affect importer (test artifact) | Replace or remove before production release |
