
# Copilot Instructions for Adventorator

Purpose
- Make agents productive fast by codifying THIS repo’s architecture, workflows, and conventions. Keep edits small, match patterns, and verify with tests.

Architecture (big picture)
- FastAPI edge: `src/Adventorator/app.py` exposes `/interactions`; verify Discord Ed25519 signatures and always defer within ~3s, then follow up via webhook.
- Command registry: `commanding.py` (`@slash_command`) + `command_loader.py`; handlers live in `commands/` and receive an `Invocation` with a transport-agnostic `responder`.
- Responder: Use `await inv.responder.send(content, ephemeral=...)` for all replies (never return raw FastAPI responses from handlers).
- Rules: Deterministic engine in `rules/` (`dice.py`, `checks.py`, `engine.py`). Prefer the injected `inv.ruleset` (default `Dnd5eRuleset`) over ad‑hoc dice math.
- AI split: `planner.py` (intent → command) and `orchestrator.py` (narration + mechanics). All LLM output is JSON-only and strictly parsed (`llm_utils.py`/schemas).
- Data layer: Async SQLAlchemy via `db.session_scope()`, models in `models.py`, helpers in `repos.py`. Never inline SQL in handlers.
- Ops: Minimal counters in `metrics.py`; JSON logging via `logging.py`; endpoints `GET /healthz`, `GET /metrics` (feature-flagged).

Developer workflow
- Bootstrap/run: `make dev`, `make run` (port 18000), `make tunnel` (cloudflared). Register slash commands with `python scripts/register_commands.py`.
- DB: `make alembic-up` (aka `make db-upgrade`); start local Postgres with `make db-up`. SQLite is default when `DATABASE_URL` is unset.
- Quality: `make test`, `make lint` (ruff), `make type` (mypy), `make format`.
- CLI: `scripts/cli.py` dynamically discovers commands for local testing (set `PYTHONPATH=./src`).

Conventions & patterns
- Handlers: validate options via Pydantic v2 `Option` models (`populate_by_name=True`), then use `inv.responder.send()`; keep I/O thin, move logic to rules/services.
- Scene/persistence: In handlers that write/read, wrap calls in `async with session_scope()` and use `repos.*` helpers.
- Discord parsing: Use `discord_schemas.Interaction`; see `app._subcommand()` for nested option parsing.
- Feature flags (from `config.toml`): `features.llm`, `features.llm_visible`, `features.planner` (`feature_planner_enabled`), `ops.metrics_endpoint_enabled`.
- Ruleset injection: `Invocation.ruleset` is passed from `app.py` so commands can call `inv.ruleset.perform_check(...)` and `inv.ruleset.roll_dice(...)`.
- Dev headers: `X-Adventorator-Use-Dev-Key` (trusted dev public key) and `X-Adventorator-Webhook-Base` (route follow-ups to a local sink in dev).

AI specifics (planner/orchestrator)
- Planner allowlist: only routes to `roll`, `check`, `sheet.create`, `sheet.show`, `do`, `ooc`. 30s cache by `(scene_id, message)`; per-user RL ~5/min; soft timeout falls back to `/roll 1d20`.
- Orchestrator defenses: require action `ability_check`, ability in whitelist, DC 5–30; reject banned verbs (e.g., “deal damage”, “modify inventory”) and unknown actors (vs. allowed names from campaign). Uses `CharacterService` to derive sheet/proficiency context when available. Visibility controlled by `features.llm_visible`.

Key files/dirs
- Core: `app.py`, `command_loader.py`, `commanding.py`, `responder.py`, `discord_schemas.py`, `config.py`, `logging.py`.
- Rules: `rules/dice.py`, `rules/checks.py`, `rules/engine.py`.
- AI: `llm.py`, `llm_utils.py`, `llm_prompts.py`, `planner.py`, `orchestrator.py`, `planner_prompts.py`, `planner_schemas.py`.
- Commands: `commands/act.py` (planner), `commands/do.py` (orchestrator), `commands/roll.py`, `commands/check.py`, `commands/ooc.py`, `commands/sheet.py`.
- Tests: `tests/` (see `test_dice.py`, `test_checks.py`, `test_planner.py`, `test_orchestrator.py`, `test_metrics_counters.py`, `test_interactions*.py`).

Examples
- Dice: `DiceRNG.roll("1d20+3", advantage=True)`; Checks: `compute_check(CheckInput(...), d20_rolls=[...])`.
- Handler shape: `@slash_command(...)
	async def mycmd(inv, opts): await inv.responder.send("...")`.
- Orchestrator entry: call `run_orchestrator(scene_id, player_msg, sheet_info_provider, llm_client=inv.llm_client, allowed_actors=...)` and persist transcripts via `repos`.

Testing notes
- Patch at import site; inject fake LLM clients; seed RNG for deterministic rules tests. Use `metrics.reset_counters()` and assert via `get_counter()`.
- End-to-end tests expect deferred ACK then follow-up; see `tests/test_interactions*.py`.

Keep PRs focused; prefer pure rules and thin I/O layers. When unsure, mirror the latest patterns in `commands/`, `rules/`, and `tests/`.
