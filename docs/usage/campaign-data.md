# Campaign Data: User Guide

This guide is the practical companion for CDA‑CORE‑001 (deterministic event substrate) and CDA‑IMPORT‑002 (campaign data import). It shows how to author a campaign data pack, validate and ingest it, and what behavior to expect in /ask, /plan, and /do across the Web CLI vs Discord clients.

If you need the formal contracts, they live in `contracts/`. The importer implementation is in `src/Adventorator/importer.py` and manifest validation is in `src/Adventorator/manifest_validation.py`.


## What you get from the two epics

- Deterministic event ledger (CDA‑CORE‑001):
  - Canonical JSON hashing, idempotency keys, and a replay hash chain for events
  - Used by importer seed events and finalization
- Package import (CDA‑IMPORT‑002):
  - Phases: Manifest → Entities → Edges → Ontology → Lore → Finalization
  - Deterministic ordering, collision detection, and ImportLog provenance
  - Strict idempotency: safe re‑runs and a manifest‑hash short‑circuit


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

Only include folders you actually use, but ensure every ingested file is listed in `content_index` in the manifest with its SHA‑256 hash.

### Manifest blueprint (v1)

Schema: `contracts/package/manifest.v1.json`

Required fields:
- `package_id` — ULID string (26 chars, Crockford base32); uniquely identifies the pack
- `schema_version` — integer (≥ 1)
- `engine_contract_range` — `{ "min": "x.y.z", "max": "x.y.z" }` compatible engine contract versions
- `dependencies` — array of `{ package_id, version }` (empty if none)
- `content_index` — map of `"relative/path" -> "sha256hex"` for all ingested files
- `ruleset_version` — semver string

Optional:
- `recommended_flags` — map of feature flag suggestions
- `signatures` — reserved for future signing

Validation guarantees:
- Schema correctness (types, semver, ULIDs)
- `content_index` hashes match the actual file contents (and paths are safe/relative)
- A canonical `manifest_hash` is computed for idempotency and provenance

Tip: Use the happy‑path fixture at `tests/fixtures/import/manifest/happy-path/` as a concrete example.

### Entities

Schemas:
- Entity: `contracts/entities/entity.v1.json`
- Emitted event: `contracts/events/seed/entity-created.v1.json`

Required fields per entity JSON:
- `stable_id` — ULID‑like unique id (per entity)
- `kind` — one of `npc | location | item | organization | creature`
- `name` — display name
- `tags[]` — semantic tags
- `affordances[]` — available actions/verbs

Optional: `traits[]`, `props{}`. The importer adds `provenance` (package_id, source_path, file_hash).

Importer behavior:
- Deterministic ordering (e.g., by kind, stable_id, source_path)
- Collision policy: same stable_id with different hash → error; same hash → idempotent skip
- Emits `seed.entity_created` per entity

### Edges

Schemas:
- Edge/event schemas under `contracts/edges/` (see taxonomy)
- Emitted event: `seed.edge_created`

Notes:
- Files may contain a single edge object or an array
- Validated against the edge schema and the taxonomy; entity refs must resolve
- Same idempotency and collision semantics as entities

### Ontology (tags & affordances)

Schemas:
- `contracts/ontology/tag.v1.json`
- `contracts/ontology/affordance.v1.json`

Behavior:
- Tags/affordances normalized (slug/lowercase) and registered; duplicates idempotent
- Emits respective `seed.tag_registered`/`seed.affordance_registered` seed events

### Lore

- Files in `lore/` are chunked by the importer
- Emits `seed.content_chunk_ingested` per chunk
- Embedding metadata path is gated by `features.importer_embeddings`


## Import pipeline & idempotency

Phases (deterministic):
1) Manifest: validate schema and content hashes; emit `seed.manifest.validated`
2) Entities: validate & emit `seed.entity_created`
3) Edges: validate & emit `seed.edge_created`
4) Ontology: register & emit `seed.tag_registered` / `seed.affordance_registered`
5) Lore: chunk & emit `seed.content_chunk_ingested`
6) Finalization: compute counts + digest; emit `seed.import.complete`

Provenance & logs:
- Each object (entity/edge/tag/affordance/chunk) gets an `ImportLog` record with `sequence_no`
- Sequence contiguity is enforced; reruns with the same manifest_hash reuse rows idempotently

Idempotency:
- Per‑event idempotency keys ensure duplicate emissions with identical payloads reuse the existing Event; mismatched payloads with the same key are rejected (safety)
- DB‑backed importer short‑circuits the entire run if it finds a prior `seed.import.complete` with the same `manifest_hash`


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

DB‑backed end‑to‑end: write a small driver that calls
`run_full_import_with_database(package_root, campaign_id, features_importer=True, features_importer_embeddings=False)`
from `src/Adventorator/importer.py` to ingest a real pack into your dev DB. The importer will:
- Reuse existing seed events/logs idempotently on re‑run
- Short‑circuit if the same `manifest_hash` was previously finalized

Testing:
- The importer is covered by tests under `tests/importer/**` and fixtures in `tests/fixtures/import/**`
- CI smoke: `make test` (see `Makefile`). Docs‑only changes don’t require full gates, but importing code changes should pass format/lint/type/test.


## How imported data affects /ask, /plan, /do

- /ask
  - Flags: `features.improbability_drive` and `features.ask.enabled` must both be true
  - Rule‑based NLU (default) infers an action verb and tags; with `features.ask.kb_lookup`, a KB adapter can resolve entity names/terms using your ontology
  - Emits observability and an ephemeral summary; does not mutate world state

- /plan
  - Flags: requires `features.llm=true`; planner also requires `feature_planner_enabled=true`
  - Persists a player transcript and scene; may fetch allowed actor names if `features.action_validation` and `features.predicate_gate` are enabled
  - With AVA + predicate gate, generates a typed Plan and checks feasibility against campaign state (entities, edges, ontology). Failed predicates result in a feasible=false plan snapshot and a friendly rejection
  - On accept, it re‑dispatches to the planned slash command with validated args

- /do
  - Requires LLM; writes transcript and runs the orchestrator
  - Uses executor flags: `features.executor` and `features.executor_confirm` for pending/approval flows
  - A richer imported world yields more grounded execution (valid targets and affordances). Retrieval (below) can further augment the LLM

- Retrieval
  - Controlled by `[features.retrieval]` (e.g., `enabled=true`, `provider="none|pgvector|qdrant"`, `top_k`)
  - Imported lore chunks provide the material that retrieval feeds into planning/execution


## Web CLI vs Discord behavior

Both clients send the same slash interactions; differences are in delivery and debug ergonomics.

- Web CLI (`scripts/web_cli.py`)
  - Starts a local webhook sink by default and prints the follow‑up content (ephemeral noted)
  - `--no-sink` + app dev‑webhook override: polls `/dev-webhook/latest/{token}` for content
  - `--raw` / `--json-only`: attempts to emit the latest plan snapshot JSON (it watches structured logs for `planner.plan_snapshot`/`plan_created/plan_built`)

- Discord
  - True ephemeral/public behavior; platform rate limiting applies
  - Without a dev‑webhook override, fake tokens won’t work; you’ll only see standard interaction acks

Common flag scenarios (expectations):
- `features.llm=false`
  - /plan and /do: disabled (friendly error). /ask: unaffected if improbability_drive + ask.enabled
- `features.action_validation=false` or `features.predicate_gate=false`
  - /plan: still plans, but without typed Plan validation or predicate feasibility checks
- `features.improbability_drive=false` or `features.ask.enabled=false`
  - /ask: disabled
- `[features.retrieval].enabled=false`
  - /plan and /do: LLM runs without RAG
- `features.importer=false`
  - Importer disabled; runtime commands still work, but world will be sparse unless seeded otherwise

CLI‑only perks:
- Easier capture of plan JSON with `--raw`/`--json-only`
- Sink start/stop and dev‑webhook polling for quick iteration


## Troubleshooting & edge cases

- Manifest/content drift: If any file changes, recompute its SHA‑256 and update `content_index`. Validation will fail if hashes don’t match
- Idempotency collisions: Same idempotency key with different payload → importer aborts to protect the ledger
- Entity collisions: Same `stable_id` with different content across files → error; identical content → idempotent skip
- Planner timeouts: Planner falls back to a dice roll preview when it times out (if `/roll` is available)
- Web CLI sink port busy: Use `--sink-port` or stop the conflicting process


## Quick references (paths)

- Importer pipeline: `src/Adventorator/importer.py`
- Manifest validation: `src/Adventorator/manifest_validation.py`
- Contracts/schemas: `contracts/**`
- Demos:
  - Manifest: `scripts/demo_manifest_validation.py`
  - Entities: `scripts/demo_entity_import.py`
- Web CLI: `scripts/web_cli.py`
- Commands: `src/Adventorator/commands/{ask,plan,do}.py`
- Feature flags: `config.toml` (see `[features]` and `[features.retrieval]`)
- Tests: `tests/importer/**`, fixtures in `tests/fixtures/import/**`


---

If you need a scaffolded “hello‑world” pack or a tiny DB‑backed importer driver, open an issue or ping the team; we can add a script that computes `content_index` and calls `run_full_import_with_database` end‑to‑end.


## Manual walkthrough: building and importing the sample campaign (2025‑09‑27)

This is a faithful log of the exact manual steps we performed to create `campaigns/sample-campaign` and import it end‑to‑end into the dev database using the DB‑backed importer. It’s meant to be the raw material we’ll automate next.

### 1) Scaffold the pack on disk

Created folder and files under `campaigns/sample-campaign/`:

- Root
  - `package.manifest.json`
  - `README.md` (pack overview)
- Entities (`entities/`)
  - `npc.alric_stone.json` (stable_id `01J8A0A0000000000000000000`)
  - `npc.seraphina_dawn.json` (`01J8A0A0000000000000000001`)
  - `location.greenhollow.json` (`01J8A0A0000000000000000002`)
  - `location.ruined_watchtower.json` (`01J8A0A0000000000000000003`)
  - `item.skyshard.json` (`01J8A0A0000000000000000004`)
  - `organization.wayfarers_guild.json` (`01J8A0A0000000000000000005`)
  - `creature.forest_troll.json` (`01J8A0A0000000000000000006`)
- Edges (`edges/`)
  - `relations.json` (e.g., `npc.resides_in.location`, `organization.controls.location`)
  - `adjacency.json` (e.g., `adjacent_to` with attributes `{ distance: 2, connection_type: "trail" }`)
- Ontology (`ontology/`)
  - `tags.json`
  - `affordances.json`
- Lore (`lore/`)
  - `intro.md`, `chapter-1.md`, `legends-skyshard.md`

Notes:
- We enforced canonical/deterministic policies while authoring:
  - ULIDs: 26‑char Crockford base32 for entity `stable_id` fields
  - No floats in event payloads: `edges/adjacency.json` distance normalized from `2.1` → `2`

### 2) Populate `content_index` with SHA‑256 hashes

- For each ingested file, computed SHA‑256 and inserted into the manifest’s `content_index` map.
- Updated `engine_contract_range` to `min=max=1.2.0`, and `ruleset_version` to `5.2.1`.
- Added `recommended_flags` with `features.importer=true` (others as appropriate).

Example to compute a file hash on macOS:

```bash
shasum -a 256 campaigns/sample-campaign/entities/npc.alric_stone.json | awk '{print $1}'
```

Tip: any file edit requires recomputing its hash and updating the manifest.

### 3) Add a tiny DB‑backed importer CLI

- Created `scripts/run_package_import.py`: a minimal driver calling
  `run_full_import_with_database(package_root, campaign_id, features_importer=True, features_importer_embeddings=True)`
  and printing a summary.

### 4) First import attempt → manifest hash mismatches

Command:

```bash
PYTHONPATH=./src python scripts/run_package_import.py --package-root campaigns/sample-campaign --campaign-id 1
```

Outcome: Manifest validation failed with "Content hash validation failed" due to edits after initial hashing (several `entities/*` and `edges/*`).

Fix: Recomputed SHA‑256 for the changed files and updated `package.manifest.json` `content_index` accordingly.

### 5) Database migrations

Command:

```bash
make alembic-up
```

Outcome: General migrations applied, but the importer later failed because `import_logs` table didn’t exist.

Fix: Added an Alembic migration to create `import_logs` and applied it.

Artifacts added:

- `migrations/versions/cda001a0002_add_import_logs.py`
  - Creates `import_logs` with columns: `id`, `campaign_id` (FK→`campaigns.id`), `sequence_no`, `phase`, `object_type`, `stable_id`, `file_hash`, `action`, `manifest_hash`, `timestamp`
  - Unique constraint on `(campaign_id, sequence_no)` and helpful indexes

Applied again:

```bash
make alembic-up
```

### 6) Second import attempt → `stable_id` too short for summary

Outcome: Insert into `import_logs` failed with `value too long for type character varying(26)` because the final summary entry uses a synthetic stable_id like `summary-01J8A0P...` which exceeds 26 chars.

Fixes:

- Widened `ImportLog.stable_id` from 26 → 64 chars in `src/Adventorator/models.py`.
- Added migration `migrations/versions/cda001a0003_widen_import_logs_stable_id.py` to alter the column.

Applied again:

```bash
make alembic-up
```

### 7) Successful import run

Command:

```bash
PYTHONPATH=./src python scripts/run_package_import.py --package-root campaigns/sample-campaign --campaign-id 1
```

Result (summarized):

- Events created: 2
  - `seed.manifest.validated`
  - `seed.import.complete`
- Import logs: 13 (entities + finalization summary)
- Hash chain tip: stable and printed by the CLI

### 8) Idempotency verification (second run)

Command:

```bash
PYTHONPATH=./src python scripts/run_package_import.py --package-root campaigns/sample-campaign --campaign-id 1
```

Result (summarized):

- `idempotent_skip: true`
- No new events (event_count remains 2)
- A single summary import log entry is recorded for the rerun

### 9) Pitfalls and how we fixed them

- Content hash drift → recompute and update `content_index` whenever files change
- Missing `import_logs` table → add migration `cda001a0002_add_import_logs.py`
- `stable_id` length limit for summary → widen to 64 chars via `cda001a0003_widen_import_logs_stable_id.py`
- Determinism:
  - Use ULIDs for entity `stable_id`
  - Avoid floats in payloads (normalized edge attributes)

### 10) What to automate next

- A small tool or Make target to:
  - Compute SHA‑256 for all content files and refresh `content_index`
  - Validate manifest locally
  - Run the DB‑backed import end‑to‑end
- Pre‑flight DB check that verifies required tables/migrations (including `import_logs`) are present
- Optional: a schema guard that asserts `ImportLog.stable_id` is ≥ 64 chars to prevent regressions

