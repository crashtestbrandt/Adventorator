## Technical and architectural review

### High-level architecture
- Entrypoint and transport
  - FastAPI app in app.py exposes `/interactions`, verifies Ed25519 signatures, immediately defers (type 5), and dispatches commands in the background. Health and metrics endpoints present.
  - Context propagation via structlog contextvars; request header override for webhook base is plumbed via a ContextVar (dev-friendly).

- Command system
  - Transport-agnostic “command” layer (commanding.py) with:
    - `Invocation` (command context), `Responder` protocol (abstracts Discord follow-up), and `Option` models (Pydantic v2).
    - Global command registry with `@slash_command` decorator and a loader (command_loader.py).
  - Commands live under commands (roll, check, do, ooc, plan, confirm/cancel/pending, sheet).
  - Strong option validation (Pydantic) before handler dispatch; ephemeral error on validation failure.

- Rules engine
  - Encapsulated as a `Dnd5eRuleset` in engine.py wrapping deterministic dice.py and checks.py.
  - Provides a thin but growing API: dice rolls, checks, initiative, attack/damage helpers, and simple HP math.

- LLM stack
  - Planner: catalogs commands and option schemas, prompts LLM, validates with `PlannerOutput` (planner.py, planner_schemas.py).
  - Orchestrator: converts transcripts to facts, runs “narrator” LLM, validates proposal (“ability_check” only), applies defenses (banned verbs, unknown actors), and computes mechanics via rules or via Executor dry-run when enabled (orchestrator.py).
  - JSON extraction/validation helpers in llm_utils.py; prompts in `llm_prompts.py`.
  - Feature flags control visibility and fallback behavior.

- Executor and tool registry (preview-first)
  - Executor and `ToolCallChain` contracts implemented; orchestrator can wrap proposals and call `execute_chain(..., dry_run=True)` for previews.
  - Feature flags: `features.executor`, `features.executor_confirm`, `features.events`, etc.

- Persistence and repos
  - SQLAlchemy models in models.py include campaigns, players, characters, scenes, transcripts; Phase 8/9: `PendingAction`, `Event`.
  - Alembic present; `repos.py` provides DB helpers; `session_scope()` centralizes async session lifecycle.
  - Content ingestion surface for Phase 6 present (`ContentNode`), plus retrieval with a SQL fallback retriever.

- Discord responder
  - responder.py sends follow-ups to Discord or to an override sink during dev.

- Observability and resilience
  - Structured logging via structlog with request_id middleware; counters in `metrics.py`; `/metrics` gateable by setting.
  - Planner and orchestrator include small in-memory caches (30s) to suppress duplicate LLM calls.

- Tooling and ops
  - Makefile targets (dev/run/test/lint/type/format/db/alembic), Dockerfile and docker-compose present, plus scripts for local tasks and command registration.

### Code quality and tests
- Tests: 84 passed in ~3.5s on macOS (Python 3.13). Overall coverage ~78% (many critical paths 85–100%).
- Lint: Ruff passes.
- Types: mypy passes.

Hotspots with lower coverage (good next targets):
- `commands/do.py` (~53%), `services/character_service.py` (~45%), `commands/pending.py` (25%), `commands/sheet.py` (40%), `executor.py` (74%).

### Design strengths
- Clean layering: transport → command routing → domain services (rules, planner/orchestrator/executor) → repos.
- Defensive LLM integration: strict schemas, allowlists, guardrails (verbs, unknown actors), caching, feature flags.
- Extensible rules encapsulation via `Ruleset` and `Dnd5eRuleset`.
- Event-sourced foundation (events + folds) and pending action confirmation loop are in place and tested.
- Deterministic dice and checks with seedable RNG.

### Notable risks and improvements
- RNG scoping: global `DiceRNG()` in app.py; better to seed per-scene/request in invocations to ensure determinism and reproducibility.
- ContextVar header override: dev-only behavior is good, but ensure it’s strictly gated by env and never active in prod (appears so; keep tests).
- Executor tool surface: rules exist for attack/damage; the executor lacks fully wired combat tools (Phase 11 ahead).
- Character context: `check` command partially defaults from a character, but deeper orchestrator context-loading is a Phase 5 goal and is only partially realized.
- Concurrency: background `create_task` dispatch is appropriate post-defer; ensure centralized error handling and backpressure if command fan-in grows.
- Coverage gaps: pending/sheet flows and deeper orchestration paths should gain tests before expanding features.

## Progress against MVP phases

Summary status based on code + tests + plan:

- Phase 0 — Project skeleton & safety rails: Done
  - Ed25519 verification, defer, pong, structured logs, metrics hooks, make tunnel/dev harness patterns. Tests cover interactions defer and ping.

- Phase 1 — Deterministic core (dice & checks): Done
  - `rules.dice` and `rules.checks` are deterministic; distribution/edge tests exist; slash commands `/roll` and `/check` implemented.

- Phase 2 — Persistence & Session Plumbing: Done
  - Models, Alembic, CRUD and transcripts; scene orchestration tied to channels; tests run on SQLite; Postgres config and docker-compose exist.

- Phase 3 — LLM “narrator” (shadow mode): Done
  - Orchestrator produces proposals, validates, computes mechanics, and formats narration; prompt-injection defenses present; feature flags for LLM fallback.

- Phase 4 — Planner and `/act`: Done
  - Planner contracts, tool catalog from command registry, `/act` integration, allowlist, caching, telemetry, soft timeouts, robust testing.

- Phase 5 — Solidify foundation & deepen narrative AI: Done (Phase 4.5 objectives)
  - Postgres primary path, containerization, improved orchestrator context hooks, rules encapsulation class exists, beginnings of character-sheet awareness. Some subitems (auto-load in more commands) are partial but gated by tests and flags.

- Phase 6 — Content ingestion & retrieval: Done
  - Content models, retrieval fallback, tests for retrieval metrics and SQL fallback; prompt assembly includes retrieved snippets while preventing GM-only leakage (tests present).

- Phase 7 — Executor (dry-run only): Done
  - Contracts implemented; orchestrator integrates preview path under FF; unit/integration tests present.

- Phase 8 — Pending actions & confirmation: Done
  - `PendingAction` model, repos, confirm/cancel commands, dedup hash/idempotency, TTL expiry, metrics hooks, and integration tests.

- Phase 9 — Event-sourced mutations: Done
  - Event ledger model, append/list helpers, predicted events in dry-run, replay/fold helpers and tests, initial hooks from `roll`/`check`.

- Phase 10 — Encounter & turn engine (foundations): In progress/not delivered
  - Scene has `mode` but no `Encounter`/`Combatant` models or lock orchestration yet. No concurrency tests for turn sequencing.

- Phase 11 — Minimal combat actions: Not delivered (partially prepared)
  - Rules helpers exist (attack/damage), but executor tool handlers for attack/damage, orchestrator wiring, and end-to-end confirm/apply aren’t present.

- Phase 12 — Map rendering MVP: Not delivered
  - No renderer module or `/map show` command yet.

- Phase 13 — Modal scenes (Exploration ↔ Combat): Partially scaffolded
  - `Scene.mode` exists; no branching/merge tools or enforcement in orchestrator.

- Phase 14 — Campaign & character ingestion with preview-confirm: Not delivered
  - Content pipeline exists from Phase 6; no preview/confirm ingestion flows or GM-only commands found.

- Phase 15 — GM controls, overrides, safety: Not delivered
  - No GM-only toolset or rewind implementation yet.

- Phase 16 — Hardening and ops: Partially delivered
  - Many resilience primitives and FFs exist (rules-only, executor toggles). Additional SLOs, rate limiting, circuit breakers, and degraded-mode flow control remain open.

## Recommendations and next steps

Short term (to unlock Phase 10–12):
- Encounter/turn foundations
  - Add models `Encounter` and `Combatant`; implement advisory locks and asyncio locks as specified; write minimal `start_encounter`, `add_combatant`, `set_initiative`, `next_turn`, `end_encounter` tool handlers in the executor.
  - Add concurrency tests to guarantee single-winner `next_turn`.

- Wire combat preview flows
  - Extend orchestrator to wrap planner suggestions (or explicit `/act`) into multi-step `ToolCallChain` for attack/damage previews; keep `features.combat=false` default.

- RNG scoping
  - Replace global `DiceRNG()` with per-invocation/scene RNG seeded from scene or request to improve determinism and testability.

- Character context
  - Promote `CharacterService` usage broadly:
    - Ensure `/do` and orchestrator sheet_info_provider load active character, not just check defaults.
    - Include character summary consistently in narrator prompts.

- Test coverage
  - Add unit/integration tests for `commands/do.py`, `services/character_service.py`, pending/sheet flows, and executor branches.
  - Golden-log for sample previews to stabilize output expectations.

Medium term (to progress Phase 11–14):
- Combat actions tooling
  - Implement executor tools for `attack`, `apply_damage`, `apply_condition`, with events in both preview and apply; orchestrator formats concise mechanics block.

- Map renderer MVP
  - Pure Python Pillow renderer with snapshot tests; attach PNG in follow-up; gate via `features.map`.

- Modal scenes and branching
  - Add `branch_scene`, `merge_scenes` tools; orchestrator enforces action targeting; tests for merge correctness.

- Ingestion with preview-confirm
  - Add `/sheet import` and `/campaign upload` with strict validators and preview diffs; execute via executor with `requires_confirmation`.

Hardening and ops
- Add rate limiting (per user/channel) and idempotency keys at interaction boundary; add circuit-breakers for LLM/retriever with degraded modes.
- Define minimal SLOs and metrics panels (executor preview/apply duration, lock wait metrics, planner cache hit ratio).
- Ensure the header override path is strictly disabled outside dev; add an automated test.

## Quality gates snapshot
- Build/Tests: PASS (84 tests, ~3.5s)
- Lint: PASS (ruff)
- Type check: PASS (mypy)
- Coverage: 78% overall; several critical modules ≥85%; specific gaps noted above.

## Requirements coverage
- Comprehensive technical/architectural review: Done (architecture, quality, risks, and recommendations).
- Assess progress against MVP phases: Done (per-phase status aligned to implementation_plan.md).