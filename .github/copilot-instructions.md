# Copilot Instructions for Adventorator

Purpose: Make AI agents productive fast. Keep edits small, match existing patterns, and verify with tests before committing.

## Architecture essentials
- FastAPI interactions endpoint `src/Adventorator/app.py` handles `POST /interactions` from Discord.
  - Always verify `X-Signature-*` via `crypto.verify_ed25519`.
  - Respond within 3s using `responder.respond_deferred()`; actual work runs in a background task.
  - Command routing: `app._dispatch_command()` uses the registry in `commanding.py` to find handlers under `Adventorator.commands/*`.
- Responder pattern: handlers call `await responder.send(content, ephemeral=...)`; in prod this uses `responder.followup_message()` (Discord webhook).
- Rules engine (deterministic): `rules/dice.py` and `rules/checks.py`.
  - `DiceRNG.roll("XdY+Z", advantage=False, disadvantage=False)`; adv/dis only for a single d20. Returns `DiceRoll(rolls, total, crit)`.
  - `compute_check(CheckInput, d20_rolls=[...]) -> CheckResult`.
- Persistence: Async SQLAlchemy in `db.py`; ORM in `models.py`; data helpers in `repos.py`.
  - Always use `async with session_scope()` in handlers/commands; helpers return plain rows/data.
- LLM narrator (Phase 3): JSON-only proposals via `llm.py` + strict parsing in `llm_utils.py`/`schemas.py`.
  - Orchestrator `orchestrator.run_orchestrator(scene_id, player_msg, *, sheet_info_provider=None, rng_seed=None, llm_client, prompt_token_cap=None, allowed_actors=None)` coordinates facts → LLM proposal → rules → formatted output.
  - Safety: action gate, ability whitelist, DC bounds, non-empty reason, verb blacklist (no HP/inventory changes), unknown-actor detection (via `allowed_actors`).
  - Visibility: gated by `features.llm_visible`; in shadow mode we acknowledge but don’t post public narration.
  - Caching: 30s in-process cache by `(scene_id, player_msg)` to suppress duplicate prompts.
  - Metrics: minimal counters in `metrics.py` (e.g., `llm.request.enqueued`, `llm.response.received`, `llm.defense.rejected`, `orchestrator.format.sent`).

## Developer workflow
- Install & run: `make dev`, `make run` (Uvicorn on :18000), `make tunnel` (Cloudflare quick tunnel for Discord).
- Database: `make alembic-up` to apply migrations; `make db-up` for local Postgres (else SQLite via `DATABASE_URL`).
- Tests: `make test`. Async tests use `pytest-asyncio`. Seed RNG in rules tests (see `tests/test_dice.py`).
- Register slash commands: `python scripts/register_commands.py` (needs `DISCORD_*` in `.env`; for faster iteration set `DISCORD_GUILD_ID`).

## Project conventions & gotchas
- Keep request handlers fast: defer first, then follow-up via webhook.
- Always go through `repos.py` inside `async with session_scope()`; avoid inline SQL.
- Parse Discord payloads with `discord_schemas.Interaction`. For subcommands, see `_subcommand()` and `_option()` in `app.py`.
- Settings: prefer `config.load_settings()`; feature flags in `config.toml`. LLM is behind `[features].llm=true`; visibility behind `[features].llm_visible=true` (defaults to false).
- Pydantic v2: character sheet uses alias `class` → `class_name` (`populate_by_name=True`).
- Testing patterns:
  - End-to-end interaction tests assert deferred ack and background follow-up (see `tests/test_ooc_orchestrator.py`). When monkeypatching, patch the symbol used at the import site (e.g., `app.followup_message`) and stub `session_scope` in the handler module.
  - Orchestrator unit tests inject a fake `llm_client.generate_json` and optionally a `sheet_info_provider`.
  - Metrics counters can be asserted via `metrics.reset_counters()` + `metrics.get_counter()` (see `tests/test_metrics_counters.py`).

## Where to look first
- Core: `app.py`, `command_loader.py`, `commanding.py`, `responder.py`, `discord_schemas.py`.
- Rules: `rules/dice.py`, `rules/checks.py`.
- Data: `db.py`, `models.py`, `repos.py`.
- LLM: `llm.py`, `llm_utils.py`, `llm_prompts.py`, `orchestrator.py`.
- Commands: `commands/ooc_do.py` (writes transcripts, derives `allowed_actors` via `repos.list_character_names`, then calls orchestrator).
- Tests: `tests/test_dice.py`, `tests/test_checks.py`, `tests/test_ooc_orchestrator.py`, `tests/test_metrics_counters.py`.

Notes
- Don’t commit secrets; mirror new keys in `.env.example`.
- Keep PRs focused; prefer pure rules and thin I/O layers.
