# EPIC-CORE-001 — Core AI Systems Hardening

**Objective.** Ensure the `/plan → /do` flow couples AI assistance with deterministic execution so players receive safe, repeatable outcomes.

**Owner.** Adventure Systems working group (planner/orchestrator/executor maintainers).

**Key risks.** Prompt drift, contract regressions in tool schemas, and insufficient observability for quality gates.

**Linked assets.**
- [ADR-0001 — Planner routing contract](../../adr/ADR-0001-planner-routing.md)
- [ADR-0002 — Orchestrator defenses](../../adr/ADR-0002-orchestrator-defenses.md)
- [ADR-0003 — Executor preview/apply contract](../../adr/ADR-0003-executor-preview-apply.md)
- [Core systems C4 context](../../architecture/core-systems-context.md)

**Definition of Ready.** Stories must meet cross-team DoR plus:
- Contract deltas enumerated with version impacts (catalog governance lives in ADR-0001; do not restate mechanics here).
- Updated prompts committed with version tags referencing catalog version.
- Rollback plan for affected feature flags.

**Definition of Done.** Beyond the repo-wide DoD, this epic requires:
- Contract tests for planner output, orchestrator defenses, and executor tool schemas run in CI.
- Observability budgets updated in [Observability & Feature Flags](../observability-and-flags.md).
- Links to live Story/Task issues added to this file.

## Stories

### STORY-CORE-001A — Planner command catalog health (superseded semantics)
*Epic linkage:* Keeps `/plan` outputs aligned with available commands.

- **Summary.** Ensure ongoing alignment with catalog (validation framework now standardized by Action Validation `Plan` abstraction; focus this story on maintenance and evaluation harness quality, not re-implementing feasibility predicates).
- **Acceptance criteria.**
  - Catalog refresh job detects new commands within CI runs.
  - Planner prompt references current command metadata; snapshot stored under `prompts/planner/`.
  - Failing validation blocks merge via quality gate.
- **Tasks.**
  - [ ] `TASK-CORE-VAL-01` — Generate command catalog contract and publish under `contracts/`
  - [ ] `TASK-CORE-PROMPT-02` — Refresh planner prompt and add evaluation harness
  - [ ] `TASK-CORE-QG-03` — Wire catalog validation into GitHub workflow
- **DoR.**
  - Linked issues list owners for each task.
  - Planned contract deltas reviewed with command registry maintainers.
- **DoD.**
  - Planner contract tests green in CI.
  - Prompt registry tag incremented and referenced from Story issue.
  - Observability docs updated with planner metrics guardrails.

### STORY-CORE-001B — Orchestrator defense coverage (align with Predicate Gate)
*Epic linkage:* Ensures AI narration is constrained by deterministic rules.

- **Summary.** Extend orchestrator defenses (policy layer) while avoiding duplication of deterministic feasibility handled by Predicate Gate (see STORY-AVA-001F).
- **Acceptance criteria.**
  - Defense matrix recorded in [ADR-0002](../../adr/ADR-0002-orchestrator-defenses.md) stays current.
  - Automated tests cover each rejection path and feed dashboards.
  - Observability budgets define rejection rate thresholds per scene type.
- **Tasks.**
  - [ ] `TASK-CORE-DEF-04` — Expand rejection unit tests and add fixtures for banned verbs
  - [ ] `TASK-CORE-OBS-05` — Emit structured metrics/logs for rejections with actor context
  - [ ] `TASK-CORE-DOC-06` — Update narrations doc with rejection troubleshooting
- **DoR.**
  - Linked Scenes/character data prepared for test fixtures.
  - Failure budget target agreed with product owner.
- **DoD.**
  - Metrics alert definitions committed to observability doc and dashboards.
  - Security review signs off on logged fields.
  - Story PR references validated ADR and contracts.

### STORY-CORE-001C — Executor deterministic replay (ExecutionRequest aware)
*Epic linkage:* Maintains integrity of preview/apply lifecycle.

- **Summary.** Capture executor tool chains (now emitted via `ExecutionRequest`) as immutable events and surface replay tooling.
- **Acceptance criteria.**
  - Events ledger records tool chains with versioned schema.
  - Replay CLI can regenerate previews for auditing.
  - Feature flag for executor enhancements documented with rollout steps.
- **Tasks.**
  - [ ] `TASK-CORE-SCHEMA-07` — Version executor tool chain schema and add CDC tests
  - [ ] `TASK-CORE-CLI-08` — Build CLI for replaying pending actions from transcripts
  - [ ] `TASK-CORE-FLAG-09` — Document rollout/rollback in feature flag guide
- **DoR.**
  - Contract review scheduled with data platform maintainers.
  - Replay tooling requirements approved by operations.
- **DoD.**
  - CDC tests green with golden fixtures.
  - Replay CLI documented and demo script checked into `docs/dev/`.
  - Feature flag entry contains monitoring and rollback triggers.

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | _Pending_ | Create via Feature Epic template and link here. |
| Story 001A | _Pending_ | Use Story template; ensure DoR/DoD fields reference this doc. |
| Story 001B | _Pending_ | "" |
| Story 001C | _Pending_ | "" |

Update the table as issues are opened so ADRs, stories, and tasks remain synchronized.
