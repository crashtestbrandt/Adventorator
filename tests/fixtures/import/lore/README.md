# Lore Chunking Fixture Bundles

These fixtures support STORY-CDA-IMPORT-002E contract and integration tests.

## Bundles

- `simple/` — Minimal single-file example with deterministic headings to assert baseline chunk counts and provenance hashing.
- `complex/` — Multi-section narrative with Unicode glyphs, code blocks, and authorial annotations to exercise tokenizer, normalization, and audience gating paths.

## Testing Guidance

1. Validate each file’s YAML front-matter against `contracts/content/chunk-front-matter.v1.json` once authored.
2. Use fixtures to drive chunker unit tests:
   - `simple/` should yield two chunks split on the level-two heading boundary.
   - `complex/` should yield multiple chunks respecting max token thresholds while preserving code fence integrity.
3. Importer integration tests should reference expected hashes recorded in forthcoming golden files under `tests/fixtures/import/lore/*.hashes.json`.
4. Ensure Unicode characters (e.g., `æ`, `Ω`, `こんにちは`) round-trip through normalization utilities before hashing.

## Provenance Notes

Each fixture includes a `provenance.expected_manifest_hash` comment to anchor ImportLog assertions during readiness and implementation testing.
