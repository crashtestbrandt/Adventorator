# Manifest Validation Fixtures

These fixtures provide deterministic sample bundles for STORY-CDA-IMPORT-002A contract and hashing tests.

## Bundles

- `happy-path/`
  - Contains a valid `package.manifest.json` plus representative entity, edge, lore, and ontology artifacts.
  - `content_index` digests are SHA-256 of the provided fixture files, suitable for golden hash computations.
  - Includes an example signature entry so contract authors can test optional signature parsing without requiring cryptographic verification.
- `tampered/`
  - **Design**: The `entities/npc.json` file has been modified (added `"tampered": true` property) but the manifest still contains the original hash from the happy-path version.
  - **Purpose**: This creates a hash mismatch scenario where the file content doesn't match the hash in the manifest's `content_index`.
  - **Expected behavior**: Content validation should detect the mismatch and report "Hash mismatch for entities/npc.json: expected [old_hash], got [actual_hash]".
  - Enables negative contract + hashing tests that must flag mismatched digests and report the offending path.

## Intended Test Usage

1. Schema validation should accept the happy-path manifest and reject structurally invalid manifests derived from the tampered bundle.
2. Hash computation utilities can recompute each `content_index` digest and compare against expected values to exercise canonical serialization and Unicode normalization logic.
3. Importer integration harnesses can mount these directories to simulate deterministic manifest validation before entity/edge ingestion.

All JSON files are formatted with stable ordering to minimize canonicalization drift in downstream tests.
