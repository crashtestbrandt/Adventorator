# Phase 10 Low-Level Implementation Plan

## Scope checkpoints (what we’ll ship, incrementally)

- Minimal data model and repos: Encounter + Combatant
- Locking: asyncio per-encounter lock + Postgres advisory lock
- Deterministic turn sequencing: start → add → initiative → next_turn → end
- Executor tools for each operation, event-emitting with dry-run support
- FF gating: [combat].enabled = false (default off; loader falls back to legacy `[features].combat`)
- Tests: unit + concurrency; a golden-log for a canned encounter
- Metrics and observability: locks.wait_ms histogram, locks.mode, and executor preview/apply per-tool counters and durations

## Guiding principles

- Small surfaces, safe-by-default: All tools behind [combat].enabled (legacy `[features].combat` supported) and executor-confirm where applicable.
- Event-sourced visibility: Mutating tools always predict and append Events (Phase 9 pattern), even with state tables.
- DB lock is source of truth; asyncio lock is a fast-path. Never mutate without both locks (when PG is available).
- Postgres-first with graceful SQLite fallback in tests/dev.

---

## Milestone 0 — Scaffolding (FF and contracts) [0.5 day]

Deliverables
- Config: Add `[combat].enabled = false` (loader supports legacy fallback to `[features].combat`).
- Contracts (docs and type hints only, no behavior yet):
  - Encounter status: setup | active | ended
  - Event types: encounter.started, combatant.added, combatant.initiative_set, encounter.advanced, encounter.ended
- No-op tool registrations guarded by FF that return “combat disabled”.

Acceptance
- Build, lint, and typecheck pass; existing tests untouched.

Risks/Rollback
- None; default FF off.

---

## Milestone 1 — Data model + migration + repos [0.5–1 day]

Deliverables
- Models in `models.py`
  - Encounter(id PK, scene_id FK, status enum, round int default 1, active_idx int default 0, created_at ts, updated_at ts)
  - Combatant(id PK, encounter_id FK, character_id nullable FK, name text, initiative int nullable, hp int default 0, conditions JSONB (default {}), token_id nullable text, order_idx int for tie-breaking)
- Alembic migration (Postgres JSONB; fallback to JSON for SQLite via SA)
- Repos in `repos.py`
  - create_encounter(scene_id) -> Encounter
  - get_encounter(encounter_id|scene_id) -> Encounter
  - update_encounter_status/active_idx/round
  - add_combatant, set_initiative, list_combatants, list_by_initiative(encounter_id)
  - id helpers: next order_idx per encounter (sequence by insertion)
- Basic unit tests: CRUD and ordering

Acceptance
- Tables exist; repo ops verified; ordering by (initiative desc nulls last, then order_idx asc).

Edge cases
- Null initiative during setup; ensures deterministic tie-break via order_idx.

---

## Milestone 2 — Locking infrastructure [0.5 day]

Deliverables
- Lock helper module (e.g., `services/lock_service.py`)
  - In-process: `asyncio.Lock` per encounter_id using WeakValueDictionary; context manager `with_encounter_lock(encounter_id)`
  - Postgres advisory lock: `pg_try_advisory_lock(1001, encounter_id)` (namespace with class key 1001), with bounded wait/backoff and timeout; `pg_advisory_unlock(1001, encounter_id)` on exit
  - Driver-aware: if not Postgres, skip DB lock and only use asyncio lock; log and metric this mode
- Metrics:
  - locks.acquire.success/timeout/error
  - locks.wait_ms (histogram)
  - locks.mode counters: locks.mode.inproc, locks.mode.pg

Acceptance
- Unit tests simulate lock mode selection; simple contention test for asyncio lock.

Risks
- Deadlocks if code path throws; ensure try/finally unlock.

---

## Milestone 3 — Service: Encounter lifecycle (start/add/init) [0.5–1 day]

Deliverables
- `services/encounter_service.py`
  - start_encounter(scene_id): creates Encounter(status=setup), emits predicted event in dry-run and writes event in apply
  - add_combatant(encounter_id, name, character_id?, hp?, token_id?): status must be setup; append; deterministic order_idx
  - set_initiative(encounter_id, combatant_id, initiative: int): allowed in setup; when all combatants have initiative, service can start encounter (status=active) and compute first active_idx
- Deterministic initiative ordering:
  - Sort key: (initiative desc, order_idx asc)
  - First active_idx = 0 at transition to active
- Event prediction utility: Build a list of domain events as dicts → consumed by Executor

Acceptance
- Unit tests for lifecycle transitions; event payloads deterministic.

Edge cases
- Setting initiative after encounter already active → reject (ephemeral error)
- Duplicate combatant names allowed but stable via order_idx

---

## Milestone 4 — Service: next_turn and end_encounter with locks [1 day]

Deliverables
- next_turn(encounter_id):
  - Acquire asyncio lock; then DB advisory lock (if Postgres), with bounded wait
  - Read Encounter + ordered combatants
  - If status != active → error
  - Compute new active_idx = (active_idx + 1) % N; if wraps to 0 → round += 1
  - Persist active_idx/round; build encounter.advanced event
  - Release locks
- end_encounter(encounter_id):
  - Acquire locks
  - Set status=ended; emit encounter.ended
- Metrics: next_turn.ok/error, contention and duration_ms

Acceptance
- Unit tests for index wrap and round increment
- Concurrency test (asyncio):
  - Two concurrent next_turn calls → exactly one success; the loser sees retry/locked message or no-op (idempotent guard by comparing pre/post active_idx)
- Optional: if `features.events` on, append events; else only state updated

Edge cases
- No combatants or all without initiative → error
- Encounter ended → no-op with message

---

## Milestone 5 — Executor tools (dry-run + apply) [0.5–1 day]

Deliverables
- Register tools (behind features.combat):
  - start_encounter(scene_id)
  - add_combatant(encounter_id, name, character_id?, hp?, token_id?)
  - set_initiative(encounter_id, combatant_id, initiative)
  - next_turn(encounter_id)
  - end_encounter(encounter_id)
- Behavior:
  - dry_run: compute predicted events and preview items (succinct mechanics: active name, round)
  - apply: call service; if `features.events` enabled, append events; return same preview for uniformity
- Schemas: strict pydantic JSON for args; helpful validation messages

Acceptance
- Unit tests for Executor integration for each tool; previews stable
- Integration: chain with two steps (add + set initiative) works; no DB mutations in dry-run

---

## Milestone 6 — Golden-log and concurrency tests [0.5 day]

Deliverables
- Golden-log test:
  - Canned: start → add A,B → set init (A: 15, B: 12) → next_turn x3 → end
  - Assert event list equality and deterministic active sequence [A, B, A]
- Concurrency test:
  - Use asyncio.gather with two next_turn calls; assert one success
  - If driver=Postgres, optional e2e that verifies advisory lock path; skip on SQLite

Acceptance
- Tests green across both drivers; PG-only test marked with skip-if-not-pg.

---

## Milestone 7 — Observability and docs [0.5 day]

Deliverables
- Metrics:
  - executor.apply/preview per-tool counters
  - locks.* (from Milestone 2)
  - encounter.* counters: encounter.start.ok, encounter.add.ok/error, encounter.initiative_set.ok/error, encounter.advanced, encounter.next_turn.ok/error (+ encounter.next_turn.ms histogram), encounter.end.ok/error
- Logging: request_id propagation (already present) through tools
- README/docs: short “Encounter mode (FF)” section with behavior; note FF default off

Acceptance
- Metrics names appear in code; docs updated.

---

## Data contracts and event payloads (minimal, deterministic)

- encounter.started: { encounter_id, scene_id, ts }
- combatant.added: { encounter_id, combatant_id, name, character_id?, order_idx, ts }
- combatant.initiative_set: { encounter_id, combatant_id, initiative, ts }
- encounter.advanced: { encounter_id, round, active_idx, active_combatant_id, ts }
- encounter.ended: { encounter_id, ts }

Notes
- Timestamps from monotonic-now or DB now() to stay consistent with other events.
- For previews, show “Round r, Active: <name> (#id)”.

---

## Turn engine “contract” and edge cases

Inputs
- encounter_id (int), scene_id (int), tool args

Outputs
- Updated Encounter fields; Events appended (when enabled); Preview items

Error modes
- Lock timeout → informative error + metric
- Invalid status transitions → ephemeral error
- No combatants/initiatives → ephemeral error

Edge cases to cover
- Ties in initiative: stable via order_idx
- Adding combatants after active: reject (Phase 11 can allow late-join as extension)
- Attempting next_turn in setup/ended: reject
- Re-entrant calls: loser sees “busy/try again” or no-op guarded by state compare

---

## Test plan (summary)

- Unit
  - Repo CRUD and ordering
  - Service transitions and next_turn math
  - Lock helper (mode selection and basic contention)
  - Executor tool validations and previews

- Integration
  - Golden-log event equality
  - Concurrency: two simultaneous next_turn → one success
  - Optional PG-only advisory lock assertion

- Determinism
  - Stable sorting and event payloads; fixed names/IDs in fixtures

---

## Rollout and FF strategy

- Default `[combat].enabled=false` (legacy `[features].combat` supported)
- Phase 10 PR 1: Models/migration + repos (FF off)
- PR 2: Locking + services (still FF off; internal tests only)
- PR 3: Executor tools (FF off by default; tests use direct service calls + executor with FF temporarily on in test config)
- PR 4: Concurrency + golden-log tests + metrics + docs
- Canary: enable FF in dev/CI PG path, then a private guild
- Rollback: flip FF; data tables remain benign

---

## Small adjacent improvements (optional, low risk)

- RNG scoping hook on encounter start (seed from scene_id or request_id) to prep for Phase 11 determinism.
- Simple read-only “/encounter status” command (behind FF) that prints active, round, and initiative table for manual inspection. (Implemented)

---

## Mapping to Phase 10 DoD

- Deterministic next_turn with proper locking: Milestones 2–4
- Basic encounter lifecycle (start/add/init/next/end): Milestones 3–4
- Tools implemented with event emission and dry-run: Milestone 5
- Concurrency test + golden-log: Milestone 6
- FF off by default; helpful messages when disabled: Milestones 0 & 5
