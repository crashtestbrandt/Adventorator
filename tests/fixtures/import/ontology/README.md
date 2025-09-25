# Ontology Import Fixtures

These fixtures back STORY-CDA-IMPORT-002D readiness by providing canonical ontology payloads for importer contract and integration tests.

## Structure
- `happy-path/`: Golden ontology definitions that should register successfully.
- `duplicate-identical/`: Mirrors the happy path definitions byte-for-byte so hashing and idempotent skip expectations can be asserted deterministically.
- `conflicting-definition/`: Introduces a conflicting tag hash (different `display_name` + synonyms) to trigger hard-fail behavior.

Each bundle exposes:
- `ontology/tags.json`
- `ontology/affordances.json`

The importer implementation should treat directory names as fixture identifiers when wiring tests.

## Manual validation
1. Ensure JSON syntax validity:
   ```bash
   python -m json.tool tests/fixtures/import/ontology/happy-path/ontology/tags.json >/dev/null
   python -m json.tool tests/fixtures/import/ontology/duplicate-identical/ontology/tags.json >/dev/null
   python -m json.tool tests/fixtures/import/ontology/conflicting-definition/ontology/tags.json >/dev/null
   ```
2. Confirm deterministic ordering by comparing sorted keys:
   ```bash
   jq '.["tags"] | map(.slug)' tests/fixtures/import/ontology/happy-path/ontology/tags.json
   ```
3. Compute SHA-256 digests to seed importer idempotency tests:
   ```bash
   sha256sum tests/fixtures/import/ontology/happy-path/ontology/tags.json
   sha256sum tests/fixtures/import/ontology/duplicate-identical/ontology/tags.json
   ```
   Identical digests indicate fixtures should be treated as idempotent.

## Test planning notes
- Happy path fixtures will feed contract validation + metrics assertions (`importer.tags.registered`).
- Duplicate fixtures should register zero new tags but increment `importer.tags.skipped_idempotent`.
- Conflicting fixtures should abort the transaction and surface a descriptive error containing the conflicting slug and provenance hash.
- Affordance fixtures intentionally reference the same slugs as tags to ensure importer + ImprobabilityDrive share identifiers.
