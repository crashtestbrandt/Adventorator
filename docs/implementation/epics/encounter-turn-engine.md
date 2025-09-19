# EPIC-ENC-002 — Encounter Turn Engine Rollout

**Objective.** Graduate the encounter feature flag into a production-ready turn engine with clear observability and rollback levers.

**Owner.** Encounter mechanics maintainers with support from operations and data engineering.

**Key risks.** Concurrency hazards during apply, missing coverage for combatant state transitions, and insufficient telemetry for live monitoring.

**Linked assets.**
- [ADR-0003 — Executor preview/apply contract](../../adr/ADR-0003-executor-preview-apply.md)
- [Observability & Feature Flags](../observability-and-flags.md)
- [Encounters developer notes](../../dev/encounters.md)

**Definition of Ready.** Stories should meet [AIDD DoR/DoD Rituals](../dor-dod-guide.md) with emphasis on:
- Up-to-date schema diagrams for `encounters` and `combatants` tables.
- List of supporting prompts or contracts to version.
- Stakeholder sign-off on rollout metrics and abort criteria.

**Definition of Done.**
- Combat mechanics covered by integration tests recorded in Story issues.
- Observability dashboards updated per story acceptance criteria.
- Feature flag lifecycle documented with rollout + rollback commands.

## Stories

### STORY-ENC-002A — Initiative and turn validation
*Epic linkage:* Ensures deterministic transitions during setup and combat.

- **Summary.** Harden initiative ordering, active combatant selection, and concurrency controls.
- **Acceptance criteria.**
  - Database constraints prevent duplicate initiative rows per combatant.
  - Concurrency tests show idempotent turn advance operations.
  - Executor apply path records events for setup → active → ended transitions.
- **Tasks.**
  - [ ] `TASK-ENC-SCHEMA-01` — Document schema invariants and add Alembic migration guards
  - [ ] `TASK-ENC-TEST-02` — Extend integration tests for concurrent `next_turn` calls
  - [ ] `TASK-ENC-DOC-03` — Update encounters dev notes with troubleshooting flowchart
- **DoR.**
  - Proposed migration reviewed by database maintainers.
  - Test data sets enumerated for concurrency scenarios.
- **DoD.**
  - Tests capture before/after snapshots in `tests/integration/`.
  - Event ledger docs show emitted events for each transition.

### STORY-ENC-002B — Encounter observability and alerts
*Epic linkage:* Connects combat operations to metrics and dashboards.

- **Summary.** Define metrics, logs, and traces for encounter flows with budgets and alerts.
- **Acceptance criteria.**
  - Metrics taxonomy recorded in [Observability & Feature Flags](../observability-and-flags.md#encounter-observability-budget).
  - Grafana dashboard mock linked in Story issue; alert thresholds defined.
  - Logs include correlation IDs for encounters and combatants.
- **Tasks.**
  - [ ] `TASK-ENC-METRIC-04` — Publish encounter metric definitions and thresholds
  - [ ] `TASK-ENC-DASH-05` — Capture dashboard mockup and link to operations backlog
  - [ ] `TASK-ENC-LOG-06` — Document structured logging fields and scrub list
- **DoR.**
  - Stakeholders align on latency and failure budgets.
  - Data catalog updated with metric owners.
- **DoD.**
  - Dashboard PRD attached to Story issue.
  - Logging fields reviewed for PII and compliance.

### STORY-ENC-002C — Feature flag graduation plan
*Epic linkage:* Drives safe rollout of encounter capabilities.

- **Summary.** Create a staged rollout plan for the `combat` feature flag with kill-switch automation.
- **Acceptance criteria.**
  - Runbook defines percentage cohorts and monitoring requirements.
  - Automation script toggles flag across environments via configuration store.
  - Rollback steps validated in staging rehearsal.
- **Tasks.**
  - [ ] `TASK-ENC-RUNBOOK-07` — Write rollout/rollback runbook with escalation tree
  - [ ] `TASK-ENC-AUTO-08` — Script flag toggles and verify idempotency
  - [ ] `TASK-ENC-REHEARSE-09` — Record staging rehearsal checklist and outcomes
- **DoR.**
  - Stakeholders approve targeted cohorts.
  - Automation dependencies inventoried (config store, secrets).
- **DoD.**
  - Runbook linked in operations wiki and this epic doc.
  - Staging rehearsal captured with logs/screenshots stored in artifacts bucket.

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | _Pending_ | Create via Feature Epic template and link here. |
| Story 002A | _Pending_ | Use Story template referencing schema/contract attachments. |
| Story 002B | _Pending_ | Attach observability mock artifacts. |
| Story 002C | _Pending_ | Include flag automation script references. |

Update links when GitHub issues are created so downstream Tasks inherit traceability.
