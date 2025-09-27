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
