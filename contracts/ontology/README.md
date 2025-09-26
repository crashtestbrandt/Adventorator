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

## Migration & Evolution Guidance (Draft)

This draft section is introduced by STORY-IPD-001E and will be finalized before story closure.

### Versioning & Deprecation
- Additive changes (new tags / affordances) are allowed without bumping schema version if they do not alter existing semantics.
- Breaking changes (renaming `tag_id`, changing category, removing required fields) are not permitted; instead:
  - Introduce a new tag/affordance with the updated meaning.
  - Mark the old one as deprecated (future field: `deprecated: true`) and retain synonyms pointing to the canonical successor.
- Synonyms list is additive; removals should be justified in a Migration Note.

### Canonical Affordance Mapping
- Tags intended for planner or ImprobabilityDrive actions SHOULD reference a `canonical_affordance` in metadata.
- Multiple affordances invoking the same planner action should nominate one canonical and list others as aliases (planned enhancement).

### Change Proposal Workflow
1. Open a PR updating ontology JSON plus this README's Migration Log.
2. Run validator locally: `make quality-artifacts ARGS="--only-ontology"`.
3. Capture the timing summary line for performance tracking.
4. Add a Migration Note (template below) summarizing rationale and impact.

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
Only ontology validation:
```
make quality-artifacts ARGS="--only-ontology"
```
Full gates:
```
make quality-gates
```
Example timing output:
```
ontology.validate summary: files=3 items=120 avg_ms=4.12 p95_ms=6.30
```

### Planned Enhancements
- Stable SHA-256 digest in conflict messages (replace Python hash())
- Deprecation field with enforcement rules
- Aggregated ontology metrics (counts by category, deprecated ratio)
- Migration Log auto-extraction script
