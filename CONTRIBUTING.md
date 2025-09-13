# Contributing to Adventorator

Welcome! 🎲

This guide will walk you through how to safely collaborate on this repository using Git and GitHub.

---

- [*Home (README)*](./README.md)
- [Collaboarating with Git & GitHub](#collaborating-with-git--github)
   - [Getting Started](#1-getting-started)
   - [Branching Workflow](#2-branching-workflow)
   - [Making Changes](#3-making-changes)
   - [Keeping Your Branch Updated](#4-keeping-your-branch-updated)
   - [Pushing & Pull Requests (PRs)](#5-pushing--pull-requests-prs)
   - [Best Practices](#6-best-practices)
   - [Common Commands Cheat Sheet](#7-common-commands-cheat-sheet)
   - [Troubleshooting](#8-troubleshooting)
   - [Where to Ask for Help](#9-where-to-ask-for-help)
- [Database Migrations (Alembic)](#database-migrations-alembic)
   - [What is Alembic?](#what-is-alembic)
   - [Why do we need it here?](#why-do-we-need-it-here)
   - [Developer Responsibilities](#developer-responsibilities)
   - [What to Commit](#what-to-commit)
   - [Typical Workflow](#typical-workflow)
   - [Example Alembic Migration Script](#example-alembic-migration-script)
   - [Key Points](#key-points)

---

## Collaborating with Git & GitHub

### 1. Getting Started

1. **Install Git**

   * [Download Git](https://git-scm.com/downloads) if you don’t already have it.
   * On macOS/Linux, you can also use Homebrew or your package manager.

2. **Clone the repository**

   ```bash
   git clone https://github.com/crashtestbrandt/Adventorator.git
   cd Adventorator
   ```

3. **Set your Git identity** (only once on your machine):

   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```

---

### 2. Branching Workflow

We use a **feature-branch workflow**:

* `main` → always stable, deployable
* Work happens on branches (`feature/...`, `bugfix/...`, `docs/...`)

#### Create a new branch

```bash
git checkout main
git pull origin main   # make sure you’re up to date
git checkout -b feature/short-description
```

Examples:

* `feature/add-sheet-crud`
* `bugfix/fix-dice-parser`
* `docs/update-readme`

---

### 3. Making Changes

1. **Edit files** in `src/Adventorator/` or other folders.

2. **Check your changes locally**:

   * Run the tests:

     ```bash
     make test
     ```
   * Run the linter:

     ```bash
     make lint
     ```
   * Start the app locally:

     ```bash
     make run
     ```

3. **Stage and commit**

   ```bash
   git add <files>
   git commit -m "Short, clear message about what you did"
   ```

> **Tip:** Keep commits small and focused. Use present tense, e.g., `"add transcript model"`.

---

### 4. Keeping Your Branch Updated

While working, keep your branch synced with `main`:

```bash
git fetch origin
git checkout main
git pull origin main
git checkout feature/your-branch
git merge main
```

If there are conflicts, Git will mark them—fix manually, then:

```bash
git add <fixed files>
git commit
```

---

### 5. Pushing & Pull Requests (PRs)

1. **Push your branch**

   ```bash
   git push -u origin feature/your-branch
   ```

2. **Open a Pull Request**

   * Go to the repo on GitHub
   * Click **“Compare & pull request”**
   * Fill in the template:

     * What problem you solved
     * What changes you made
     * How to test it

3. **Get a review**

   * Another team member reviews and approves.
   * Make changes if requested, then push again:

     ```bash
     git add <files>
     git commit -m "address review comments"
     git push
     ```

4. **Merge**

   * Once approved and checks pass, **Squash & Merge** into `main`.

---

### 6. Best Practices

* **One branch = one task.** Don’t mix unrelated changes.
* **Write meaningful commit messages.**
* **Run tests and lint before pushing.**
* **Never commit secrets** (API keys, passwords, tokens).
* **Ask questions early**—better to clarify than guess.

---

### 7. Common Commands Cheat Sheet

| Task                      | Command                                |
| ------------------------- | -------------------------------------- |
| Clone repo                | `git clone <url>`                      |
| New branch                | `git checkout -b feature/thing`        |
| Switch branch             | `git checkout branch-name`             |
| See status                | `git status`                           |
| Stage file                | `git add file.py`                      |
| Commit staged changes     | `git commit -m "message"`              |
| Pull latest main          | `git pull origin main`                 |
| Merge main into branch    | `git merge main`                       |
| Push branch to GitHub     | `git push -u origin feature/thing`     |
| View log (recent commits) | `git log --oneline --graph --decorate` |

---

### 8. Troubleshooting

* **“I accidentally committed to main”**

  * Make a branch from main, reset main:

    ```bash
    git checkout -b feature/fix-branch
    git push -u origin feature/fix-branch
    ```

    Then restore `main` with:

    ```bash
    git checkout main
    git reset --hard origin/main
    ```

* **Merge conflicts**

  * Open the conflicted file, look for `<<<<<<<` and `>>>>>>>`, fix manually, then:

    ```bash
    git add file.py
    git commit
    ```

* **Forgot to pull before pushing**

  * Run:

    ```bash
    git pull --rebase origin main
    git push
    ```

---

### 9. Where to Ask for Help

* Post questions in the team’s chat channel
* Tag `@repo-maintainers` in your PR if you need review
* For Git basics: [GitHub Docs](https://docs.github.com/en/get-started/using-git)

---

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

Perfect — here’s a “toy migration” you can drop into your `CONTRIBUTING.md` as a visual aid. It shows what Alembic scripts look like, and emphasizes the `upgrade` vs `downgrade` pattern.

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

## Working on the Planner and /act

Phase 4 adds a planner that routes freeform `/act` messages to strict, validated commands.

Tips for contributors:

- Feature flags
   - Enable in `config.toml` or env: `features.llm=true`, `features.planner=true`.
   - For safe rollout, keep `features.llm_visible=false` (shadow mode) while testing.
- Tests
   - Run `make test` to execute unit/integration tests including planner routing (`tests/test_act_*.py`).
   - Use the fake LLM pattern in tests to return a JSON plan (see `_FakeLLM` fixtures in tests).
   - Metrics assertions are available via `metrics.reset_counters()` and `metrics.get_counter()`.
- Caching & rate limits
   - `/act` caches decisions for 30s per (scene_id, message) and rate-limits per user (simple in-memory window).
- Safety guardrails
   - The planner is allowed to route only to: `roll`, `check`, `sheet.create`, `sheet.show`, `do`, `ooc`.
   - All args must validate against the target command’s Pydantic option model; invalid → ephemeral error.
- CLI & registration
   - The dynamic CLI (`scripts/cli.py`) mirrors slash commands; test `/act` locally without Discord.
   - To register commands in a dev guild, set Discord env vars and run `python scripts/register_commands.py`.

When in doubt, prefer small, focused PRs and add tests alongside new behavior.


