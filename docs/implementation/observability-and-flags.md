# Observability and Feature Flag Playbook

This playbook documents budgets, metrics, and rollout/rollback guidance required by the AIDD pipeline for Adventorator’s critical systems. Keep it synchronized with feature epics, ADRs, and the configuration reference in [`README.md`](../../README.md#configuration).

## Global Observability Principles

- **Signal coverage.** Every Story must register metrics, logs, and traces that satisfy the "Observability Spec" section of the issue template.
- **Cardinality guardrails.** Dimensions limited to `guild_id`, `channel_id`, `feature_flag`, `actor_id` (for orchestrator) to keep metrics stores manageable.
- **Alert routing.** Alerts page the on-call DM SRE rotation via OpsGenie; dashboards live in the "Adventorator Core" Grafana folder.

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

## Feature Flag Runbooks

| Flag | Purpose | Rollout Stages | Rollback |
| --- | --- | --- | --- |
| `features.planner` | Enables `/plan` AI routing | 1) Internal guilds, 2) Opt-in beta servers, 3) General availability | Set to `false` in config, invalidate planner cache, notify #ops-adventorator |
| `features.executor` | Connects orchestrator to executor preview/apply | 1) Preview-only flows, 2) Partial apply (non-destructive), 3) Full apply | Disable flag, run `scripts/cleanup_pending.py`, replay events for audit |
| `features.combat` | Activates encounter engine | 1) Staging playtests, 2) 10% guild cohort, 3) 50% guilds, 4) 100% rollout | Toggle flag off, execute rollback checklist in STORY-ENC-002C, notify players |
| `features.events` | Emits domain events for ledger | 1) Observability shadow mode, 2) Apply flows, 3) External integrations | Turn off flag, prune queued events, communicate to downstream consumers |

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
