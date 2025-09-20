# EPIC-ACTLOG-001 — Mechanics ActivityLog Enablement

**Objective.** Establish a structured, auditable ActivityLog for mechanics (dice rolls, checks, orchestrator-approved actions) with phased rollout, defensive guarantees, and minimal latency impact.

**Owner.** ActivityLog working group (data, mechanics, observability maintainers).

**Key risks.** Payload bloat / storage growth, double logging, latency regression from synchronous writes, schema drift without taxonomy governance, insufficient redaction.

**Linked assets.**
- ARCH-AVA-001 — Action Validation Architecture (ActivityLog integration phases)
- EPIC-AVA-001 — Action Validation Pipeline (depends on Phase 2+ of this epic for auditable mechanics)
- Observability & Feature Flags guide

**Definition of Ready.** Stories must list event types introduced/changed, planned indexes, migration impact, and rollback toggles.

**Definition of Done.**
- Feature flag `features.activity_log` governs all writes; disabling flag is a safe rollback.
- Schema version, taxonomy, and redaction rules documented and tested.
- Logs & metrics emitted match observability guide.
- E2E determinism and latency budgets validated.

---
## Stories

### STORY-ACTLOG-001A — Flag, taxonomy, and actor reference scaffold
*Milestone 0*
- **Summary.** Introduce feature flag, event taxonomy, and actor/reference formats.
- **Acceptance criteria.**
  - `features.activity_log` added (default false) and surfaced in settings docs.
  - Event taxonomy (dice.roll, check.ability, orchestrator.mechanics) documented with owners.
  - Actor/target identifier format (char:<id>, user:<discord>, npc:<key>) adopted.
- **Tasks.**
  - [ ] `TASK-ACTLOG-FLAG-01` — Add flag + settings wiring + doc update.
  - [ ] `TASK-ACTLOG-TAX-02` — Draft taxonomy doc section.
  - [ ] `TASK-ACTLOG-ACTOR-03` — Implement helper for stable actor/target refs.

### STORY-ACTLOG-001B — Schema and repository foundations
*Milestone 1*
- **Summary.** Create DB model, migration, and repository helper with redaction hooks.
- **Acceptance criteria.**
  - Alembic migration adds `activity_log` table + indexes.
  - Model fields: id, event_type, summary, payload (JSON), correlation_id, scene_id, campaign_id, actor_ref, target_ref, created_at (UTC).
  - Repository helper enforces size clamps & redaction.
- **Tasks.**
  - [ ] `TASK-ACTLOG-MIG-04` — Migration + downgrade path.
  - [ ] `TASK-ACTLOG-MODEL-05` — Pydantic/ORM model & indices.
  - [ ] `TASK-ACTLOG-HELPER-06` — Repo helper with redaction & caps.
  - [ ] `TASK-ACTLOG-TEST-07` — Unit tests: create/read, UTC timestamp.

### STORY-ACTLOG-001C — Initial mechanics integration (/roll, /check, orchestrator)
*Milestone 2*
- **Summary.** Log core mechanics sources non-invasively post-defer.
- **Acceptance criteria.**
  - /roll & /check produce ActivityLog rows when flag enabled.
  - Orchestrator mechanics path logs once per approval.
  - No user-visible message changes.
- **Tasks.**
  - [ ] `TASK-ACTLOG-ROLL-08` — Integrate /roll logging.
  - [ ] `TASK-ACTLOG-CHECK-09` — Integrate /check logging.
  - [ ] `TASK-ACTLOG-ORCH-10` — Orchestrator logging hook.
  - [ ] `TASK-ACTLOG-INTEG-11` — Integration tests for basic events.

### STORY-ACTLOG-001D — Transcript linkage & narrative decoupling
*Milestone 3*
- **Summary.** Link transcripts to ActivityLog entries while keeping narrative text independent.
- **Acceptance criteria.**
  - Transcript.activity_log_id populated only for mechanics-driven bot messages.
  - Transcript content remains narrative-only (no raw mechanics payload duplication).
- **Tasks.**
  - [ ] `TASK-ACTLOG-LINK-12` — Add nullable FK / column + migration update if needed.
  - [ ] `TASK-ACTLOG-POP-13` — Populate linkage in handlers.
  - [ ] `TASK-ACTLOG-TRANS-14` — Tests verifying linkage & unchanged transcript content.

### STORY-ACTLOG-001E — Defensive logging (caps, redaction, idempotency)
*Milestone 4*
- **Summary.** Apply payload caps, redaction rules, correlation/idempotency guidance.
- **Acceptance criteria.**
  - Size clamp & key redaction enforced (tests prove truncation/redaction).
  - correlation_id reused per interaction; no duplicate rows in concurrency tests.
  - Failures degrade silently with metric increments.
- **Tasks.**
  - [ ] `TASK-ACTLOG-CLAMP-15` — Implement size clamp + tests.
  - [ ] `TASK-ACTLOG-REDACT-16` — Redaction rules + tests.
  - [ ] `TASK-ACTLOG-IDEMP-17` — correlation_id guidance & duplicate prevention tests.
  - [ ] `TASK-ACTLOG-CHAOS-18` — Chaos / failure injection tests (degrade, not fail request).

### STORY-ACTLOG-001F — Metrics & structured logs
*Milestone 5*
- **Summary.** Emit counters and structured logs with stable field sets.
- **Acceptance criteria.**
  - Metrics: activity_log.created, activity_log.failed, activity_log.linked_to_transcript.
  - Logs include event_type, correlation_id, scene_id, campaign_id, actor_ref, target_ref, payload_size.
- **Tasks.**
  - [ ] `TASK-ACTLOG-METRIC-19` — Register counters & tests.
  - [ ] `TASK-ACTLOG-LOG-20` — Structured logging additions.
  - [ ] `TASK-ACTLOG-OBS-21` — Observability doc updates + dashboard mock.

### STORY-ACTLOG-001G — Test matrix & determinism
*Milestone 6*
- **Summary.** Establish unit/integration/E2E determinism + RNG seeding & UTC assertions.
- **Acceptance criteria.**
  - Unit: helper redaction/clamp determinism.
  - Integration: /roll, /check, orchestrator produce consistent rows.
  - E2E: seeded tests stable on CI (no flake).
- **Tasks.**
  - [ ] `TASK-ACTLOG-RNG-22` — Seed & deterministic harness.
  - [ ] `TASK-ACTLOG-E2E-23` — E2E test suite for ActivityLog.
  - [ ] `TASK-ACTLOG-FLAKE-24` — Flakiness guard (retry or timing instrumentation).

### STORY-ACTLOG-001H — Staged rollout & latency guardrails
*Milestone 7*
- **Summary.** Progressive enablement with latency & storage monitoring.
- **Acceptance criteria.**
  - Rollout plan stages (dev → canary guild → wider) documented with abort triggers.
  - p95 interaction latency unchanged (< defined budget) when enabled.
  - Storage growth tracked; threshold alert defined.
- **Tasks.**
  - [ ] `TASK-ACTLOG-RUNBOOK-25` — Rollout / rollback runbook.
  - [ ] `TASK-ACTLOG-LAT-26` — Latency measurement instrumentation & test.
  - [ ] `TASK-ACTLOG-STORAGE-27` — Storage monitoring guidance + alert config stub.

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Dependency Epic | EPIC-AVA-001 | AVA Phase 6 (Story 001G) depends on ActivityLog phases A–D completion. |
| Story 001A | (pending issue) | Flag, taxonomy, actor ref. |
| Story 001B | (pending issue) | Schema + repo foundations. |
| Story 001C | (pending issue) | Initial mechanics integration. |
| Story 001D | (pending issue) | Transcript linkage. |
| Story 001E | (pending issue) | Defensive logging. |
| Story 001F | (pending issue) | Metrics & structured logs. |
| Story 001G | (pending issue) | Test matrix & determinism. |
| Story 001H | (pending issue) | Staged rollout & latency. |

Update with GitHub issue numbers upon creation.
