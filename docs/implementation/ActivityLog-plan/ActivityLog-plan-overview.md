# ActivityLog — Mechanics Event Ledger — status: open

Introduce a dedicated ActivityLog table for structured, queryable mechanics with a safe, incremental rollout. Keep edits small, match existing patterns (async repos + session_scope), and validate via tests.

---

## Goal and Scope

Why
- Separate narrative (Transcript) from mechanics (ActivityLog).
- Enable efficient queries, live UIs, deterministic reconstruction, analytics.
- Prepare for future features (undo/redo, GM tools, combat trackers).

Success
- Deferred acks remain <3s; logging happens off the hot path.
- Deterministic, test-covered logging of rolls/checks/orchestrator outcomes.
- Backward compatible; instant disable via feature flag.
- Narration remains narrative-only; mechanics render via ActivityLog.

Out of scope
- No rules changes; no UI components in this phase.

---

## Design Principles

- Structured-first: indexed context columns + JSON payload for details.
- Immutable and auditable: timezone-aware timestamps; correlation_id for grouping.
- Defensive: payload redaction/clamps; never break user flow on log failure.
- Compatibility: optional Transcript.activity_log_id; feature-flagged writes.
- Observability: minimal counters, structured logs, payload size metrics.

---

## Milestone 0 — Groundwork and Contracts

What
- Define event taxonomy (e.g., dice.roll, check.ability, combat.*).
- Decide on actor reference format (e.g., char:<id>, user:<discord>, npc:<key>).
- Add a feature flag (features.activity_log) default false.

Acceptance
- Taxonomy documented; feature flag wired into settings and tests.

Rollback
- N/A (no writes yet).

---

## Milestone 1 — Schema and Repository

What
- Add ActivityLog model with indexed context, event_type, summary, payload, correlation_id, created_at (UTC).
- Add optional Transcript.activity_log_id (nullable).
- Provide a repository helper to create ActivityLog entries; apply payload redaction and size bounds.

Acceptance
- Alembic upgrade applies cleanly on SQLite/Postgres.
- Basic create-read verified in a unit/integration test.
- No handler routes call it yet.

Rollback
- Alembic downgrade restores previous state without data loss.

---

## Milestone 2 — Integration Points (non-invasive)

What
- Integrate logging in mechanics sources:
  - /roll: log dice outcomes (expr, rolls, total, crit).
  - /check: log check inputs and results.
  - Orchestrator: log validated mechanics when applicable.
- Always use async with session_scope and repos; defer first, log in background.
- Do not change user-visible content yet.

Acceptance
- End-to-end tests show ActivityLog rows created for /roll and /check.
- Orchestrator integration covered with mocks; counters increment.

Rollback
- Flip features.activity_log=false; behavior unchanged for users.

---

## Milestone 3 — Decouple Transcript from Mechanics

What
- Start linking bot/system transcripts to ActivityLog via activity_log_id when the message originates from a mechanical action.
- Keep transcript content narrative-only; render mechanics via ActivityLog in UI (future).

Acceptance
- Transcript rows contain activity_log_id for mechanics messages.
- No regression in existing transcript tests.

Rollback
- Keep column but stop populating it (flag off); transcripts still work.

---

## Milestone 4 — Defensive Programming

What
- Enforce payload caps (size), redact sensitive keys, and clamp summaries if needed.
- Idempotency guidance: reuse correlation_id per interaction to group events; avoid double-logging at call sites.
- Errors degrade silently (log + metric) and never block command completion.

Acceptance
- Unit tests for redaction/clamping; metrics show created/failed increments.
- Chaos injection doesn’t affect user-visible flow.

Rollback
- Leave defenses in place; no behavior change required.

---

## Milestone 5 — Observability and Metrics

What
- Minimal counters: activity_log.created, activity_log.failed, activity_log.linked_to_transcript.
- Structured logs with event_type, scene_id, campaign_id, correlation_id, refs, and payload size (not contents).
- Sampling as needed; avoid logging raw payloads.

Acceptance
- Metrics visible in tests (metrics.reset_counters + get_counter).
- Logs show expected fields during integration tests.

Rollback
- Disable metrics/log sampling without affecting functionality.

---

## Milestone 6 — Testing

What
- Unit: repo helper redaction/clamp; model shape; timestamp UTC.
- Integration: /roll and /check create ActivityLog; orchestrator path logs once; transcript linkage present.
- E2E (SQLite): deferred ack, background follow-up, matching ActivityLog records.
- Determinism: RNG seeded per existing patterns; stable assertions.

Acceptance
- Tests green locally and in CI; no flakiness.

Rollback
- Revert failing integrations behind feature flag.

---

## Milestone 7 — Rollout

Plan
1) Apply migration with writes disabled (flag off).  
2) Enable in dev; verify metrics, payload sizes, and latency.  
3) Canary in one guild; monitor error rates and DB growth.  
4) Gradual prod rollout; confirm p95 latency unchanged.

Rollback
- Disable via features.activity_log=false (no redeploy).
- Data retained; reads unaffected.

---

## Data Guidelines

- event_type: string constants; enforce via code-level allowlist.
- source_ref/target_ref: compact, stable identifiers; avoid PII.
- summary: single-line, human-readable; keep short.
- payload: essential mechanics only; avoid raw prompts or large blobs.

---

## Risks and Mitigations

- Payload bloat → clamps, redaction, minimal fields.
- Double logging → correlation_id guidance, call-site dedupe.
- Latency impact → logging runs post-defer, minimal DB round-trips.
- Query needs evolve → start with flexible payload; add indexes iteratively.

---

## Future Extensions

- Typed payload schemas (Pydantic v2) per event_type with strict validation.
- Materialized views for analytics; dashboards for GM tooling.
- Rewind/redo based on ActivityLog replay.
- Retention/archival policy per campaign.
- UI components rendering ActivityLog with icons by event_type.

---