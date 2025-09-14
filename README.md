# Adventorator

*The best adventures are the ones **no one** has to plan.*

A Discord-native Dungeon Master bot that runs tabletop RPG campaigns directly in chat. It blends deterministic game mechanics with AI-powered narration, letting players experience a text-based campaign without needing a human DM online 24/7.

---

## Development

### Quick Dev Setup

![](/docs/images/usage-slash-check.jpeg)


* [Overview](#overview)
* [Prerequisites](#prerequisites) & [Quickstart](#quickstart)
* [Database & Alembic](#database--alembic)
* [Configuration](#configuration)
* [Commands](#commands)
* [Operations](#operations)
* [Repo Structure](#repo-structure)
* [Contributing](./CONTRIBUTING.md)

---

## Overview

Adventorator is a FastAPI application that serves as a backend for a Discord bot. It receives slash command interactions, verifies their authenticity using Ed25519 signatures, and processes them asynchronously to provide a rich, interactive TTRPG experience.

**✨ What it does (today)**

* Discord-first gameplay with slash commands: `/roll`, `/check`, `/sheet`, `/ooc`, and the smart router `/act`.
* Fast 3-second deferral on all interactions; real work happens asynchronously with webhook follow-ups.
* A deterministic `rules` engine for dice and ability checks (advantage/disadvantage, crits, modifiers).
* Campaign persistence via async SQLAlchemy and Alembic, including full transcripts of player and bot messages.

**🚧 Project Status**

* [X] Phase 0: Verified interactions endpoint, 3s deferral, logging.
* [X] Phase 1: Deterministic dice + checks, `/roll` and `/check` commands.
* [X] Phase 2: Persistence (campaigns, characters, transcripts).
* [X] Phase 3: Shadow LLM narrator, proposal-only.
* [X] Phase 4: Planner + `/act` smart routing.
* [ ] Phase 5+: Combat system, content ingestion, GM controls, premium polish.

**🔜 Roadmap**

* Add `/sheet` CRUD with strict JSON schema.
* Initiative + combat encounters with Redis turn locks.
* Adventure ingestion pipeline for SRD or custom campaigns.
* Optional Embedded App for lightweight maps/handouts in voice channels.

---

## Architecture

This project follows a modular, layered architecture designed for security, testability, and extensibility, especially when integrating with LLMs.

* **FastAPI** server implements the Discord Interactions endpoint, verifies signatures, and defers responses to work asynchronously.
* A **Command Registry** (`Adventorator/commanding.py`) discovers and routes requests to handlers located in `Adventorator/commands/`.
* A pure Python **Rules Engine** (`Adventorator/rules/`) implements deterministic game mechanics like dice rolls and ability checks.
* An asynchronous **Data Layer** using SQLAlchemy (`repos.py`) provides structured access to the database.
* The optional **AI Layer** is split into two distinct components: a `Planner` for routing and an `Orchestrator` for game logic.

**Diagram: High-Level System Architecture**

```mermaid
flowchart TD
  %% === External ===
  subgraph EXTERNAL[External]
    U[Player on Discord]:::ext
    DP[Discord Platform<br/>Commands & Interactions]:::ext
    WH[Discord Webhooks API<br/>Follow-up Messages]:::ext
    LLM[LLM API<br/>e.g., Ollama]:::ext
  end

  %% === Network Edge ===
  CF[cloudflared Tunnel<br/>optional for local dev]:::edge

  %% === App ===
  subgraph APP[Adventorator - FastAPI]
    subgraph REQUEST[Request Handling]
      A[POST /interactions]
      SIG[Ed25519 Verify<br/>X-Signature-*]
      DISP[Command Dispatch<br/>registry in commanding.py]
  DEF[Deferred ACK]
    end

    subgraph BUSINESS[Command Logic]
      RULES[Rules Engine<br/>dice, checks]
      REPOS[Repos & Context<br/>session_scope + repos.py]
      PLAN[Planner/Orchestrator<br/>JSON-only + safety + 30s cache]
    end

    subgraph RESPONSE[Response]
      RESP[Responder<br/>follow-up webhooks]
      TRANS[Transcript Logger]
      MET[Metrics Counters]
      LOGS[Structlog JSON Logs]
    end
  end

  %% === Data ===
  subgraph DATA[Data]
    DB[(Postgres or SQLite<br/>campaigns, characters, transcripts)]:::data
    MIG[Alembic Migrations]:::ops
  end

  %% === Tooling ===
  subgraph TOOLING[Tooling]
    CLI[Dynamic CLI<br/>scripts/cli.py]:::ops
    REG[scripts/register_commands.py]:::ops
    TEST[pytest suite]:::ops
    CFG[config.toml<br/>feature flags + logging]:::ops
  end

  %% === Ingress Flow ===
  U -->|Slash command| DP
  DP -->|signed request| CF
  CF --> A
  A --> SIG
  SIG -->|valid| DISP
  SIG -.->|invalid| DEF
  DISP --> DEF

  %% === Command Paths (examples) ===
  DISP -- "/roll" --> RULES --> RESP
  DISP -- "/check" --> RULES --> RESP
  DISP -- "/sheet" --> REPOS --> RESP
  DISP -- "/ooc" --> REPOS --> PLAN --> LLM --> RESP
  DISP -- "/act" --> REPOS --> PLAN -->|route| RULES --> RESP

  %% === Egress ===
  RESP --> TRANS -->|write| DB
  RESP -->|POST| WH --> DP --> U
  LOGS -.-> APP
  MET -.-> APP

  %% === Styles ===
  classDef ext  fill:#eef7ff,stroke:#4e89ff,stroke-width:1px,color:#0d2b6b
  classDef edge fill:#efeaff,stroke:#8b5cf6,stroke-width:1px,color:#2b1b6b
  classDef data fill:#fff7e6,stroke:#f59e0b,stroke-width:1px,color:#7c3e00
  classDef ops  fill:#eefaf0,stroke:#10b981,stroke-width:1px,color:#065f46
  ```

### Core AI Components: Planner and Orchestrator

The distinction between the `planner` and `orchestrator` is a key architectural decision that promotes security and modularity. They are intentionally separate and serve different purposes.

#### Planner: The Semantic Router

The **`planner`** (`Adventorator/planner.py`) acts as a natural language front-end to the bot's structured command system. It translates a user's freeform request from the `/act` command into a specific, validated command invocation.

  * **Responsibilities:**
      * Dynamically builds a catalog of available, developer-defined slash commands.
      * Uses the LLM to analyze a user's intent and select the single best command "tool" to fulfill it.
      * Outputs a structured JSON object (`PlannerOutput`) specifying the command and its arguments.
  * **Analogy:** The planner is a smart switchboard operator. It listens to a request and connects the user to the correct department (the command handler).

#### Orchestrator: The Game Engine

The **`orchestrator`** (`Adventorator/orchestrator.py`) is the core AI Dungeon Master. It is invoked by narrative commands like `/do` to interpret a player's action within the game world and determine the outcome.

  * **Responsibilities:**
      * Gathers context from recent game history (`transcripts`).
      * Uses the LLM to propose a specific game mechanic (e.g., a "Strength check vs. DC 15") and generate descriptive narration.
      * Performs strict validation on the LLM's proposal to prevent it from bypassing the rules (e.g., by banning verbs like "deal damage" or "add item").
      * Executes the proposed mechanic using the deterministic `rules` engine.
      * Combines the mechanic's outcome with the narration into a final result.
  * **Analogy:** The orchestrator *is* the Dungeon Master. It listens to what a player wants to do, decides which dice roll is needed, and describes what happens.

This separation of concerns ensures that the flexible, high-level routing logic is decoupled from the secure, low-level game state progression.

### Key Command Flows

#### The `/act` Command Flow

This diagram shows how the `planner` and `orchestrator` work together when a user invokes the `/act` command to perform an in-game action.

```mermaid
sequenceDiagram
    actor User
    participant App as Adventorator Service
    participant Planner
    participant Orchestrator
    participant RulesEngine as Rules Engine
    participant LLM

    User->>App: /act "I try to pick the lock"
    App->>Planner: plan(intent)
    Planner->>LLM: Which command for this text?
    LLM-->>Planner: {"command": "do", "args": ...}
    Planner-->>App: Return planned command
    
    Note over App: Dispatches to /do handler
    
    App->>Orchestrator: run_orchestrator("I try to pick the lock")
    Orchestrator->>LLM: Propose mechanics & narration
    LLM-->>Orchestrator: {"proposal": {"ability": "DEX", "dc": 18}, "narration": ...}
    Orchestrator->>RulesEngine: compute_check(DEX, DC=18)
    RulesEngine-->>Orchestrator: {total: 14, success: false}
    Orchestrator-->>App: Return formatted result (mechanics + narration)
    
    App-->>User: Sends follow-up message with outcome
```

#### The `/ooc` Command Flow

This flow is simpler, as it bypasses the `planner` and the `rules` engine, using the LLM only for narration.

```mermaid
sequenceDiagram
  participant User
  participant App as Adventorator Service
  participant DB as Database
  participant LLM as LLM API

  User->>App: /ooc "What does the room smell like?"
  
  Note over App: Dispatches "ooc" command
  
  App->>DB: get_recent_transcripts(scene_id)
  DB-->>App: Return transcript history
  
  Note over App: Formats history and user message into prompt
  
  App->>LLM: generate_response(prompt)
  LLM-->>App: Return text-only narration
  
  App-->>User: Sends follow-up message with narration
```

-----

## Prerequisites

  - Bash-like environment
  - Docker
  - Python \> 3.10
  - [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
  - [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (`brew install cloudflared` on macOS)

## Quickstart

```bash
cp .env.example .env    # <-- Add secrets
make dev                # Install Python requirements
make db-upgrade         # Initialize the database schema
make run                # Start local dev server on port 18000
```

To expose your local server to Discord, run the Cloudflare tunnel in a separate terminal:

```bash
make tunnel
```

Discord can now reach your dev server using the tunnel URL + `/interactions`.

-----

## Database & Alembic

Adventorator uses SQLAlchemy with Alembic for database migrations. Initialize your database schema before running commands that require persistence.

```bash
# Apply all migrations (run this once on setup)
make db-upgrade
# OR
alembic upgrade head
```

Common commands:

```bash
# Generate a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"

# Roll back one migration
alembic downgrade -1
```

By default, `alembic.ini` points at the `DATABASE_URL` from your configuration. For local development, SQLite is used by default.

-----

## Configuration

Behavior is configured via `config.toml`, which can be overridden by environment variables or a `.env` file.

**Key Toggles:**

  * `features.llm`: Master switch for all LLM-powered features (`/ooc`, `/act`).
  * `features.llm_visible`: If `true`, LLM narration is posted publicly; otherwise, it runs in a "shadow mode" (logged but not sent to Discord).
  * `features.planner`: Hard on/off switch for the `/act` planner.
  * `ops.metrics_endpoint_enabled`: If `true`, exposes a `GET /metrics` endpoint.

**LLM Client:**

  * `llm.api_provider`: `"ollama"` or `"openai"`.
  * `llm.api_url`: Base URL for your provider (e.g., `http://localhost:11434` for Ollama).
  * `llm.model_name`: Model identifier (e.g., `"llama3:latest"`).

See `src/Adventorator/config.py` for all options and default values.

-----

## Commands

### Adding New Commands

The application uses a decorator-based system to discover and register new commands.

1.  **Create a command file** in `src/Adventorator/commands/`, e.g., `greet.py`:

    ```python
    # src/Adventorator/commands/greet.py
    from pydantic import Field
    from Adventorator.commanding import Invocation, Option, slash_command

    class GreetOpts(Option):
        name: str = Field(description="Who to greet")

    @slash_command(name="greet", description="Say hello", option_model=GreetOpts)
    async def greet(inv: Invocation, opts: GreetOpts):
        await inv.responder.send(f"Hello, {opts.name}!")
    ```

2.  **Test it locally** with the dynamic CLI:

    ```bash
    # The CLI auto-discovers the new command
    PYTHONPATH=./src python scripts/cli.py greet "World"
    ```

3.  **Register it with Discord:**

    ```bash
    # Fill out DISCORD_* variables in .env first
    python scripts/register_commands.py
    ```

### Using the `/act` Smart Router

`/act` lets players use natural language, which is routed to a known command.

  * `/act "roll 2d6+3 for damage"` → routes to `/roll --expr 2d6+3`
  * `/act "make a dexterity check against DC 15"` → `/check --ability DEX --dc 15`
  * `/act "I sneak along the wall"` → `/do --message "I sneak along the wall"`

**Safety & Guardrails:**

  * **Allowlist:** Only routes to a pre-defined set of safe commands.
  * **Validation:** All arguments must pass the target command’s Pydantic option model.
  * **Caching:** Identical messages are cached for 30 seconds to reduce LLM load.
  * **Rate Limiting:** A lightweight per-user limiter prevents spam.
  * **Fallbacks:** A soft timeout will fall back to a simple `/roll 1d20`.

-----

## Operations

The FastAPI app exposes two operational endpoints:

  * `GET /healthz`: A lightweight check that the application can load commands and connect to the database. Returns `{"status":"ok"}` or a 500 error.
  * `GET /metrics`: A JSON dump of internal counters. Disabled by default; enable with `ops.metrics_endpoint_enabled=true`.

-----

## Docker / Compose

To run Postgres and the app together:

```bash
docker compose up -d --build db app
```

Ensure `.env` has:

```env
DATABASE_URL=postgresql+asyncpg://adventorator:adventorator@db:5432/adventorator
```

On your host (or inside the app container), apply migrations:

```bash
make alembic-up
```

The app will be available on http://localhost:18000.

Tip: For local-only dev without containers, set `DATABASE_URL=sqlite+aiosqlite:///./adventorator.sqlite3` and use the Quick Dev Setup above.

-----

## Development Setup: Postgres

Use Postgres locally either via Docker Compose or a standalone container.

Option A — docker compose (recommended)

```bash
# Start DB and app
docker compose up -d --build db app

# Set DATABASE_URL in .env to the db service hostname
# DATABASE_URL=postgresql+asyncpg://adventorator:adventorator@db:5432/adventorator

# Apply migrations from your host (or inside the app container)
make alembic-up
```

Option B — standalone Postgres container

```bash
# Start a local Postgres 16 container
docker run --rm -d --name advdb \
  -e POSTGRES_PASSWORD=adventorator \
  -e POSTGRES_USER=adventorator \
  -e POSTGRES_DB=adventorator \
  -p 5432:5432 postgres:16

# Point DATABASE_URL at localhost
# DATABASE_URL=postgresql+asyncpg://adventorator:adventorator@localhost:5432/adventorator

# Apply migrations
make alembic-up
```

Notes
- You can switch back to SQLite any time by setting `DATABASE_URL=sqlite+aiosqlite:///./adventorator.sqlite3`.
- Alembic reads `DATABASE_URL` (via `.env`), and will choose the proper sync driver under the hood for migrations.

-----

## Repo Structure

```
.
├── alembic.ini                  # Alembic config for database migrations
├── config.toml                  # Project-level config (feature flags, etc.)
├── migrations/                  # Alembic migration scripts
├── scripts/                     # Utility scripts (register commands, CLI)
├── src/                         # Application source code
│   └── Adventorator/
│       ├── app.py               # FastAPI entrypoint & Discord interactions
│       ├── commanding.py        # Core command registration framework
│       ├── commands/            # Individual slash command handlers
│       ├── orchestrator.py      # Core AI game engine
│       ├── planner.py           # AI semantic router for /act
│       ├── rules/               # Deterministic game mechanics
│       └── ...                  # (config, db, models, repos, etc.)
└── tests/                       # Unit and integration tests
```

```
```