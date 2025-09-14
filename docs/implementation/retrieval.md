# Retrieval (Phase 6) — Design & Integration

Goal: Provide safe, player-visible augmentation for the Orchestrator using content nodes stored in the primary DB. GM-only text must never be surfaced.

## Data Model

- `NodeType` enum: `location`, `npc`, `encounter`, `lore`.
- `ContentNode` table: `id`, `campaign_id`, `node_type`, `title`, `player_text`, `gm_text`, `tags`.
- Indexes on `campaign_id`, `node_type`, `title` for simple LIKE scans.

## Settings

Defined in `config.py` under `Settings.RetrievalConfig`:

- `enabled: bool` — default `false`.
- `provider: "none" | "pgvector" | "qdrant"` — default `"none"` (SQL fallback).
- `top_k: int` — default `4`.

Example `config.toml` (feature flags):

```toml
[features]
retrieval = { enabled = true, provider = "none", top_k = 4 }
```

## Retriever

`SqlFallbackRetriever` performs a conservative search:

- Tokenizes the user query and requires all terms to appear in at least one of: `title`, `player_text`, or `gm_text` (for matching only).
- Always returns snippets with `player_text` only.
- Metrics: `retrieval.calls`, `retrieval.snippets`, `retrieval.errors`, `retrieval.latency_ms`.

Switching providers later is handled behind `build_retriever(settings)`.

## Orchestrator Integration

`run_orchestrator(..., settings=...)` consults `settings.retrieval` and, when enabled:

1. Resolves the scene’s `campaign_id`.
2. Retrieves `top_k` snippets matching the player’s message.
3. Appends facts as `[ref] <title>: <player_text>`.
4. Proceeds with validation + mechanics as usual.

Safety notes:

- Banned verbs and unknown-actor defenses limit narrative misuse.
- DC must be between 5 and 30; ability is whitelisted.
- GM text is never sent to the LLM by construction.

## Commands / Settings Threading

- `/do` calls `run_orchestrator(..., settings=inv.settings)` so retrieval flags are honored.
- `/plan` routes to `/do` (or others) and preserves `inv.settings` when redispatching.
- `app.py` constructs `Invocation` with `settings=load_settings()` and injects it into responders and handlers.

## Tests

- `tests/test_retrieval_sql_fallback.py` — verifies only player text is returned, respects campaign scoping, and truncates queries.
- `tests/test_orchestrator_retrieval_integration.py` — asserts snippets included in facts when enabled.
- `tests/test_retrieval_metrics.py` — validates metrics paths for success and error cases.

## Operational Tips

- For local demos, import a few lore nodes via `scripts/import_content.py`.
- Keep retrieval disabled in production until content is curated.
- Use `GET /metrics` (when enabled) to observe retrieval and orchestrator counters.
