# Key Data Structures and Contracts

This survey highlights the primary data models and cross-boundary contracts you’ll interact with when extending Adventorator.

## Discord Interaction boundary
- File: `src/Adventorator/discord_schemas.py`
- Key models:
  - `Interaction` (incoming request), `InteractionData` (name/options), `Member`, `User`, `Guild`, `Channel`.
- Flow: FastAPI `/interactions` verifies Ed25519, defers, then dispatches by command name/subcommand with parsed `options`.

## Command layer (transport-agnostic)
- File: `src/Adventorator/commanding.py`
- Models:
  - `Option` (Pydantic v2 base for command options). `populate_by_name=True` keeps CLI and Discord in sync.
  - `Invocation` (context: name, subcommand, options, user/channel/guild IDs, `Responder`, `settings`, `llm_client`, `ruleset`).
  - `Responder` Protocol: `send(content: str, *, ephemeral: bool=False)`; implemented in app dispatch using Discord webhooks.
  - `Command` registry populated via `@slash_command`.

## AI Planner contract
- Files: `src/Adventorator/planner.py`, `src/Adventorator/planner_schemas.py`
- Output model: `PlannerOutput { command: str, subcommand?: str, args: dict, confidence?: number, rationale?: string }`.
- Behavior:
  - Builds a catalog from registered commands and each option model’s JSON schema.
  - Prompts LLM to select exactly one command; args validated strictly against the target option model.

## Orchestrator output
- File: `src/Adventorator/orchestrator.py`
- Output model (internal): `OrchestratorResult { mechanics: str, narration: str, rejected?: bool, reason?: str, chain_json?: dict }`.
- Proposal schema from LLM: `LLMOutput` (see below). Orchestrator enforces defenses (action allowlist, ability whitelist, DC bounds; banned verbs; unknown-actor detection).

## LLM JSON utilities and schema
- Files: `src/Adventorator/llm_utils.py`, `src/Adventorator/schemas.py`
- `extract_first_json(text)` returns the first balanced JSON object from mixed output.
- `LLMOutput` schema: `{ proposal: { action: "ability_check", ability: "DEX", suggested_dc: number, reason?: string }, narration: string }`.

## Rules engine
- Files: `src/Adventorator/rules/*.py`
- Key types:
  - `DiceRoll { expr, rolls[], total, modifier, sides, count, crit }`
  - `CheckInput { ability, score, proficient, expertise, proficiency_bonus, dc, advantage, disadvantage }`
  - `CheckResult { total, d20[], pick, mod, success }`
- `Dnd5eRuleset` API: `roll_dice(...)`, `perform_check(...)`, `roll_initiative(...)`, `make_attack_roll(...)`, `roll_damage(...)`, `apply_damage(...)`, `apply_healing(...)`.

## Executor and ToolCallChain (preview/apply)
- Files: `src/Adventorator/executor.py`, `src/Adventorator/tool_registry.py`
- Core contracts:
  - `ToolCallChain v1 { request_id, scene_id, actor_id?, steps[] }` where `steps[i] = { tool, args, requires_confirmation?, visibility? }`.
  - `Executor.execute_chain(chain, dry_run: bool) -> Preview|Result`.
- Usage:
  - Orchestrator (under FF) wraps a narrator proposal into a `check` tool step and calls `execute_chain(..., dry_run=True)`; UI returns preview text.

## Persistence (models)
- File: `src/Adventorator/models.py`
- Core tables:
  - `Campaign`, `Player`, `Character { sheet: jsonb }`, `Scene { channel_id unique }`, `Transcript { author, content, meta }`.
  - Phase 6: `ContentNode { node_type, title, player_text, gm_text? }`.
  - Phase 8: `PendingAction { request_id, chain json, mechanics, narration, status, expires_at, dedup_hash }`.
  - Phase 9: `Event { scene_id, actor_id?, type, payload json, request_id?, created_at }`.

## Retrieval layer
- File: `src/Adventorator/retrieval.py`
- `ContentSnippet { id, title, text }` and retriever interface; SQL fallback searches player-visible text only for prompts.

## Repos and session management
- Files: `src/Adventorator/repos.py`, `src/Adventorator/db.py`
- Pattern: `async with session_scope() as s: ...` to perform DB reads/writes. Repos implement helpers for campaigns/scenes/transcripts/characters/events/pending.

## Config and feature flags
- File: `src/Adventorator/config.py`, `config.toml`
- Examples: `features_llm`, `features_llm_visible`, `features_planner`, `features_executor`, `features_executor_confirm`, `metrics_endpoint_enabled`, `retrieval.enabled/top_k`.

## Logging and metrics
- Files: `src/Adventorator/logging.py`, `src/Adventorator/metrics.py`
- JSON logs via structlog with `request_id`; metrics counters for planner/orchestrator/executor/retrieval.

## Discord follow-up responder
- File: `src/Adventorator/responder.py`
- Sends follow-up messages via Discord webhooks; supports a per-request webhook base override in dev for local sinks.
