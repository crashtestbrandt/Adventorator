# (Deprecated) Implementation Plan — Phase Descriptions

> NOTE: This file is retained as a historical snapshot generated from GitHub issues. The authoritative forward-looking roadmap now lives at `ROOT/ROADMAP.md`.
>
> Active epics and their current statuses: see `docs/implementation/epics/` and the roadmap. Update statuses in the roadmap (not here) when work advances.

This document aggregates the previously defined “Phase N” issues from GitHub with their full descriptions for historical reference. Each section links back to the original issue.

## Phase 0 — Project skeleton & safety rails (no gameplay) ([#15](https://github.com/crashtestbrandt/Adventorator/issues/15)) — status: closed

**Goal:** A minimal, secure Discord Interactions handler with observability.

**Deliverables**
* Interactions endpoint (FastAPI/Express) that:
 * Verifies Ed25519 signatures
 * Immediately defer replies
 * Sends a trivial follow-up (“pong”)
 * Secrets via env; config via config.toml with feature flags (e.g., ff.rules=false, ff.llm=false)
* Logging/metrics:
 * Structured logs with correlation IDs per interaction
 * Basic metrics: ack latency, follow-up latency, error rate
 * CI: lint, tests, container build
 * Dev harness: make tunnel (ngrok/Cloudflare) and a tiny “fake Discord” payload replayer

**Exit criteria**
* ≥99% acks under 1.5s locally
* Replay tool can re-inject a captured interaction and produce the same output (idempotency).

**Rollback**
* Only this phase is active; revert to stub reply if anything fails.

---

## Phase 1 — Deterministic core (dice & checks), no LLM ([#16](https://github.com/crashtestbrandt/Adventorator/issues/16)) — status: closed

**Goal:** Useful bot with /roll and basic ability checks—pure rules, no AI.

**Deliverables**
* Rules Service v0 (library + HTTP tool endpoints):
  * Dice parser XdY+Z, adv/dis, crits; seedable RNG; audit log
  * Ability checks (proficiency, expertise), DC comparison
  * Slash commands: /roll, /check ability:<STR…> adv:<bool> dc:<int?>
* Unit & property tests (e.g., distribution tests for d20)

**Exit criteria**
* 100% deterministic from seed; property tests pass; audit log shows inputs/outputs.

**Rollback**
* Flip ff.rules=false → commands respond with an explanatory stub.

---

## Phase 2: Persistence & Session Plumbing ([#8](https://github.com/crashtestbrandt/Adventorator/issues/8)) — status: closed

**Goal:** Store characters/campaigns; keep transcripts; structure for later context.

**Deliverables**

* Postgres (or SQLite to start) schemas: campaigns, players, characters(jsonb), scenes, turns, transcripts
* Character CRUD: /sheet create|show|update
* Transcript writer: every bot I/O saved; golden log fixture for tests
* Thread orchestration: scene_id = channel_or_thread_id

**Exit criteria**

 * DB up via Docker; alembic upgrade head succeeds.
 * On any interaction, bot:
 * Verifies signature
 * Defers immediately
 * Resolves {campaign, player, scene} and logs a player transcript
 * /sheet create validates JSON via Pydantic and upserts to characters.
 * /sheet show fetches by name and returns a compact summary (ephemeral).
 * Bot writes a system transcript for sheet operations.
 * Tests pass on SQLite; app runs against Postgres.
 * Restart-safe: kill the app, restart, run /sheet show—the sheet persists.

**Rollback**

* If DB fails, commands degrade to ephemeral error without crashing the process.

---

## Phase 3 — LLM “narrator” in shadow mode ([#9](https://github.com/crashtestbrandt/Adventorator/issues/9)) — status: closed

**Goal:** Introduce the model without letting it change state.

**Deliverables**

* LLM client with JSON/tool calling: tools registered but disabled from mutating
* Clerk prompt (low temperature) for extracting key facts from transcripts
* Narrator prompt (moderate temperature) that proposes DCs and describes outcomes, but outputs:

  ```json
  {
    "proposal": {
      "action": "ability_check",
      "ability": "DEX",
      "suggested_dc": 15,
      "reason": "well-made lock"
    },
      "narration": "..."
  }
  ```

* Orchestrator compares proposal to Rules Service v0 and posts:
  * Mechanics block (actual roll, DC, pass/fail)
  * Narration text
* Prompt-injection defenses: tool whitelist, max tokens, strip system role leakage, reject proposals that reference unknown actors or fields

**Exit criteria**

* Shadow logs show ≥90% proposals sensible (manual spot-check)
* No unauthorized state mutations possible (unit tests enforce)

**Rollback**

* ff.llm=false returns rules-only responses.

---

## Phase 4 — Planner Layer and `/act` Command ([#56](https://github.com/crashtestbrandt/Adventorator/issues/56)) — status: closed

Introduce an **LLM-driven planner** that can translate freeform user input into valid Adventorator commands. The implementation is incremental and defensive, with strong validation and rollback options.

**Key steps:**

* **Groundwork fixes:** clean up small issues (OpenAI client response path, Pydantic API changes, timezone-aware timestamps, safe Pydantic defaults) to reduce noise during rollout.
* **Planner contract:** define strict Pydantic model (`Plan`) (legacy `PlannerOutput` now wrapped; retained only for backward-compatible adapter) and a system prompt that forces the LLM to output JSON with a single command and validated arguments.
* **Tool catalog:** auto-generate a schema catalog from the command registry (`all_commands()`), ensuring the planner cannot invent unknown shapes.
* **Planner service:** implement a `plan()` helper that builds prompts, invokes the LLM, and parses/validates JSON output defensively.
* **New `/act` command:** route freeform input through the planner, validate the selected command and args against the existing option models, then dispatch safely. Player input is persisted to transcripts before planning, like `/ooc`.
* **Parity:** `register_commands.py` and `cli.py` pick up `/act` automatically; users can test locally or in Discord with identical behavior.
* **Guardrails:** enforce an allowlist of commands (`roll`, `check`, `sheet.create`, `sheet.show`, `do`, `ooc`), size caps (≤16KB sheet JSON), and ephemeral errors for unknown or invalid plans. Planner “rationale” is logged but never shown to users.
* **Observability:** add structlog events and metrics counters (requests, parse failures, accepted/rejected decisions). Add a 30s cache to suppress duplicate LLM calls for identical input.
* **Latency & resilience:** keep the DEFERRED flow, apply a soft timeout, and fall back gracefully (default roll or user-friendly error). Feature flag `FEATURE_PLANNER_ENABLED` allows instant disable.
* **Testing:** unit tests for schema validation, plan parsing, and allowlist; integration tests with mocked LLM output; optional E2E test with SQLite to confirm transcripts and dispatches.
* **Rollout:** shadow in a dev guild, then canary in production with monitoring, before full availability. Document `/act` usage and examples. Rollback plan: flip the feature flag to disable without redeploy.
* **User experience:** freeform input like
  – `roll 2d6+3 for damage` → `/roll`
  – `make a dexterity check against DC 15` → `/check`
  – `create a character named Aria` → `/sheet.create` (or prompt for JSON)
  – `I sneak quietly` → `/do`
  …with deterministic rules resolving outcomes if `features_llm_visible` is enabled.

**Security considerations:** no direct tool execution; all planner output validated through option models; ephemeral error handling; strict input bounds; planner decisions logged with confidence but without leaking sensitive content.

**Future enhancements:** disambiguation mode for low-confidence plans, few-shot examples to improve stability, and per-guild defaults for planner behavior.

**Definition of done:** `/act` works in CLI and Discord, only allowlisted commands can be executed, invalid inputs are handled gracefully, caching and telemetry are in place, and feature flag control is available.

---

## Phase 5 — Solidify Foundation & Deepen Narrative AI ([#67](https://github.com/crashtestbrandt/Adventorator/issues/67)) — status: closed

**Goal:** Transition the application from a clever prototype to a stable, robust platform. Deepen the core AI's capabilities to make it a more intelligent and context-aware narrator before introducing the complexities of combat.

**Deliverables:**

1.  **Foundational Infrastructure (`postgres`, `containerization`):**
    * **Migrate to Postgres:** Update `db.py` and configuration to use `postgresql+asyncpg` as the primary driver.
    * **Full Containerization:** Create a `docker-compose.yml` file that orchestrates the FastAPI application, Postgres database, and any other services (like Redis, if planned for Phase 5). This ensures a one-command setup for development and creates a production-ready deployment artifact.
    * **Update CI/CD:** Modify the continuous integration pipeline to build the Docker image and run tests against a containerized Postgres instance, achieving true dev/prod parity.

2.  **Core Architecture Refinements (`rule engine encapsulation`, `campaign persistence`):**
    * **Encapsulate the Rules Engine:** The `rules` package is currently a collection of functions. Formalize it. Perhaps create a `Ruleset` class that can be initialized for a specific system (e.g., `ruleset = Ruleset("5e-srd")`). This class would contain methods like `ruleset.perform_check(...)`, `ruleset.calculate_damage(...)`, etc. This makes the `orchestrator`'s dependency clearer and prepares for supporting multiple game systems.
    * **Mature Campaign/Character Persistence:**
        * The `/sheet create` command is good, but it's basic.
        * Implement a `Character` class or service that can be loaded within the `orchestrator`.
        * The `sheet_info_provider` function in `orchestrator.py` is a hint at this; make it a reality. It should load the character's full sheet from the DB based on the `player_id`.

3.  **Core Capability Maturation (`context awareness`, `planner/orchestrator`):**
    * **Context-Aware Orchestrator:** This is the most important step. Modify `run_orchestrator` to be truly context-aware.
        * **Input:** It should accept a `character_id` or `player_id`.
        * **Logic:** It should load the relevant `CharacterSheet` from the database.
        * **Proposal Enhancement:** The LLM's "narrator" prompt should be enriched with key character details (e.g., ability scores, known skills). This allows the LLM to propose more intelligent checks. For example, if a character is proficient in "Stealth", the LLM should be more likely to propose a DEX (Stealth) check when the player says "I sneak past the guard."
        * **Rules Execution:** The call to `compute_check` should now be populated with the *actual* stats from the loaded character sheet, not default values or user-provided options.
    * **Smarter Planner:**
        * **Disambiguation:** If the `planner` LLM returns a low-confidence plan, instead of failing, the `/act` command could respond with "Did you mean to: a) `/do I attack the goblin`, or b) `/roll for initiative`?" using Discord buttons.
        * **Argument Extraction:** Improve the planner's prompt to not just pick a command, but also to better populate its arguments. For `create a character named Aria`, it should know to prompt for the required JSON, rather than just calling `/sheet create` with no arguments.

**Exit Criteria for Phase 4.5:**

* The entire application runs via a single `docker-compose up` command.
* All tests pass against a Postgres database.
* The `/do` command automatically loads the acting character's sheet from the DB.
* The `orchestrator`'s LLM prompt now includes the character's core abilities, leading to more contextually relevant check proposals.
* The outcome of a check proposed by the `orchestrator` uses the character's real stats, not defaults.
* The `rules` logic is cleanly separated and easier to test and extend.

---

## Phase 6 — Content ingestion & retrieval (memory without hallucinations) ([#11](https://github.com/crashtestbrandt/Adventorator/issues/11)) — status: closed

**Goal:** Feed the bot structured adventure info and prior sessions safely.

**Deliverables**
* Ingestion pipeline:
  * Markdown/HTML → normalized nodes (location, npc, encounter, lore)
  * Separate player-facing vs gm-only fields
  * Vector store (pgvector/Qdrant) + retriever with filters (campaign_id, node_type)
* Clerk summarizer job producing neutral session summaries with key_facts, open_threads
* Orchestrator context bundle cap (~8–12k tokens): {current scene node, active PC sheets (pruned), last N turns, house rules} + top-k retrieved

**Exit criteria**
* Retrieval accuracy: spot-check that top-k includes the correct node in canned tests
* No GM-only leaks in player messages (unit test: redaction passes)

**Rollback**
* If vector DB down, fall back to last session summary only.

---

## Phase 7 — Introduce Executor (dry-run only) ([#10](https://github.com/crashtestbrandt/Adventorator/issues/10)) — status: closed

Goal
- Establish the Executor and ToolRegistry contracts without allowing state mutations. Orchestrator uses Executor.dry_run to produce previews; all outputs remain ephemeral.

Deliverables
- Contracts
  - `ToolCallChain` JSON schema (versioned, v1) with `request_id`, `scene_id`, and `steps[{ tool, args, requires_confirmation, visibility }]`.
  - `ToolRegistry` with JSON-Schema metadata and argument validation; initial tools: `roll`, `check`.
  - `Executor` service: `execute_chain(chain, dry_run: bool) -> Preview|Result`.
- Orchestrator integration
  - Wrap legacy single-action planner outputs into a one-step `ToolCallChain` (compat shim).
  - Call `Executor.execute_chain(..., dry_run=True)`; format a concise preview; keep responses ephemeral.
- Observability
  - Add `request_id` propagation: interaction → planner → orchestrator → executor logs.
  - Metrics: `executor.preview.ok/error`, duration_ms.
- FF: `features.executor = false` (default off); `features.llm_visible` respected.

Tests
- Unit: `ToolRegistry` validation, `Executor` dry-run for roll/check.
- Integration: `/plan` → orchestrator → executor.dry_run; transcripts written; no DB mutations.

DoD
- All existing tests pass; new preview tests pass; executor can be toggled via FF.

RB
- Flip `features.executor=false`; orchestrator falls back to legacy behavior.

---

## Phase 8 — Pending Actions and Confirmation Flow ([#12](https://github.com/crashtestbrandt/Adventorator/issues/12)) — status: closed

Goal
- Introduce a gating loop for destructive actions using PendingAction with TTL and idempotency. Still minimal tool surface.

Deliverables
- Data/Repos
  - `PendingAction(id, scene_id, user_id, plan_json, status: pending|applied|canceled, expires_at, dedup_hash)`.
  - Repos: `create_pending_action`, `mark_applied`, `mark_canceled`, `get_pending_for_user(scene)`.
- Commands/UI
  - Present preview plus CTA. Start simple with commands: `/confirm <action_id>`, `/cancel <action_id>`; buttons can come later.
  - Orchestrator: when `requires_confirmation` present in any step → persist `PendingAction` and prompt user.
- Executor
  - `execute_chain(..., dry_run=False)` applies only after orchestrator confirmation; enforce idempotency by `(scene_id, user_id, dedup_hash)`.
- Observability
  - Metrics: `pending.created`, `pending.confirmed`, `pending.canceled`, `pending.expired`.
- FF: `features.executor_confirm = true` (can disable confirmation for dev/testing only).

Tests
- Unit: dedup hash stability; TTL expiry job/logic.
- Integration: preview → confirm → apply; repeated confirm is a no-op; cancel prevents apply.

DoD
- Safe, idempotent confirm/apply loop working for synthetic mutating tools (stub mutation).

RB
- Disable `features.executor` to drop back to non-mutating previews only.

---

## Phase 9 — Event-Sourced Mutations (Ledger foundation) ([#13](https://github.com/crashtestbrandt/Adventorator/issues/13)) — status: closed

Goal
- Make all state changes append-only events; current state is derived by folding events where needed.

Deliverables
- Models/Repos
  - `Event(id, scene_id, actor_id, type, payload(jsonb), request_id, ts)`.
  - Write helpers: `append_event`, `list_events(scene_id, since)`.
  - Lightweight state fold helpers for targeted views (e.g., HP by character).
- Executor
  - All mutating tool handlers emit Events (even if state tables exist). Dry-run produces predicted events without writing.
- Migrations
  - Alembic migration for `pending_actions` and `events`.
- Observability
  - Metrics: `events.append.ok/error`; log with `request_id`.

Tests
- Unit: event append and fold; serialization determinism.
- Integration: confirm → events appended; replay yields identical state.

DoD
- Mutating tool stubs append events reliably; replay produces expected views.

RB
- Keep a kill-switch: `features.events = false` routes to in-memory events (dev only) or disables mutation tools.

---

## Phase 10 — Encounter & Turn Engine (Foundations) ([#14](https://github.com/crashtestbrandt/Adventorator/issues/14)) — status: closed

Goal
- Introduce minimal encounter model and synchronous turn sequencing with locks.

Deliverables
- Models/Repos
  - `Encounter(id, scene_id, status: setup|active|ended, round, active_idx)`
  - `Combatant(id, encounter_id, character_id|null, name, initiative, hp, conditions jsonb, token_id|null)`
- Locks & Concurrency
  - Postgres advisory locks keyed by `encounter_id` for turn-critical mutations.
  - In-process `asyncio.Lock` per `encounter_id` as a fast-path; always acquire DB lock as the source of truth.
- Tools
  - `start_encounter`, `add_combatant`, `set_initiative`, `next_turn`, `end_encounter` (event-emitting; dry-run supported).
- FF: `features.combat = false` (default off).

Tests
- Concurrency tests: two actors try to `next_turn` simultaneously → exactly one success; lock wait metrics recorded.
- Golden-log: canned encounter plays the same across runs (event equality).

DoD
- Deterministic next_turn with proper locking; basic encounter lifecycle.

RB
- Disable `features.combat`; commands return helpful exploration-only message.

---

## Phase 11 — Minimal Combat Actions ([#75](https://github.com/crashtestbrandt/Adventorator/issues/75)) — status: closed

Goal
- Enable core actions: to-hit, damage, simple conditions; keep scope tight.

Deliverables
- Rules
  - `attack(attacker, target, weapon)` → to-hit vs AC, crit on 20, fumbles optional.
  - `apply_damage(amount, type)`, `apply_condition(name, duration?)`.
- Executor tools
  - Implement above as tool handlers; dry-run computes outcomes and proposed events; apply appends events and updates derived views if any.
- Orchestrator
  - Preview includes mechanics (rolls, DC/AC, pass/fail) and concise narration.
- Observability
  - Metrics: `executor.apply.ok/error`, per-tool counters.

Tests
- Unit: rules correctness for edge cases (advantage, resistances as TODO guardrails).
- Integration: end-to-end attack flow with confirm/apply; idempotent re-apply.

DoD
- A basic attack can be proposed, previewed, confirmed, and applied with consistent outcomes.

RB
- Flip `features.combat=false` to disable combat tools; non-combat features unaffected.

---

## Phase 12 — Map Rendering MVP ([#76](https://github.com/crashtestbrandt/Adventorator/issues/76)) — status: open

Goal
- Provide a simple, synchronous visual for encounters via a static image.

Deliverables
- Renderer service (pure Python)
  - Pillow or matplotlib to render: grid, background tint, tokens (colored circles with initials), active combatant highlight.
  - Caching by `(encounter_id, last_event_id)`; invalidated on new events.
- Commands
  - `/map show` for the active encounter; orchestrator attaches rendered PNG (or URL) to the follow-up.
- Observability
  - Metrics: `renderer.render_ms`, cache hit ratio.
- FF: `features.map = false` (default off).

Tests
- Snapshot tests: render a tiny 10×10 grid with 2–3 tokens; compare hash.

DoD
- Image renders deterministically; attach to Discord works in dev.

RB
- Disable `features.map`; command returns a helpful stub.

---

## Phase 13 — Modal Scenes (Exploration ↔ Combat) ([#77](https://github.com/crashtestbrandt/Adventorator/issues/77)) — status: open

Goal
- Allow branching personal scenes and merging into a shared combat thread.

Deliverables
- Scene model additions
  - `mode: exploration|combat`, `participants[]`, `location_ref`, `clock`.
- Tools
  - `branch_scene(player)`, `merge_scenes([ids])` with event records and conflict prompts to GM on divergence.
- Orchestrator
  - Enforce that actions target the user’s current scene; surface helpful errors if not.

Tests
- Merge correctness: HP/conditions/initiative preserved; audit trail captures merge lineage.

DoD
- Two solo scenes can merge into a combat scene with consistent state.

RB
- Disable branching/merge FF to funnel all actions into a single scene.

---

## Phase 14 — Campaign & Character Ingestion with Preview-Confirm ([#78](https://github.com/crashtestbrandt/Adventorator/issues/78)) — status: open

Goal
- Import campaign nodes and character sheets with a safe, reviewable flow.

Deliverables
- Commands
  - `/campaign upload` (markdown/zip) → normalized nodes; index for retrieval (if enabled).
  - `/campaign start` sets the active scene/location; GM-only.
  - `/sheet import` accepts Markdown with YAML frontmatter or fenced JSON; normalize to strict `CharacterSheet`.
- Orchestrator + Executor
  - Treat imports as mutating tool chains; always preview a diff and require confirmation.
- Observability
  - Metrics: import sizes, node counts, normalization errors.

Tests
- Unit: normalizer mappings (aliases), invalid inputs rejected.
- Integration: upload → preview → confirm → data persisted; GM ACL enforced.

DoD
- Data imports are reliable, previewed, and gated; retrieval (if enabled) indexes new content.

RB
- Disable ingestion FF; commands return stubs.

---

## Phase 15 — GM Controls, Overrides, and Safety ([#79](https://github.com/crashtestbrandt/Adventorator/issues/79)) — status: open

Goal
- Give GMs precise, permissioned control and recovery tools.

Deliverables
- Commands (GM-only)
  - `gm.set_hp`, `gm.add_condition`, `gm.end_turn`, `gm.reroll`.
- Safety
  - Rewind last N mutations by replaying the event ledger to a prior cursor.
  - Lines/Veils filters for narration/output.
- Permissions
  - Role-based checks; deny with clear ephemeral errors.

Tests
- Rewind correctness under concurrent events; permission matrix.

DoD
- GM can correct state quickly and safely; audit remains consistent.

RB
- GM tools remain operational even if LLM or retrieval is disabled.

---

## Phase 16 — Hardening and Ops ([#80](https://github.com/crashtestbrandt/Adventorator/issues/80)) — status: open

Goal
- Achieve reliable small-scale operation with degraded-mode strategies.

Deliverables
- Resilience
  - Rate limiting per user/channel; idempotency keys across interactions.
  - Circuit breakers for LLM and retriever; degraded modes: rules-only, last-summary-only.
  - Safe retries for follow-ups and webhooks.
- SLOs & Metrics
  - SLOs: ack <3s, p95 preview/apply latency targets, error budgets.
  - Metrics coverage: planner.accepted/rejected, executor preview/apply, lock wait, renderer_ms, ingestion sizes.
- Cost guards
  - Token budgeting and truncation strategies; planner cache/TTL.

Tests
- Chaos tests: kill app mid-turn; LLM 500s; vector DB unavailable → degraded but usable.

DoD
- Degraded modes keep the bot functioning; SLOs met in CI/dev benchmarks.

RB
- Flip FFs per dependency to restore normal flow or isolate faults quickly.

---

Notes
- This file is generated from GitHub issues to keep the implementation plan close to source. Update the issues to refresh content.
