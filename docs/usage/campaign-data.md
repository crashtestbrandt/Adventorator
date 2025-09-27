# Campaign Data: User Guide

This guide shows how to author, validate, and ingest a campaign data pack.

## Quickstart

- Create a new pack
  - make package-scaffold DEST=campaigns/sample-campaign NAME="Greenhollow Demo"
- Author/edit content, then assign IDs and update hashes:
  - make package-ids PACKAGE_ROOT=campaigns/sample-campaign
  - make package-hash PACKAGE_ROOT=campaigns/sample-campaign
- Preflight DB (auto-migrate if needed):
  - make package-preflight AUTO=1
- Import end‑to‑end:
  - make package-import PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1
- Optional watcher (auto-import on change):
  - make package-watch PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1 IMPORT_ON_CHANGE=1

If you need the formal contracts, they live in `contracts/`. The importer implementation is in `src/Adventorator/importer.py` and manifest validation is in `src/Adventorator/manifest_validation.py`.


## Authoring a campaign data pack

A pack is a folder with `package.manifest.json` plus any of these content folders:

```
package-root/
  package.manifest.json
  entities/
    npc.json
    location.json
  edges/
    relations.json   # object or array of edge objects
  ontology/          # or: ontologies/
    tags.json
    affordances.json
  lore/
    intro.md
    chapter-1.md
```

Only include folders you actually use. Every ingested file must be listed in `content_index` in the manifest with its SHA‑256 hash. You don’t have to compute these manually—use the tools below to keep IDs and hashes up to date.

Manifest essentials (v1):
- Schema: `contracts/package/manifest.v1.json`
- Required: `package_id` (ULID), `schema_version`, `engine_contract_range`, `dependencies[]`, `content_index{}`, `ruleset_version`
- Guarantees: schema correctness, hashes match contents, canonical `manifest_hash` for idempotency

Entities (`contracts/entities/entity.v1.json`):
- Required: `stable_id` (ULID), `kind` (`npc|location|item|organization|creature`), `name`, `tags[]`, `affordances[]`
- Behavior: deterministic ordering, collision protection; emits `seed.entity_created`

Edges (`contracts/edges/*`):
- Single object or array; validated against taxonomy; refs must resolve; emits `seed.edge_created`

Ontology (`contracts/ontology/*`):
- Tags and affordances normalized/registered; duplicates idempotent; emits `seed.tag_registered` / `seed.affordance_registered`

Lore:
- Markdown/text chunked into `seed.content_chunk_ingested`; embeddings gated by `features.importer_embeddings`


## Import pipeline & idempotency

At a glance:
- Phases: 1) Manifest → 2) Entities → 3) Edges → 4) Ontology → 5) Lore → 6) Finalization
- Provenance: `ImportLog(sequence_no)` enforces deterministic ordering
- Idempotency: event keys protect duplicates; prior finalized `manifest_hash` short‑circuits reruns


## Validate and ingest locally

Feature gate: the importer is globally gated by `features.importer` (default: false).

Quick demos (no code changes required):

- Validate a manifest (prints the computed manifest hash and a demo seed event attempt):

```bash
python scripts/demo_manifest_validation.py --happy-path
```

- See entity parsing, deterministic ordering, and seed event shapes:

```bash
python scripts/demo_entity_import.py --package-path tests/fixtures/import/manifest/happy-path
```

DB‑backed end‑to‑end: use `make package-import` (or the script) to ingest a real pack. It updates hashes, runs a DB preflight, and invokes the importer for you.

Example (Make):

```
make package-import PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1
```

Script alternative:

```
python scripts/import_package.py --package-root campaigns/sample-campaign --campaign-id 1
```

Flags (script):
- `--no-hash-update` to skip recomputing `content_index`
- `--skip-preflight` to skip the DB table checks
- `--no-importer` to dry-run the pre-steps only
- `--no-embeddings` to disable lore embeddings during import

The importer will:
- Reuse existing seed events/logs idempotently on re‑run
- Short‑circuit if the same `manifest_hash` was previously finalized

Testing:
- Covered by tests in `tests/importer/**` with fixtures under `tests/fixtures/import/**`
- CI smoke: `make test` (docs‑only edits don’t require gates; importer code should pass format/lint/type/test)


## Troubleshooting & edge cases

- Manifest/content drift: If any file changes, recompute its SHA‑256 and update `content_index` using `scripts/update_content_index.py`. Validation will fail if hashes don’t match
- Idempotency collisions: Same idempotency key with different payload → importer aborts to protect the ledger
- Entity collisions: Same `stable_id` with different content across files → error; identical content → idempotent skip
- Planner timeouts: Planner falls back to a dice roll preview when it times out (if `/roll` is available)
- Web CLI sink port busy: Use `--sink-port` or stop the conflicting process

DB schema notes:
- Requires `import_logs`; use `make alembic-up` or `scripts/preflight_import.py --auto-migrate`
- `ImportLog.stable_id` length is 64 to support synthetic summary IDs



---

## Commands cheat sheet

- Make targets (preferred):
  - Scaffold: make package-scaffold DEST=… NAME=…
  - Assign IDs: make package-ids PACKAGE_ROOT=…
  - Update hashes: make package-hash PACKAGE_ROOT=…
  - Preflight DB: make package-preflight [AUTO=1]
  - Import: make package-import PACKAGE_ROOT=… CAMPAIGN_ID=…
  - Watch: make package-watch PACKAGE_ROOT=… [CAMPAIGN_ID=… IMPORT_ON_CHANGE=1]
- Scripts:
  - python scripts/scaffold_package.py --dest … [--name …]
  - python scripts/assign_entity_ids.py --package-root …
  - python scripts/update_content_index.py --package-root …
  - python scripts/preflight_import.py [--auto-migrate]
  - python scripts/import_package.py --package-root … --campaign-id …
  - python scripts/watch_package.py --package-root … [--campaign-id … --import-on-change]

## Further reading

- Importer pipeline: `src/Adventorator/importer.py`
- Manifest validation: `src/Adventorator/manifest_validation.py`
- Contracts/schemas: `contracts/**`
- Tests and fixtures: `tests/importer/**`, `tests/fixtures/import/**`

