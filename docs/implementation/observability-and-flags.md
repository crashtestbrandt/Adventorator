# Observability and Feature Flag Playbook

This playbook documents budgets, metrics, and rollout/rollback guidance required by the AIDD pipeline for Adventorator’s critical systems. Keep it synchronized with feature epics, ADRs, and the configuration reference in [`README.md`](../../README.md#configuration).

## Global Observability Principles

- **Signal coverage.** Every Story must register metrics, logs, and traces that satisfy the "Observability Spec" section of the issue template.
- **Cardinality guardrails.** Dimensions limited to `guild_id`, `channel_id`, `feature_flag`, `actor_id` (for orchestrator) to keep metrics stores manageable.
- **Alert routing.** Alerts page the on-call DM SRE rotation via OpsGenie; dashboards live in the "Adventorator Core" Grafana folder.

## Event Hash Chain Budgets (STORY-CDA-CORE-001C)

- **Metrics.**
  - `events.applied` (counter) — Total events successfully persisted with hash chain linkage.
  - `events.hash_mismatch` (counter) — Hash chain corruption detected; should be zero under normal conditions.
- **Logs.** Hash chain mismatch events structured as `event.chain_mismatch` with fields:
  - `campaign_id`, `replay_ordinal`, `event_type` — Event context for debugging
  - `expected_hash`, `actual_hash` — Hex-encoded hash prefixes (16 chars) for correlation
- **Verification API.** `verify_hash_chain(events)` returns summary dict; `get_campaign_events_for_verification(session, campaign_id=N)` retrieves ordered events.
- **Alert thresholds.** Any `events.hash_mismatch` > 0 triggers immediate investigation; indicates data corruption or implementation bug.

## Planner Budgets

- **Metrics.**
  - `planner.request.initiated` (counter) — Target alert if error rate ≥2% over 5 minutes.
  - `planner.catalog.drift` (gauge) — Should be zero; spikes trigger a DoR review.
  - `planner.latency.ms` (histogram) — p95 budget ≤ 1200 ms.
- **Logs.** Structured JSON with `request_id`, `command`, `validation_state`.
- **Traces.** Span `planner.generate` wraps LLM call; attach token usage attributes.
- **Feature flag dependencies.** `features.planner` gates planner usage; rollback disables `/plan` routing and falls back to manual command entry.

## Orchestrator Budgets

- **Metrics.**
  - `orchestrator.request.total` (counter) with outcome label `accepted|rejected` — monitor rejection spikes (>10% for 15 minutes).
  - `llm.defense.rejected` (counter) — tie to DoD acceptance tests.
  - `orchestrator.latency.ms` (histogram) — p95 budget ≤ 2500 ms.
- **Logs.** Include `scene_id`, `actor_id`, `rejection_reason`; scrub user PII.
- **Traces.** Span `orchestrator.propose` includes nested `llm.call` child.
- **Feature flags.** `features.executor` toggles preview/apply integration; rollback disables executor coupling and uses deterministic ruleset fallback.

## Executor Budgets

- **Metrics.**
  - `executor.preview.duration_ms` / `executor.apply.duration_ms` (histogram) — p95 ≤ 800 ms preview, ≤ 1500 ms apply.
  - `executor.toolchain.validation` (counter, labels `result=passed|failed`).
  - `locks.wait_ms` (histogram) — p95 ≤ 200 ms; track concurrency pressure.
- **Logs.** Tool chain JSON serialized with `tool`, `args_hash`, `requires_confirmation`.
- **Traces.** Span `executor.run` wraps preview/apply; include link to originating interaction.
- **Feature flags.** `features.executor_confirm` ensures confirmation for mutating actions; rollback flips flag to `false` and cancels pending confirmations.

## Encounter Observability Budget

- **Metrics.**
  - `encounter.active.count` (gauge) — Watch for >5 concurrent actives per guild (capacity planning).
  - `encounter.turn.advance` (counter, labels `result=success|conflict`); alert on conflict > 0.5/min.
  - `encounter.round.duration_ms` (histogram) — target p95 ≤ 90 seconds.
- **Logs.** Extend encounter logs with `encounter_id`, `round`, `active_combatant_id`, `transition` fields.
- **Traces.** Add span `encounter.advance` attached to executor apply flows.
- **Dashboards.** Grafana panels: "Encounter load", "Turn conflicts", "Round duration". Attach mock screenshot or JSON export to STORY-ENC-002B.

## Feature Flag Dependencies

| Flag | Depends On | Provides | Notes |
| ---- | ---------- | -------- | ----- |
| `features.action_validation` | `features.planner` (logical), optional `features.predicate_gate` | Wraps legacy planner/orchestrator/executor with Plan & ExecutionRequest | Safe disable reverts to legacy flow |
| `features.predicate_gate` | `features.planner` | Deterministic feasibility | When off, `Plan.feasible` always True (legacy path) |
| `features.mcp` | `features.action_validation` | MCP adapter routing | Off → direct rules path |
| `features.activity_log` | (none) | Mechanics ledger entries | Independent; enriches observability |
| `features.executor_confirm` | `features.executor` | Confirmation safety layer | Enforced for mutating apply |
| `features.combat` | `features.executor` (indirect for apply paths) | Encounter turn engine | Disable pauses encounters gracefully |
| `features.retrieval.enabled` | (none) | Retrieval augmentation | Provider sub-flag selects backend |
| `features.retrieval.provider` | `features.retrieval.enabled` | Backend selection | Changing may shift latency |

## Normalized Metric Namespace

| Domain | Legacy Metric (if any) | Normalized Name | Type | Key Labels |
| ------ | --------------------- | --------------- | ---- | ---------- |
| Planner | `planner.request.initiated` | `planner.request.count` | counter | outcome=`ok|error` |
| Planner | `planner.catalog.drift` | `planner.catalog.drift` | gauge | n/a |
| Predicate Gate | (n/a) | `predicate.gate.result` | counter | result=`ok|fail`, reason (bounded) |
| Orchestrator | `orchestrator.request.total` | `orchestrator.request.count` | counter | outcome=`accepted|rejected` |
| Orchestrator | `llm.defense.rejected` | (merged into above) | (removed) | Use outcome+reason labels |
| Executor | `executor.preview.duration_ms` | `executor.preview.seconds` | histogram | status=`ok|error` |
| Executor | `executor.apply.duration_ms` | `executor.apply.seconds` | histogram | status=`ok|error` |
| Executor | `executor.toolchain.validation` | `executor.toolchain.validation` | counter | result=`passed|failed` |
| Executor | `locks.wait_ms` | `executor.lock.wait.seconds` | histogram | resource=`encounter|combatant|global` |
| ExecutionRequest | (n/a) | `executor.execution_request.steps.count` | histogram | n/a |
| ActivityLog | (n/a) | `activity_log.entry.count` | counter | type=`mechanics` |
| Events | (n/a) | `events.applied` | counter | n/a |
| Events | (n/a) | `events.hash_mismatch` | counter | n/a |
| Events | (n/a) | `events.conflict` | counter | n/a |
| Events | (n/a) | `events.idempotent_reuse` | counter | n/a |
| Events | (n/a) | `event.apply.latency_ms` | histogram | n/a |
| Encounter | `encounter.turn.advance` | `encounter.turn.advance.count` | counter | result=`success|conflict` |
| Encounter | `encounter.round.duration_ms` | `encounter.round.duration.seconds` | histogram | n/a |

Adopt normalized names in new code; migrate legacy names opportunistically with dual-publish if dashboards depend on them.

## Feature Flag Runbooks

| Flag | Purpose | Rollout Stages | Rollback |
| --- | --- | --- | --- |
| `features.planner` | Enables `/plan` AI routing | 1) Internal guilds, 2) Opt-in beta servers, 3) General availability | Set to `false` in config, invalidate planner cache, notify #ops-adventorator |
| `features.executor` | Connects orchestrator to executor preview/apply | 1) Preview-only flows, 2) Partial apply (non-destructive), 3) Full apply | Disable flag, run `scripts/cleanup_pending.py`, replay events for audit |
| `features.combat` | Activates encounter engine | 1) Staging playtests, 2) 10% guild cohort, 3) 50% guilds, 4) 100% rollout | Toggle flag off, execute rollback checklist in STORY-ENC-002C, notify players |
### Consolidated Feature Flag Reference (Current Defaults)

| Flag | Default | Domain | Description | Related Epics / Stories | Rollout Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `features.llm` | true | LLM | Enables core LLM responses (baseline chat) | Core AI Systems | Medium | Disable to force pure deterministic command mode |
| `features.llm_visible` | true | LLM | Surfaces LLM output directly to users (vs shadow) | Core AI Systems | Low | Set false for shadow validation |
| `features.planner` | true | Planning | Routes `/plan` through planner pipeline | Core AI Systems / Planner Stories | Medium | Cache invalidation on disable |
| `features.action_validation` | false | Action Validation | Enables Plan/ExecutionRequest internal contracts | EPIC-AVA-001 (Phases 0–6) | Low | Wraps legacy paths; flip off for rollback |
| `features.predicate_gate` | false | Action Validation | Activates deterministic predicate feasibility checks | STORY-AVA-001F | Low | Bypass returns legacy feasibility behavior |
| `features.mcp` | false | Action Validation / MCP | Routes executor tooling via MCP adapter layer | STORY-AVA-001H | Medium | Off → direct rules path; on emits `executor.mcp.*` metrics |
| `features.activity_log` | false | Observability | Persists mechanics ActivityLog entries | STORY-AVA-001G | Low | Off retains metrics/logs only |
| `features.executor` | true | Execution | Connects orchestrator to executor preview/apply | Multiple | Medium | Disable to isolate planning without apply |
| `features.executor_confirm` | (implied true when confirmation flow active) | Safety | Requires explicit confirm for mutating actions | Pending Action / Safety Stories | Low | Use for high-risk tool gating |
| `features.events` | true | Events | Emits domain events for ledger & integration | Event Epics | Medium | Off halts downstream integrations |
| `features.rules` | true | Rules Engine | Enables deterministic rules module usage | Core Systems | Low | Rarely disabled outside tests |
| `features.combat` | true | Encounter | Activates encounter/turn engine | Encounter Turn Engine | Medium | Off pauses active encounters (gracefully) |
| `features.retrieval.enabled` | true | Retrieval | Enables retrieval-augmented context injection | Retrieval Epic | Medium | provider sub-flags control backend |
| `features.retrieval.provider` | "none" | Retrieval | Selects retrieval backend (`none|pgvector|qdrant`) | Retrieval Epic | Medium | Changing may impact latency |

## Rollout/Rollback Checklist Template

1. Announce planned change in `#ops-adventorator` with link to Story issue.
2. Verify monitoring dashboards and alerts are in "ready" state.
3. Execute staged rollout commands (documented per flag above).
4. Capture metrics snapshots before/after change in shared drive.
5. For rollback, reverse the commands, postmortem in the Story issue, and update this playbook if new learnings surface.

## Ownership

- **Primary.** Adventorator Operations (on-call DM SRE rotation).
- **Secondary.** Feature owners listed in each Epic document.
- **Review cadence.** Monthly reliability review; align updates with ADR revisions.
