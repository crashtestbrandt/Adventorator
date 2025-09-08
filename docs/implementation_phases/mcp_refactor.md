# MCP Refactor Plan

This document tracks the incremental steps to expose Adventorator via MCP while keeping
the existing Discord integration intact.

## Goals
- Isolate pure tool handlers that wrap the existing rules and orchestrator.
- Provide an MCP adapter with minimal new dependencies.
- Keep tests green throughout; add unit tests for tool handlers.

## Phase 1 (done here)
- Add `adapters/mcp/` package with a framework-agnostic `roll_dice` tool.
- Provide an optional `server.py` that wires the tool into an MCP server (lazy import).
- Add unit tests for the tool handler.

## Next steps
- Add `compute_check` tool mapping to `rules/checks.py`.
- Extract orchestrator dependency seams (LLM client, repos, cache) behind simple interfaces.
- Add `orchestrate_action` tool that calls the orchestrator with those dependencies.
- Add resource readers for transcripts and streams for orchestrator/metrics events.

See `.github/copilot-instructions.md` for architectural constraints and testing patterns.
# MCP Refactor

crashtestbrandt: Perform a complete review of the project's architecture. Then, talk to me about refactoring for MCP.

GitHub Copilot: Here’s a focused review of the current architecture and a concrete path to 

## Architecture review

What you’ve built (from the provided repo and guidance):
- Ingress/adapter
  - FastAPI app (`app.py`) handles Discord `POST /interactions`.
  - Ed25519 signature verification (`crypto.verify_ed25519`).
  - Acknowledge within 3s via `responder.respond_deferred()`, do work in background, then follow-up via webhook (`responder.followup_message()`).
  - Command routing via `commanding.py` and registry-driven loaders under `commands/`.
- Core application logic
  - Orchestrator (`orchestrator.run_orchestrator`) coordinates:
    - Scene + facts → LLM proposal (JSON) → strict parsing/gating → rules → output formatting.
    - Safety gates: action whitelists, DC bounds, reason non-empty, verb blacklist, actor validation via `allowed_actors`.
    - Caching (30s) to dedupe prompts.
    - Visibility behind feature flags (`features.llm`, `features.llm_visible`).
  - Rules engine (`rules/dice.py`, `rules/checks.py`) deterministic and testable; `DiceRNG.roll` supports adv/dis on single d20.
- Data access
  - Async SQLAlchemy with `session_scope()` in `db.py`.
  - ORM models in `models.py`; higher-level helpers in `repos.py` return plain data.
- LLM integration
  - Client wrapper in `llm.py`, strict JSON parsing in `llm_utils.py` + schemas in `schemas.py`.
  - Prompts in `llm_prompts.py`.
- Telemetry/ops
  - Minimal counters in `metrics.py`.
  - Config via `config.load_settings()`, feature flags in config.toml.
- Testing
  - Good coverage across rules, orchestrator, LLM JSON handling, metrics, and end-to-end interaction flow.
  - Async tests via `pytest-asyncio`, RNG seeding in rules tests, and monkeypatch guidance followed.

Strengths
- Clean IO boundaries: Discord adapter defers quickly and does the heavy work in background tasks.
- Deterministic rules with seeds make it robust and testable.
- LLM proposal is strictly parsed and gated for safety—great for reliability.
- Registry-based command routing keeps adding commands easy.
- Caching, metrics, feature flags, and good test coverage show production-minded design.

Risks / opportunities
- Adapters vs. core: while responder/routing are decoupled, the core engine and adapters could be teased apart more explicitly to support additional ingress (e.g., MCP) without touching Discord-specific code.
- Interfaces: define thin interfaces for LLM client, RNG, repos, and outbound messaging. This will simplify swapping adapters (Discord vs. MCP) and improve testing seams.
- Idempotency: ensure follow-up operations are idempotent (e.g., dedupe keys by interaction id + step) to avoid double posts under retries.
- Structured logging: make logs uniform, contextual (scene_id, interaction_id, request_id), and JSON-formatted for easier analysis.
- Timeouts/retries: centralize and enforce timeouts on LLM and downstream operations with jittered retries; expose them in settings.
- Validation: schemas are solid; consider richer enums/typing for DCs, advantage/disadvantage, and actor IDs to prevent drift at boundaries.
- Caching: duplicate suppression is good; consider cache scope and keys for MCP reentrancy (more below).
- Observability: metrics are minimal; add counters/histograms for LLM latency, acceptance rate, rule failures, parse failures, and orchestration steps.

Quick wins
- Define interfaces/protocols: LLMClient, RNG, Repos, Outbox (message sender), Clock, Cache.
- Extract a “core engine” package with pure functions (or thin stateful orchestrator service) that takes these interfaces as inputs.
- Add request-scoped context (request/trace id, actor ids) and pass consistently through orchestrator and repos for logs/metrics.

## Refactoring for MCP

Goal
- Keep the Discord adapter intact.
- Expose the “core engine” via an MCP server so AI clients can invoke tools and subscribe to resources/streams.
- Minimize churn by isolating Discord-specific concerns and plugging a new MCP adapter.

MCP recap (for planning)
- Tools: RPC-like functions with JSON params/returns.
- Resources: listable addressable items you can read (and sometimes write).
- Streams/Events: server-initiated pushes (e.g., logs, metrics, status).
- Sessions are stateless; keep state in your DB/cache, not in the session.

Proposed module layout (incremental, not a big-bang)
- src/Adventorator/
  - domain/          ← pure logic and types
    - rules/ (move existing `rules/`)
    - schemas.py (or split into domain_schemas.py if needed)
  - app/             ← orchestration and services (no HTTP/Discord)
    - orchestrator.py (move here), service factories, interfaces (LLMClient, Repos, RNG, Outbox, Clock, Cache)
  - infra/           ← adapters for infra concerns
    - db.py, models.py, repos.py
    - llm.py, llm_utils.py, llm_prompts.py
    - metrics.py, logging.py, config.py
    - cache.py (optional thin wrapper; current in-process cache logic can move here)
  - adapters/
    - discord/       ← current FastAPI app, responder, command registry
      - app.py, responder.py, commanding.py, command_loader.py, commands/*
    - mcp/           ← new MCP server exposing tools/resources/streams

MCP tools (initial set)
- roll_dice
  - Input: { formula: "XdY+Z", advantage?: bool, disadvantage?: bool, seed?: int }
  - Output: { rolls: number[], total: number, crit: "none" | "crit" | "fumble" }
- compute_check
  - Input: { check: CheckInput, d20_rolls?: number[], seed?: int }
  - Output: CheckResult (as currently returned by rules/checks)
- orchestrate_action
  - Input: { scene_id: string, player_msg: string, allowed_actors?: string[], rng_seed?: int, options?: { prompt_token_cap?: int, visibility?: "shadow" | "public" } }
  - Output: { narration: string, gates: { accepted: boolean, reasons?: string[] }, metrics: { tokens_in, tokens_out, latency_ms }, artifacts?: { proposal, rule_eval } }
- list_characters
  - Output: { characters: string[] }
- append_transcript
  - Input: { scene_id: string, author: string, message: string, ooc?: boolean }
  - Output: { ok: boolean, message_id: string, timestamp: string }

MCP resources
- resource: transcript://scene/{scene_id}
  - Read: returns last N messages with authors and timestamps
  - List: lists scenes with latest message info
- resource: scene://{scene_id}
  - Read: current scene state (high-level facts used by orchestrator)
- resource: metrics://counters
  - Read: { metric: value } map; optionally filtered by prefix

Streams
- stream: events://orchestrator
  - Emits: { scene_id, type: "llm.enqueued" | "llm.received" | "defense.rejected" | "format.sent", ts, extra }
- stream: logs://app
  - Emits structured logs with level, module, correlation ids

Key refactor steps (phased, test-first)

Phase 1: Extract core interfaces and stabilize orchestrator seams
- Introduce protocols (typing.Protocol or ABCs):
  - LLMClient: generate_json(prompt, schema, caps) -> dict
  - Repos: list_character_names(), transcripts IO, scene facts retrieval
  - RNG: roll(), maybe seed-scoped instance factory
  - Outbox: send(content, ephemeral?: bool) — used only in adapters
  - Cache: get/set by key+ttl
- Move `orchestrator.py` to app/ and make it accept dependencies via constructor or function params. Keep behavior exactly the same; adjust imports in tests. Run tests.

Phase 2: MCP server skeleton with one tool
- Create `adapters/mcp/server.py` using the Python MCP SDK.
- Wire a single tool: roll_dice -> calls domain.rules.dice.
- Add tests for MCP handler shapes (unit-level; no network calls). Keep Discord unchanged.

Phase 3: Add compute_check, then orchestrate_action
- Add compute_check tool calling rules/checks.
- Add orchestrate_action tool that invokes `app.orchestrator.run_orchestrator` with dependencies created from infra factories (repos, llm, cache).
- Gate visibility via settings equivalent; default to shadow mode for MCP unless configured.

Phase 4: Resources and streams
- Add transcript resource read/list via repos.
- Add orchestrator/metrics streams. Reuse `metrics.py` and forward key events.

Phase 5: Consolidate adapters and config
- Introduce a single settings module that both adapters read from (Discord and MCP).
- Ensure logging and metrics are unified (same context fields and format).

Phase 6: Hardening
- Idempotency and dedupe keys for orchestrate_action (scene_id + normalized player_msg).
- Timeout/retry policies for LLM and repos.
- Access control for MCP (tokens or allowlist), plus per-tool rate limits.

Notes on minimal churn
- Keep package names and public APIs stable; move files gradually with import shims if needed.
- Tests first for each extraction (start by moving tests’ import targets, then move code).
- Avoid touching Discord code except to point to the new orchestrator location and interfaces.

Tiny “contracts” for MCP tools (inputs/outputs, error modes)
- All tools return { ok: true, data: ... } or throw standardized MCP tool errors with code and message.
- Common errors: invalid_input (schema), not_found (scene/character), rate_limited, timeout, internal_error.
- Success criteria: deterministic for seeded inputs; otherwise trace ids for correlation.

Testing strategy
- Unit tests: tool handlers with fakes for repos/llm/rng/cache.
- Integration-like: run server in-process and call handlers directly (SDK allows handler invocation without transport).
- Property tests for dice and checks (aleatory coverage).
- Snapshot tests for orchestrate_action formatting (stable under seeded RNG and fixed LLM stub).

Open questions to align
- MCP client(s) you intend to support first? This influences auth and response shaping.
- Resource write operations: should transcript writes be tools (preferred) or resource mutations?
- Do we want a separate cache namespace for MCP to avoid cross-adapter collisions?

Suggested follow-ups (small, high-value)
- Add JSON structured logging (include interaction_id, scene_id, tool_name).
- Expand metrics with latency histograms and acceptance rates.
- Introduce a thin Outbox interface in adapters to unify Discord follow-ups and future channels.