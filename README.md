# Adventorator

*The best adventures are the ones **no one** has to plan.*

A Discord-native Dungeon Master bot that runs tabletop RPG campaigns directly in chat. It blends deterministic game mechanics with AI-powered narration, letting players experience a text-based campaign without needing a human DM online 24/7.

![](/docs/images/usage-slash-check.jpeg)

---

* [Overview](#overview)
* [Prerequisites](#prerequisites) & [Quickstart](#quickstart)
* [Databases & Alembic](#database--alembic)
* [Repo Structure](#repo-structure)
* [Add & Test New Commands](#add--test-new-commands)
* [Contributing](./CONTRIBUTING.md)

---

## Overview

**✨ Features (MVP and beyond)**

* Discord-first gameplay
* Slash commands (/roll, /check, /sheet, /act) and interactive components (buttons, modals).
* Combat threads with initiative order, per-turn locks, and timeouts.
* Ephemeral prompts for individual player actions.
* Deterministic rules engine
* Full SRD 5e dice system (advantage/disadvantage, crits, modifiers).
* Ability checks, saving throws, AC, HP, conditions.
* Initiative and turn management with audit logging.
* Campaign persistence
* JSON-schema character sheets stored in Postgres (or SQLite for dev).
* Adventure content as structured "nodes" (locations, NPCs, encounters).
* Automatic transcripts and neutral session summaries.
* AI-assisted narration (behind feature flag)
* LLM proposes DCs and narrates outcomes; Rules Service enforces mechanics.
* Retrieval-augmented memory: previous sessions, adventure nodes, campaign facts.
* Configurable tone, verbosity, and house rules.
* Developer experience
* Python 3.10+, FastAPI interactions endpoint, Redis for locks/queues.
* Pydantic models, property-based tests for dice & checks.
* Structured JSON logs, reproducible seeds, feature flags for every subsystem.

**🏗 Architecture**

* Discord Interactions API → FastAPI app → defer in <3s → enqueue background job.
* Rules Service (pure Python functions) → resolves rolls, DCs, initiative, mutations.
* Database → campaign state, character sheets, transcripts.
* Optional LLM → narrates and proposes rulings, never mutates state directly.
* Workers → long-running tasks: narration, summarization, content ingestion.
 
**Diagram: High-Level Architecture**

```mermaid
flowchart TD
  %% === External ===
  subgraph EXTERNAL[External Systems]
    U[Player on Discord]:::ext
    DP[Discord Platform<br/>App Commands and Interactions]:::ext
    WH[Discord Webhooks API<br/>Follow-up Messages]:::ext
    LLM[LLM API<br/>e.g., Ollama]:::ext
  end

  %% === Network Edge ===
  CF[cloudflared Tunnel<br/>TLS - trusted CA]:::edge

  %% === App ===
  subgraph APP[Adventorator Service - FastAPI]
    subgraph REQUEST[Request Handling]
      A[Interactions Endpoint<br/>path: /interactions]
      SIG[Ed25519 Verify<br/>X-Signature-* headers]
      DISP[Command Dispatcher]
    end

    subgraph BUSINESS[Business Logic]
      RULES[Rules Engine<br/>Dice, Checks]
      CTX[Context Resolver<br/>Campaign, Player, Scene]
      LLMC[LLM Client<br/>Prompting & JSON Parsing]
      ORCH[Orchestrator<br/>Coordinates LLM + Rules]
    end

    subgraph RESPONSE[Response Handling]
      RESP[Responder<br/>defer and follow-up]
      TRANS[Transcript Logger]
    end
  end

  %% === Data ===
  subgraph DATA[Data Layer]
    DB[(Postgres or SQLite<br/>campaigns, players, characters, scenes, transcripts)]:::data
    MIG[Alembic Migrations]:::ops
  end

  %% === Tooling ===
  subgraph TOOLING[Tooling]
    REG[scripts/register_commands.py<br/>Guild command registration]:::ops
    LOG[Structured Logs<br/>structlog and orjson]:::ops
    TEST[Tests<br/>pytest and hypothesis]:::ops
  end

  %% === Ingress Flow ===
  U -->|Slash command| DP
  DP -->|POST /interactions<br/>signed| CF
  CF --> A
  A --> SIG
  SIG -->|valid| DISP
  A -.->|invalid| RESP

  %% Phase 0: immediate defer
  DISP -->|defer| RESP

  %% === Command-Specific Flows ===
  DISP -- "/roll" --> RULES
  RULES --> RESP

  DISP -- "/sheet" --> CTX
  CTX -->|reads| DB
  CTX --> RESP

  DISP -- "/ooc: read history" --> DB
  DISP -- "/ooc: call LLM" --> LLMC
  LLMC --> LLM
  LLMC -- "respond" --> RESP

  DISP -- "/narrate" --> ORCH
  ORCH -- "get facts" --> DB
  ORCH -- "get proposal" --> LLMC
  ORCH -- "run rules" --> RULES
  ORCH -- "respond" --> RESP

  %% === Egress & Logging (for all command flows) ===
  RESP -- "log event" --> TRANS
  TRANS -->|write| DB
  RESP -->|POST follow-up| WH
  WH --> DP --> U

  %% === Tooling Edges ===
  REG --> DP
  MIG --> DB
  TEST -.-> RULES & ORCH & A
  LOG -.-> APP

  %% === Styles ===
  classDef ext  fill:#eef7ff,stroke:#4e89ff,stroke-width:1px,color:#0d2b6b
  classDef edge fill:#efeaff,stroke:#8b5cf6,stroke-width:1px,color:#2b1b6b
  classDef data fill:#fff7e6,stroke:#f59e0b,stroke-width:1px,color:#7c3e00
  classDef ops  fill:#eefaf0,stroke:#10b981,stroke-width:1px,color:#065f46
```

**Diagram: Narrate Command Flow**

```mermaid
sequenceDiagram
  autonumber
  participant User as Player (Discord)
  participant Discord as Discord Platform
  participant API as Adventorator Service
  participant ORCH as Orchestrator
  participant DB as Database
  participant LLM as LLM API
  participant RULES as Rules Engine
  participant WH as Discord Webhooks

  User->>Discord: /narrate message:"I try to pick the lock"
  Discord->>API: POST /interactions (signed)
  
  Note over API: Verifies Ed25519 signature

  API-->>Discord: ACK with Defer (type=5) in < 3s

  par Background Processing
    API->>API: Dispatches "narrate" command
    
    API->>DB: write_transcript("player", "I try to pick the lock")

    API->>ORCH: run_orchestrator(scene_id, player_msg)
    
    activate ORCH
      ORCH->>DB: get_recent_transcripts(scene_id)
      DB-->>ORCH: Return transcript history
      
      Note over ORCH: Builds facts prompt from history
      
      ORCH->>LLM: generate_json(prompt)
      LLM-->>ORCH: Return JSON proposal (action, ability, dc, narration)
      
      Note over ORCH: Validates proposal
      
      ORCH->>RULES: compute_check(DEX, dc=15, ...)
      RULES-->>ORCH: Return CheckResult (success, total, rolls)
    deactivate ORCH
    
    ORCH-->>API: Return OrchestratorResult
    
    Note over API: Formats mechanics and narration for response
    
    API->>WH: POST follow-up message
    WH-->>Discord: Delivers message
    Discord-->>User: Shows formatted mechanics + narration
    
    API->>DB: write_transcript("bot", narration, meta={mechanics})
  end
```

**`/ooc` command flow**

```mermaid
sequenceDiagram
  autonumber
  participant User as Player (Discord)
  participant Discord as Discord Platform
  participant API as Adventorator Service
  participant DB as Database
  participant LLM as LLM API
  participant WH as Discord Webhooks

  User->>Discord: /ooc message:"What does the room smell like?"
  Discord->>API: POST /interactions (signed)
  
  Note over API: Verifies Ed25519 signature

  API-->>Discord: ACK with Defer (type=5) in < 3s

  par Background Processing
    API->>API: Dispatches "ooc" command
    
    Note over API: Resolves campaign, scene, player context
    
    API->>DB: write_transcript(author="player", content="What...")
    
    API->>DB: get_recent_transcripts(scene_id)
    DB-->>API: Return transcript history
    
    Note over API: Formats chat history into prompt for LLM
    
    API->>LLM: generate_response(prompt)
    LLM-->>API: Return full text response (potentially long)
    
    Note over API: Prepares attribution & splits response into chunks (max 2000 chars)
    
    loop For Each Chunk
      API->>WH: POST follow-up(chunk)
      WH-->>Discord: Delivers chunked message part
      Discord-->>User: Shows chunk
    end
    
    Note over API: After sending all chunks, logs the full original response
    API->>DB: write_transcript(author="bot", content="<full llm response>")
  end
```



**🔒 Design philosophy**

* AI narrates, rules engine rules. No silent HP drops or fudged rolls.
* Human-in-the-loop. GM override commands (/gm) and rewind via event sourcing.
* Defensive defaults. Feature flags, degraded modes (rules-only if LLM/vector DB down).
* Reproducible. Seeded RNG, append-only logs, golden transcripts for regression tests.

**🚧 Status**

* [X] Phase 0: Verified interactions endpoint, 3s deferral, logging.
* [X] Phase 1: Deterministic dice + checks, /roll and /check commands.
* [X] Phase 2: Persistence (campaigns, characters, transcripts).
* [ ] Phase 3: Shadow LLM narrator, proposal-only.
* [ ] Phase 4+: Combat system, content ingestion, GM controls, premium polish.

**🔜 Roadmap**

* Add /sheet CRUD with strict JSON schema.
* Initiative + combat encounters with Redis turn locks.
* Adventure ingestion pipeline for SRD or custom campaigns.
* Optional Embedded App for lightweight maps/handouts in voice channels.

---

## Prerequisites

- Bash-like environment
- Docker
- Python > 3.10
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)

    ```bash
    # Linux
    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
    sudo cp ./cloudflared-linux-arm /usr/local/bin/cloudflared
    sudo chmod +x /usr/local/bin/cloudflared
    cloudflared -v

    # MacOS
    brew install cloudflared
    ```

## Quickstart

```bash
cp .env.example .env    # <-- Add secrets
make dev                # Install Python requirements
make run                # Start local dev server on 18000
```

### Optional: Anonymous Cloudflare tunnel:

```bash
make tunnel
```

In the output, you should see something like:

    ```
    2025-09-05T18:57:54Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
    2025-09-05T18:57:54Z INF |  https://rooms-mechanics-tires-mats.trycloudflare.com  
    ---

Discord can now reach your dev server using that URL + `/interactions`.

---

## Database & Alembic

Adventorator uses SQLAlchemy with Alembic migrations. You’ll need to initialize your database schema before running commands that hit persistence (Phase 2+).

```bash
# Create the database (SQLite default, Postgres if DATABASE_URL is set)
alembic upgrade head
```

This will apply all migrations in `migrations/versions/` to your database.

Common commands:

```bash
# Generate a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"

# Apply latest migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

By default, `alembic.ini` points at your `DATABASE_URL` (set in `.env` or config).
For quick local dev you can rely on SQLite (`sqlite+aiosqlite:///./adventurator.sqlite3`), but Postgres is recommended for persistent campaigns.

---

That way, someone can go from `make dev` → `alembic upgrade head` → bot commands writing to DB.

---

## Repo Structure

```
.
├── alembic.ini                  # Alembic config for database migrations
├── config.toml                  # Project-level config (env, feature flags, etc.)
├── Dockerfile                   # Container build recipe
├── docs                         # Documentation assets and guides
├── Makefile                     # Common dev/test/build commands
├── migrations                   # Alembic migration scripts
│   ├── env.py                   # Alembic environment setup
│   └── versions                 # Generated migration files
├── pyproject.toml               # Build system and tooling config (ruff, pytest, etc.)
├── README.md                    # Project overview and usage guide
├── requirements.txt             # Python dependencies lock list
├── scripts                      # Utility/CLI scripts
│   ├── aicat.py                 # Quickly cat combined source files for copying to clipboard
│   └── register_commands.py     # Registers slash commands with Discord API
├── src                          # Application source code
│   └── Adventorator             # Main package
│       ├── app.py               # FastAPI entrypoint + Discord interactions handler
│       ├── config.py            # Settings loader (TOML + .env via Pydantic)
│       ├── crypto.py            # Ed25519 signature verification for Discord
│       ├── db.py                # Async SQLAlchemy engine/session management
│       ├── discord_schemas.py   # Pydantic models for Discord interaction payloads
│       ├── logging.py           # Structlog-based logging setup
│       ├── models.py            # SQLAlchemy ORM models (Campaign, Player, etc.)
│       ├── repos.py             # Data access helpers (CRUD, queries, upserts)
│       ├── responder.py         # Helpers for Discord responses and follow-ups
│       ├── rules                # Deterministic rules engine (dice, checks)
│       │   ├── checks.py        # Ability check logic & modifiers
│       │   └── dice.py          # Dice expression parser and roller
│       └── schemas.py           # Pydantic schemas (e.g., CharacterSheet)
└── tests                        # Unit and integration tests
    ├── conftest.py              # Pytest fixtures (async DB session, etc.)
    └── data                     # Sample payloads/test data
```

---

## Add & Test New Commands

Adventorator exposes a tiny command framework. You declare commands with a decorator and a Pydantic options model; everything else (server dispatch, CLI, and Discord registration) auto-discovers them.

1) Implement the command

- Create a new file under `src/Adventorator/commands/`, e.g. `greet.py`:

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

- Subcommands: register multiple handlers under a single top-level name using `subcommand`:

  ```python
  @slash_command(name="npc", subcommand="add", description="Add an NPC", option_model=AddNPCOpts)
  async def npc_add(inv: Invocation, opts: AddNPCOpts):
      ...

  @slash_command(name="npc", subcommand="show", description="Show an NPC", option_model=ShowNPCOpts)
  async def npc_show(inv: Invocation, opts: ShowNPCOpts):
      ...
  ```

Guidelines:
- Use `Option` subclasses to define inputs with `Field(description=...)` to populate help text and Discord option descriptions.
- For DB access, always use `async with session_scope()` and helpers in `repos.py`. Avoid inline SQL.
- Write transcripts for meaningful player/bot messages (see existing commands for patterns).
- If you need the LLM narrator, follow `ooc_do.py` and gate behavior behind feature flags.

2) Discovery: no wiring needed

- The app and tools auto-load `Adventorator.commands` on startup or invocation. Just add the file and export the handler.

3) Local smoke test via dynamic CLI

- The dynamic CLI mirrors the same handlers; it also supports grouped subcommands.
- Single required string field (with no alias) becomes a positional arg for friendlier UX.

  ```bash
  # Show available commands
  PYTHONPATH=./src python scripts/cli.py --help

  # Top-level command
  PYTHONPATH=./src python scripts/cli.py greet Alice

  # Subcommand
  PYTHONPATH=./src python scripts/cli.py npc show --name Bob
  ```

4) Register slash commands with Discord

- Fill out `.env` with `DISCORD_APPLICATION_ID`, `DISCORD_BOT_TOKEN`, and (for faster iteration) `DISCORD_GUILD_ID`.
- Then run:

  ```bash
  python scripts/register_commands.py
  ```

5) Run the server (and optional tunnel)

```bash
make dev
make run        # starts FastAPI on :18000
# optional (for Discord to reach you):
make tunnel
```

6) Quality gates

```bash
make format
make lint
make type
make test
```

7) Minimal unit test example

```python
# tests/test_greet_command.py
import asyncio
from Adventorator.commanding import Invocation
from Adventorator.commands.greet import GreetOpts, greet

class CaptureResponder:
    def __init__(self):
        self.messages = []
    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.messages.append((content, ephemeral))

def test_greet_says_hello():
    resp = CaptureResponder()
    inv = Invocation(
        name="greet", subcommand=None, options={"name":"Alice"},
        user_id="1", channel_id="1", guild_id="1", responder=resp,
    )
    opts = GreetOpts.model_validate({"name": "Alice"})
    asyncio.run(greet(inv, opts))
    assert resp.messages[0][0] == "Hello, Alice!"
```

Notes
- Option names map to CLI flags using kebab-case; if you declare a `Field(alias="json")`, the CLI flag will be `--json`.
- For LLM-dependent commands, if `features.llm` is disabled in `config.toml`, the handlers will respond in a safe degraded mode.
- Handlers can access server context via `Invocation`: `inv.settings` and `inv.llm_client` are provided in the FastAPI runtime; when running via the local CLI they are `None`. Gate LLM behavior behind feature flags and handle `None` safely (see `ooc_do.py`).
