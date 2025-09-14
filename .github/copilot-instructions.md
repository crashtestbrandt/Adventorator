
# Copilot Instructions for Adventorator

## Purpose
Enable AI agents to quickly and safely contribute to Adventorator by following project-specific architecture, workflow, and conventions. Keep edits small, match existing patterns, and always verify with tests.

## Architecture Overview
- **FastAPI backend**: `src/Adventorator/app.py` exposes `/interactions` for Discord/CLI. All requests are signature-verified (`crypto.verify_ed25519`) and must respond within 3s (defer, then follow-up).
- **Command routing**: `app._dispatch_command()` uses the registry in `commanding.py` to dispatch to handlers in `commands/`.
- **Responder pattern**: Handlers use `await responder.send()` or `await responder.followup_message()` for Discord/webhook replies.
- **Rules engine**: Deterministic mechanics in `rules/dice.py` and `rules/checks.py`. Use `DiceRNG.roll()` and `compute_check()` for all dice logic.
- **Planner/LLM orchestration**: `planner.py` and `orchestrator.py` coordinate LLM intent mapping, rules application, and narration. LLM proposals are JSON-only, parsed strictly in `llm_utils.py`/`schemas.py`.
- **Persistence**: Async SQLAlchemy in `db.py`, ORM in `models.py`, helpers in `repos.py`. Always use `async with session_scope()` in handlers.
- **Metrics**: Minimal counters in `metrics.py` (e.g., `llm.request.enqueued`).

## Developer Workflow
- **Install & run**: Use `make dev` for setup, `make run` to start Uvicorn on :18000, and `make tunnel` for Discord integration.
- **Database**: `make alembic-up` for migrations, `make db-up` for local Postgres. Use `DATABASE_URL` for SQLite fallback.
- **Testing**: Run `make test` (pytest, async supported). Seed RNG in rules tests (see `tests/test_dice.py`).
- **Slash command registration**: `python scripts/register_commands.py` (requires `DISCORD_*` in `.env`).

## Project Conventions & Patterns
- **Handlers**: Always defer immediately, then follow up via webhook.
- **Data access**: Only use `repos.py` helpers inside `async with session_scope()`; never inline SQL.
- **Discord payloads**: Parse with `discord_schemas.Interaction`. Use `_subcommand()`/`_option()` helpers in `app.py` for options.
- **Settings**: Use `config.load_settings()` and feature flags in `config.toml` (`[features].llm`, `[features].llm_visible`).
- **Pydantic v2**: Character sheet uses alias `class` → `class_name` (`populate_by_name=True`).
- **Testing**: End-to-end tests assert deferred ack and follow-up (see `tests/test_ooc_orchestrator.py`). Patch at import site. Orchestrator tests inject fake LLM clients. Metrics can be asserted via `metrics.reset_counters()` and `metrics.get_counter()`.

## Key Files & Directories
- **Core**: `app.py`, `command_loader.py`, `commanding.py`, `responder.py`, `discord_schemas.py`
- **Rules**: `rules/dice.py`, `rules/checks.py`, `rules/engine.py`
- **Data**: `db.py`, `models.py`, `repos.py`
- **LLM/Planner**: `llm.py`, `llm_utils.py`, `llm_prompts.py`, `planner.py`, `orchestrator.py`, `planner_prompts.py`, `planner_schemas.py`
- **Commands**: `commands/` (see `ooc_do.py` for orchestrator integration)
- **Tests**: `tests/` (see `test_dice.py`, `test_checks.py`, `test_ooc_orchestrator.py`, `test_metrics_counters.py`)

## Integration & Gotchas
- **LLM**: All LLM output must be JSON and parsed strictly. Orchestrator applies safety gates (action whitelist, DC bounds, verb blacklist, etc.). LLM visibility is feature-flagged.
- **Caching**: 30s in-process cache on `(scene_id, player_msg)` to suppress duplicate prompts.
- **Metrics**: Use `metrics.py` for counters; assert in tests as needed.
- **Secrets**: Never commit secrets; update `.env.example` for new keys.

## Example Patterns
- **Dice roll**: `DiceRNG.roll("1d20+3", advantage=True)`
- **Check**: `compute_check(CheckInput(...), d20_rolls=[...])`
- **Handler**: `async def handle_do(...): await responder.send(...); ...`
- **Test**: Patch at import site, stub `session_scope`, inject fake LLM client.

---
Keep PRs focused; prefer pure rules and thin I/O layers. When in doubt, match the style and structure of the most recent code in `commands/`, `rules/`, and `tests/`.
