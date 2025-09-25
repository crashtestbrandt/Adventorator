# Embedding Metadata Feature Flag Decision Log

**Context:** STORY-CDA-IMPORT-002E introduces optional lore embedding metadata (`embedding_hint`) that must only be processed when explicitly enabled.

## Decision

- **Flag name:** `features.importer_embeddings`
- **Default state:** `false`
- **Configuration home:** Extend the existing `[features]` table in `config.toml`, colocated with other importer-related toggles.【F:config.toml†L1-L53】
- **Rollout strategy:**
  - Phase 1 (current story): Flag remains `false`; importer ignores `embedding_hint` during hashing unless enabled, ensuring hash stability.
  - Phase 2 (retrieval integration): Retrieval team may enable flag in staging once embedding storage contracts are ready.

## Rationale

1. Aligns with importer epic requirement that embedding metadata is optional and feature-flagged to avoid destabilizing existing pipelines.【F:docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md†L119-L138】
2. Default `false` prevents accidental embedding ingestion in production environments lacking vector storage.
3. Using a dedicated flag clarifies test matrix expectations: unit tests will assert both disabled (no embedding processing) and enabled (embedding metadata captured) behaviors.

## Test Implications

- Contract tests should validate that `embedding_hint` is optional yet subject to length constraints when flag eventually enables processing.
- Integration tests must verify deterministic hashing when the flag toggles; golden fixtures will include both states before rollout.
