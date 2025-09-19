# Adventorator Agent Guidelines

These instructions apply to the entire repository.

## Development workflow
- Prefer the existing Makefile targets (`make dev`, `make run`, `make tunnel`) instead of ad-hoc scripts when bootstrapping or running the service.
- When modifying Python code, run `make format`, `make lint`, `make type`, and `make test` before committing. For docs-only edits these checks are optional.
- Set `PYTHONPATH=./src` when invoking helper scripts (e.g., `scripts/web_cli.py`, `scripts/register_commands.py`).
- Database upgrades should use the provided Alembic tasks (`make alembic-up` / `make db-upgrade`) and Postgres via `make db-up` when persistent storage is required.

## Coding conventions
- Follow the FastAPI + async SQLAlchemy patterns already established in `src/Adventorator/app.py` and `src/Adventorator/repos.py` (async context managers, no inline SQL in handlers).
- Use the command registry decorators (`@slash_command`) and responder abstraction (`inv.responder.send(...)`) when adding interaction handlers.
- Feature flags live in `config.toml` under `[features]`; new behavior must default to disabled and integrate with the existing config dataclass.
- Structured logging goes through `action_validation.logging_utils.log_event` / `log_rejection` or the repo-wide logging helpers. Emit metrics via `Adventorator.metrics.inc_counter`.

## Documentation
- Link to the root `CHANGELOG.md` when referencing release notes.
- Keep manual test plans in `docs/dev/` aligned with the current feature-flag expectations and include both Web CLI and Discord flows when relevant.

## Pull requests & summaries
- Summaries should highlight user-visible behavior changes, mention affected modules, and tie back to action-validation milestones when applicable.
- If checks are skipped, call that out explicitly in the final response along with the reason.
