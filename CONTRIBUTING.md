# Contributing to Adventorator

Welcome! This guide focuses on repo-specific workflows and expectations. For general Git usage, please refer to GitHub’s documentation.

- [Home (README)](./README.md)
- [AI Development Pipeline Workflow](#ai-development-pipeline-workflow)
- [Branching and PRs](#branching-and-prs)
- [Local checks](#local-checks)
- [Feature flags](#feature-flags)
- [Database migrations (Alembic)](#database-migrations-alembic)
- [LLM/planner/orchestrator testing](#llmplannerorchestrator-testing)

---

## AI Development Pipeline Workflow

Adventorator organizes delivery using the AI-Driven Development (AIDD) pipeline. Review the [alignment plan](./docs/implementation/aidd-plan.md) for a phased view of how governance assets, templates, and automation fit together before starting new work.

### Plan with Templates and DoR/DoD Rituals
- Create Feature Epics, Stories, and Tasks with the issue templates in [`.github/ISSUE_TEMPLATE/`](./.github/ISSUE_TEMPLATE/). Fill out the Definition of Ready/Done fields and link to the relevant ADRs, prompts, contracts, and evaluation assets so downstream contributors (human or AI) can pick up the work.
- Keep traceability current in [`docs/implementation/epics/`](./docs/implementation/epics/) and confirm checklist expectations using the [DoR/DoD guide](./docs/implementation/dor-dod-guide.md).
- Reference architectural decisions in [`docs/adr/`](./docs/adr/) using the [`ADR-TEMPLATE.md`](./docs/adr/ADR-TEMPLATE.md) and keep diagrams or system maps in [`docs/architecture/`](./docs/architecture).

### Manage Prompts, Contracts, and Evaluations
- Store AI prompt updates in the [`prompts/`](./prompts) registry and follow the [versioning workflow](./prompts/README.md). Pair prompt changes with evaluation fixtures (for example the assets under [`prompts/evals/`](./prompts/evals/)) so quality gates can exercise them.
- Capture API or schema deltas in [`contracts/`](./contracts) and document compatibility in the [contract workspace README](./contracts/README.md). Link Stories/Tasks to these artifacts for contract-first delivery.
- When automation requires additional validation (e.g., ADR linting or prompt checks), use the scripts in [`scripts/`](./scripts) such as [`validate_prompts_and_contracts.py`](./scripts/validate_prompts_and_contracts.py).

### Satisfy Quality Gates
- Pull requests should include the Story/Task references and quality results requested by [`.github/pull_request_template.md`](./.github/pull_request_template.md). Reviewers will block merges when gates are missing.
- Run the full `make quality-gates` target before requesting review; it chains coverage, mutation, security, artifact validation, and AI evaluation checks defined in the [Makefile](./Makefile). CI enforces the same policies via [`tests.yml`](./.github/workflows/tests.yml) and [`pr-quality-gates.yml`](./.github/workflows/pr-quality-gates.yml).
- Capture any gate failures or DoR/DoD gaps in the linked issue template so other contributors (including AI assistants) can continue the workflow transparently.

## Branching and PRs

- Create small, focused branches (e.g., `feature/executor-attack-preview`, `fix/retrieval-null-check`).
- Open PRs early; link to the phase/issue in the description and include test notes.
- Squash & merge once CI passes and a reviewer approves.

## Local checks

Before pushing:

```bash
make test
make lint
make type
```

For manual runs:

```bash
make run           # FastAPI app (port 18000)
make tunnel        # cloudflared for Discord webhook ingress
make alembic-up    # apply DB migrations
```

## Feature flags

Toggle behavior in `config.toml` or via env. Common flags:

- `features_llm`, `features_llm_visible`, `features_planner`
- `features_executor`, `features_executor_confirm`, `features_events`
- `retrieval.enabled`, `ops.metrics_endpoint_enabled`

These should default to safe modes; tests often flip them explicitly.

## Database Migrations (Alembic)

*What is this and what do I do with it?*

We use **[Alembic](https://alembic.sqlalchemy.org/)** to manage database schema changes.

### What is Alembic?

* It’s a **migration tool** for SQLAlchemy projects.
* Instead of hand-editing tables in dev/prod databases, you write or autogenerate **migration scripts**.
* Each script describes how to **upgrade** the schema (add column, new table, etc.) and how to **downgrade** (rollback).
* Alembic keeps a version history in the `migrations/versions/` folder.

### Why do we need it here?

* Our bot persists campaigns, characters, scenes, and transcripts in a relational DB.
* The schema will evolve as features ship (new tables, extra fields).
* Alembic keeps every dev, test, and prod database in sync with the **current schema** in source control.
* CI/CD and teammates can run the same migrations to reproduce the DB state.

### Developer Responsibilities

* **Don’t edit tables by hand.** Always go through Alembic.
* When you change a model in `src/Adventorator/models.py`:

  1. Make sure your local DB is running (`make db-up`).
  2. Run:

     ```bash
     make alembic-rev m="describe change"
     make alembic-up
     ```

     * `alembic-rev` autogenerates a new script in `migrations/versions/`.
     * `alembic-up` applies it to your local DB.
  3. Inspect the generated script — fix anything weird (autogen isn’t perfect).
  4. Commit the migration script **along with your model changes**.
* To roll back one step (rare):

  ```bash
  make alembic-down
  ```
* To reset your dev DB completely:

  ```bash
  dropdb adventorator && createdb adventorator
  make alembic-up
  ```

### What to Commit

* **Commit:** everything under `migrations/` (except `*.sqlite3` test DBs).
* **Don’t commit:** your local database, `.env`, or `.sqlite3` files.
* `alembic.ini` is tracked but should not contain secrets (we load `DATABASE_URL` from env).

### Typical Workflow

1. Pull main branch, run `make alembic-up` → your DB is current.
2. Make a schema change in models.
3. Generate a revision: `make alembic-rev m="add field X"`.
4. Apply: `make alembic-up`.
5. Commit the code **and** the new migration file.

## Example Alembic Migration Script

When you run `make alembic-rev m="add characters table"`, Alembic creates a new file in `migrations/versions/` with a filename like `20240925_1234_add_characters_table.py`.

A typical migration looks like this:

```python
"""add characters table

Revision ID: 2b1ae634e5cd
Revises: None
Create Date: 2025-09-05 10:15:00.123456
"""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "2b1ae634e5cd"   # unique id for this migration
down_revision = None        # previous migration id, or None if first
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change (schema goes forward)."""
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("sheet", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    """Undo the change (schema goes back)."""
    op.drop_table("characters")
```

### Key points

* `upgrade()` → define schema changes going **forward**.
* `downgrade()` → define how to **roll back**.
* Alembic autogenerates most code based on your SQLAlchemy models, but you should **review/edit** before committing.
* Each migration has a `revision` (unique ID) and `down_revision` (its parent in the chain).

---

## LLM/Planner/Orchestrator testing

Phase 4 adds a planner that routes freeform `/plan` messages to strict, validated commands.

Tips for contributors:

- Feature flags
   - Enable in `config.toml` or env: `features.llm=true`, `features.planner=true`.
   - For safe rollout, keep `features.llm_visible=false` (shadow mode) while testing.
- Tests
   - Run `make test` to execute unit/integration tests including planner routing (`tests/test_act_*.py`).
   - Use the fake LLM pattern in tests to return a JSON plan (see `_FakeLLM` fixtures in tests).
   - Metrics assertions are available via `metrics.reset_counters()` and `metrics.get_counter()`.
- Caching & rate limits
   - `/plan` caches decisions for 30s per (scene_id, message) and rate-limits per user (simple in-memory window).
- Safety guardrails
   - The planner is allowed to route only to: `roll`, `check`, `sheet.create`, `sheet.show`, `do`, `ooc`.
   - All args must validate against the target command’s Pydantic option model; invalid → ephemeral error.
 - Registration: set Discord env vars and run `python scripts/register_commands.py` to update slash commands in a dev guild.

When in doubt, prefer small, focused PRs and add tests alongside new behavior.


