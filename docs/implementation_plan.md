# Implementation Plan — Phase Descriptions

This document aggregates the “Phase N” issues from GitHub with their full descriptions for easy reference. Each section links back to the original issue.

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

## Phase 3 — LLM “narrator” in shadow mode ([#9](https://github.com/crashtestbrandt/Adventorator/issues/9)) — status: open

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

## Phase 4 — Initiative & turn engine (synchronous queue) ([#10](https://github.com/crashtestbrandt/Adventorator/issues/10)) — status: open

**Goal:** Combat with strict turn order and timeouts; still minimal rules.

**Deliverables**
* Rules Service v1:
  * Initiative queue; start/end-of-turn hooks
  * Attacks: to-hit vs AC; damage; simple conditions (prone, restrained)
  * HP/resource mutation endpoints
  * Redis locks: per-scene turn lock; TTL-based timeout → auto-Dodge or configured fallback
* Commands/UI:
  * /start-combat (spawns a combat thread)
  * Buttons/selects for common actions; ephemeral per-player panels
* Recovery: if the worker dies mid-turn, lock expiry yields safe fallback

**Exit criteria**
* Concurrency tests (two users act “simultaneously”) don’t break the queue
* Golden log for a canned encounter plays identically across runs

**Rollback**
* ff.combat=false falls back to exploration-only; command returns helpful message.

---

## Phase 5 — Content ingestion & retrieval (memory without hallucinations) ([#11](https://github.com/crashtestbrandt/Adventorator/issues/11)) — status: open

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

## Phase 6 — Modal solo scenes + merge to combat ([#12](https://github.com/crashtestbrandt/Adventorator/issues/12)) — status: open

**Goal:** Players can act in personal threads; merge to shared combat when needed.

**Deliverables**
* Scene model: {scene_id, participants[], location_node, mode:'exploration'|'combat', clock}
* Merge/branch ops:
  * branch_scene(from, player) → solo thread
  * merge_scenes([ids]) → new combat thread; rebase clocks if you track time
  * Conflict policy: if asynchronous scenes diverge, prompt the human GM to resolve or soft-retcon (configurable)

**Exit criteria**
* Merging two solo scenes into one combat scene keeps initiative & HP correct
* Audit trail shows how/when merges occurred

**Rollback**
* Disable branching: all actions happen in one shared channel.

---

## Phase 7 — GM controls, overrides, & safety tooling ([#13](https://github.com/crashtestbrandt/Adventorator/issues/13)) — status: open

**Goal:** Human-in-the-loop when it matters.

**Deliverables**
* /gm commands (permission-gated): set HP, add/remove condition, modify inventory, end turn, reroll
* Pause & rewind last N mutations (event-sourced ledger → rebuild)
* Lines/Veils & content filters applied to narration
* “Why” panel: include the roll and rule citation the LLM used (from your proposal + rules call)

**Exit criteria**
* Rewind restores pre-change state in ≤1s in test; mutation ledger replays cleanly
* Permissions tested against role IDs

**Rollback**
* GM overrides always available even if LLM/tools are off.

---

## Phase 8 — Hardening & productionization ([#14](https://github.com/crashtestbrandt/Adventorator/issues/14)) — status: open

**Goal:** Operate at small scale without surprises.

**Deliverables**
* Rate limiting per user/channel; exponential backoff on Discord 429s
* Idempotency keys for interactions; safe retry on network flaps
* Circuit breakers per external dependency (LLM, vector DB). Degraded modes:
 * LLM down → rules-only, factual responses
 * Vector DB down → no retrieval, rely on last summary
 * Chaos tests: kill the worker mid-turn; drop the vector DB; random 500s from LLM client
* Cost guards:
 * Token budgeter (hard caps); refusal → ask for shorter actions
 * Cache last narration for identical prompts within 30s (spam control)

**Exit criteria**
* Degraded modes keep the bot usable (no crashes, just reduced features)
* SLOs defined: ack <3s, p95 narration <X sec, error rate <Y%

**Rollback**
* Feature flags per dependency; turn off the breaker to restore normal flow.

---

Notes
- This file is generated from GitHub issues to keep the implementation plan close to source. Update the issues to refresh content.
