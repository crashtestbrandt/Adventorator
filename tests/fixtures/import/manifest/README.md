# Manifest Validation Fixtures

These fixtures provide deterministic sample bundles for STORY-CDA-IMPORT-002A contract and hashing tests.

## Bundles

- `happy-path/`
  - Contains a valid `package.manifest.json` plus representative entity, edge, lore, and ontology artifacts.
  - `content_index` digests are SHA-256 of the provided fixture files, suitable for golden hash computations.
  - Includes an example signature entry so contract authors can test optional signature parsing without requiring cryptographic verification.
- `tampered/`
  - Mirrors the happy-path structure but intentionally introduces a digest mismatch for `entities/npc.json` while leaving the manifest hash entry untouched.
  - Enables negative contract + hashing tests that must flag mismatched digests and report the offending path.

## Intended Test Usage

1. Schema validation should accept the happy-path manifest and reject structurally invalid manifests derived from the tampered bundle.
2. Hash computation utilities can recompute each `content_index` digest and compare against expected values to exercise canonical serialization and Unicode normalization logic.
3. Importer integration harnesses can mount these directories to simulate deterministic manifest validation before entity/edge ingestion.

All JSON files are formatted with stable ordering to minimize canonicalization drift in downstream tests.
