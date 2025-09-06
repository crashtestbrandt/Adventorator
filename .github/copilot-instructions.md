# Copilot Instructions for Adventorator

Purpose: Make AI agents productive fast. Keep edits small, match existing patterns, and verify with tests before committing.

## Architecture: what matters
- Interactions service `src/Adventorator/app.py` (FastAPI) exposes `POST /interactions` for Discord. Always verify `X-Signature-*` via `crypto.verify_ed25519`, then respond within 3s using `responder.respond_deferred()` and do work in a background task.
- Command flow: `app._dispatch_command()` routes slash commands: `roll`, `check`, `sheet`, `ooc`. Use `responder.followup_message()` for webhook follow-ups.
- Rules engine (pure/deterministic): `src/Adventorator/rules/`
  - `dice.DiceRNG.roll(expr, advantage=False, disadvantage=False)` supports `XdY+Z`; adv/dis only for single d20; returns `DiceRoll` with `rolls/total/crit`.
  - `checks.compute_check(CheckInput, d20_rolls)` returns `CheckResult` (includes `success` when `dc` set).
- Persistence: Async SQLAlchemy in `db.py`; models in `models.py`; data access in `repos.py`. Use `async with session_scope()`—commit on exit. Avoid inline SQL in handlers.
- Schemas: Pydantic v2 in `schemas.py` and `discord_schemas.py`. Character sheet alias: `class -> class_name` (see `populate_by_name=True`).
- Logging: `logging.setup_logging()` configures structlog JSON logs; log events not strings.
- LLM (Phase 3, shadow mode): `llm.py` provides `LLMClient` (Ollama-like). Gated by `[features].llm=true` in `config.toml`; config under `[llm]`. `ooc` writes player transcript, builds messages from `repos.get_recent_transcripts`, calls `generate_response`, posts follow-up, then logs bot message. LLM must not mutate state directly.

## Dev workflow quickstart
- Setup: `make dev` to create venv and install; run with `make run` (Uvicorn on :18000). Tunnel for Discord with `make tunnel`.
- DB: Run `make alembic-up` before features needing persistence. Local Postgres: `make db-up` (else default SQLite via `DATABASE_URL`).
- Tests: `make test`. Async fixtures live in `tests/conftest.py`. Dice/Checks are pure—seed RNG as in `tests/test_dice.py`.
- Register slash commands: run `scripts/register_commands.py` (reads `.env` for `DISCORD_*`). Global by default; switch to guild route in the script for faster iteration (requires `DISCORD_GUILD_ID`).

## Patterns and gotchas
- Defer fast, then follow-up: keep handler under 3s. Example in `app.py` for `roll`/`check` formatting (include chosen d20 when adv/dis).
- Use `repos.py` for all DB I/O inside `async with session_scope()`; return simple dataclasses/rows—not ORM sessions—from helpers.
- Discord payloads: parse with `discord_schemas.Interaction`. Subcommand/options one level deeper; helpers `_subcommand()` and `_option()` are provided.
- Settings: Prefer `config.load_settings()` over raw env reads (except one-off scripts). Feature flags live in `config.toml`.
- LLM degraded mode: if `LLMClient.generate_response` times out/returns empty, send a polite ephemeral follow-up and skip mutations; always write transcripts for both sides.

## Where to look first
- Code: `app.py`, `responder.py`, `discord_schemas.py`, `rules/dice.py`, `rules/checks.py`, `db.py`, `models.py`, `repos.py`, `schemas.py`, `llm.py`.
- Tests: `tests/test_dice.py`, `tests/test_checks.py`, `tests/test_repos.py`, `tests/test_interactions.py` (message formats). See `tests/test_ollama_chat_nostream.py` for Ollama response example (reference-only).

Notes
- Don’t commit secrets. Use `.env.example` when adding new keys.
- Keep PRs focused; prefer pure rules and thin I/O layers.
