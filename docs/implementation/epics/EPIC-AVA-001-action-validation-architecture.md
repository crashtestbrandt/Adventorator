# EPIC-AVA-001 — Action Validation Pipeline Enablement

**Objective.** Deliver the Action Validation pipeline so free-form player intent is validated deterministically before execution, while preserving current `/plan → /do` behavior behind feature flags.

**Owner.** Action Validation working group (planner/orchestrator/executor maintainers, observability, and contracts).

**Key risks.** Schema drift between legacy and new contracts, insufficient telemetry to defend AI-assisted decisions, and rollout regressions when feature flags enable new behavior.

**Linked assets.**
- [ARCH-AVA-001 — Action Validation Architecture](../../architecture/action-validation-architecture.md)
- [Implementation Plan — Action Validation Architecture](../action-validation-implementation.md)
- [AIDD DoR/DoD Rituals](../dor-dod-guide.md)

**Definition of Ready.** Stories must satisfy the cross-team DoR plus:
- Planned contract deltas enumerated with proposed versioning strategy.
- Updated feature flag rollout plan with rollback toggles.
- Test strategy covering schema parity and regression expectations.

**Definition of Done.**
- Contracts, prompts, and feature flags referenced in Story issues are merged and linked here.
- Quality gates (format, lint, type, test) run green with new assets included.
- Observability updates documented in relevant guides (logging, ActivityLog, metrics) with owners noted.

## Stories

### STORY-AVA-001A — Contracts and feature flag scaffolding
*Epic linkage:* Establishes data contracts and defensive flags before behavior changes.

- **Summary.** Introduce the canonical Action Validation schemas, converters, and flags to support phased rollout.
- **Acceptance criteria.**
  - New Pydantic v2 models align with ARCH-AVA-001 contracts.
  - Legacy planner, orchestrator, and executor paths round-trip through adapters without regressions.
  - Feature flags (`features.action_validation`, `features.predicate_gate`, `features.mcp`) default to safe/off values.
- **Tasks.**
  - [x] `TASK-AVA-SCHEMA-01` — Implement IntentFrame/AskReport/Plan/PlanStep/ExecutionRequest/ExecutionResult models and serialization helpers.
  - [x] `TASK-AVA-CONVERT-02` — Add converters bridging legacy planner/orchestrator/executor types to the new contracts.
  - [x] `TASK-AVA-FLAGS-03` — Extend `config.toml` and config dataclasses with Action Validation feature flags and documentation.
  - [x] `TASK-AVA-TEST-04` — Add round-trip tests covering roll/check/attack flows to validate adapters.
- **DoR.**
  - Contract change proposal reviewed with planner/orchestrator maintainers.
  - Test plan outlines identity fixtures for roll/check/attack cases.
- **DoD.**
  - Conversion tests committed with deterministic fixtures.
  - Flag documentation updated in feature flag guide.

### STORY-AVA-001B — Logging and metrics foundations
*Epic linkage:* Ensures early instrumentation aligns with defensibility requirements.

- **Summary.** Align planner/orchestrator logging with observability strategy and add foundational counters.
- **Acceptance criteria.**
  - Planner/orchestrator logs cover initiated/completed events and rejection reasons per logging plan.
  - Metrics counters (`planner.allowlist.rejected`, `predicate.gate.ok/error`, `plan.steps.count`) recorded and documented.
  - Unit tests assert metric increments via reset/get helpers.
- **Tasks.**
  - [x] `TASK-AVA-LOG-05` — Audit planner/orchestrator logs and add structured events per logging plan alignment.
  - [x] `TASK-AVA-METRIC-06` — Register counters for planner and predicate gate outcomes with taxonomy updates.
  - [x] `TASK-AVA-TEST-07` — Create unit tests validating logging hooks and metric counters fire as expected.
- **DoR.**
  - Observability acceptance criteria reviewed with logging maintainers.
  - Metric naming vetted against observability guide.
- **DoD.**
  - Logging guide references new events and owners.
  - Metrics documented in observability and dashboards story attachments.

### STORY-AVA-001C — Planner returns Plan contract
*Epic linkage:* Wraps existing planner output in the new Plan representation.

- **Summary.** Represent planner decisions as single-step Plans while maintaining current dispatch behavior.
- **Acceptance criteria.**
  - `/plan` returns a Plan (behind feature flag) with single-step semantics mirroring legacy responses.
  - Plan logging and caching remain identical to baseline behavior.
  - Dispatcher continues using existing handlers with Plan stored for observability.
- **Tasks.**
  - [x] `TASK-AVA-PLAN-08` — Wrap planner results into Plan objects with deterministic plan_id generation.
  - [x] `TASK-AVA-CMD-09` — Update `/plan` command handler to persist/log Plans while dispatching legacy flows.
  - [x] `TASK-AVA-CACHE-10` — Confirm cache hit/miss behavior with Plan integration through tests.
- **DoR.**
  - Planner prompt/catalog updates (if any) reviewed and linked.
  - Cache regression scenarios enumerated with expected outputs.
- **DoD.**
  - Plan serialization documented in architecture appendix or code comments.
  - Tests confirm cache operations unaffected by flag.

### STORY-AVA-001D — Orchestrator ExecutionRequest shim
*Epic linkage:* Converts orchestrator decisions into ExecutionRequests without altering user previews.

- **Summary.** Translate orchestrator approvals into ExecutionRequest payloads while preserving existing defenses and outputs.
- **Acceptance criteria.**
  - When flag enabled, orchestrator produces ExecutionRequest objects with parity to legacy ToolCallChain data.
  - User-facing previews remain unchanged.
  - Rejection counters and logs remain stable.
- **Tasks.**
  - [x] `TASK-AVA-ORCH-11` — Map orchestrator approvals to ExecutionRequest structures with drift checks.
  - [x] `TASK-AVA-PREVIEW-12` — Ensure preview rendering uses existing formatting paths while logging ExecutionRequests.
  - [x] `TASK-AVA-REJECT-13` — Validate rejection analytics remain accurate with new data structures.
- **DoR.**
  - Updated orchestrator contract documented and reviewed with stakeholders.
  - Test cases prepared for approval, repair, and rejection flows.
- **DoD.**
  - ExecutionRequest logging included in observability docs.
  - Regression suite confirms zero diff in preview output.

### STORY-AVA-001E — Executor adapter interoperability
*Epic linkage:* Bridges ExecutionRequest payloads into the executor ToolCallChain.

- **Summary.** Implement adapter logic converting ExecutionRequests into existing executor structures without API breaks.
- **Acceptance criteria.**
  - Adapter converts ExecutionRequest → ToolCallChain for both dry-run and apply paths.
  - Idempotency keys and argument clamps reused without duplication.
  - Integration tests confirm parity for roll/check scenarios.
- **Tasks.**
  - [x] `TASK-AVA-EXEC-14` — Build adapter functions translating ExecutionRequest into ToolCallChain/ToolStep.
  - [x] `TASK-AVA-IDEMP-15` — Reuse existing idempotency/deduplication logic within adapter path.
  - [x] `TASK-AVA-INTEG-16` — Add integration tests verifying dry-run/apply parity with adapter enabled.
- **DoR.**
  - Executor maintainers sign off on adapter design.
  - Test fixtures prepared for preview/apply comparisons.
- **DoD.**
  - Adapter code documented with rollback instructions.
  - Integration tests run in CI and linked to Story issue.

### STORY-AVA-001F — Predicate Gate v0 rollout
*Epic linkage:* Introduces deterministic feasibility checks prior to planning.

- **Summary.** Implement a read-only Predicate Gate with minimal predicates and integrate it into the planner behind a flag.
- **Acceptance criteria.**
  - Predicate module exposes documented functions for `exists`, `known_ability`, `dc_in_bounds`, and `actor_in_allowed_actors`.
  - Planner marks plans infeasible with failed predicate metadata when checks fail.
  - Unit tests cover pass/fail scenarios using seeded data.
- **Tasks.**
  - [x] `TASK-AVA-PRED-17` — Implement predicate module leveraging repos/rules helpers.
  - [x] `TASK-AVA-PLUG-18` — Invoke Predicate Gate within planner when feature flag enabled.
  - [x] `TASK-AVA-UNIT-19` — Write unit tests for predicates and planner infeasible responses.
- **DoR.**
  - Data fixtures defined for predicate evaluation.
  - Rollback plan validated (flag disable).
- **DoD.**
  - Predicate documentation added to architecture or dev notes.
  - Tests demonstrate deterministic results.

### STORY-AVA-001G — ActivityLog integration dependency
*Epic linkage:* Depends on Mechanics ActivityLog Enablement (EPIC-ACTLOG-001) for auditable mechanics from Phase 6 onward.

- **Summary.** Action Validation requires ActivityLog stories (ACTLOG 001A–001D minimum) to supply durable, queryable mechanics records (ExecutionRequest approvals, /roll, /check) and transcript linkage. Detailed milestones, tasks, and defenses live in EPIC-ACTLOG-001.
- **Acceptance criteria (delegated).**
  - ActivityLog epic Stories 001A–001D completed (flag, schema, initial integrations, transcript linkage).
    - Status tracked in [EPIC-ACTLOG-001](activitylog-mechanics-ledger.md) with DoR/DoD checklists marked complete.
  - Feature flag `features.activity_log` remains a rollback lever; AVA tests pass with flag on/off (`tests/test_action_validation_activity_log_phase6.py::test_roll_command_activity_log_toggle`).
  - Cross-epic traceability updated when ActivityLog issue numbers created and validated via shared test coverage for orchestrator, `/check`, and `/roll` integrations (`tests/test_action_validation_activity_log_phase6.py`).
- **Tasks (tracked in ACTLOG epic).** Former local tasks migrated and reissued with ACTLOG prefixes.
- **DoR.** ActivityLog epic has approved taxonomy, migration, and privacy review.
- **DoD.** AVA E2E tests observe stable ActivityLog payloads; observability docs link to ActivityLog metrics section.

### STORY-AVA-001H — MCP adapter scaffold
*Epic linkage:* Prepares executor tooling for eventual external MCP services.

- **Summary.** Define the MCP adapter shape and route executor tool calls through in-process MCP client shims.
- **Acceptance criteria.**
  - Minimal MCP interface defined for rules.apply_damage, rules.roll_attack, rules.compute_check, and sim.raycast placeholder.
  - Executor uses MCP adapters internally without network I/O when flag enabled.
  - Unit tests compare MCP adapter results with direct rules calls.
- **Tasks.**
  - [x] `TASK-AVA-MCP-23` — Specify MCP interface modules and placeholder implementations. In-process adapters live under `src/Adventorator/mcp/` with contracts versioned in `contracts/mcp/`.
  - [x] `TASK-AVA-EXEC-24` — Update executor tool handlers to call MCP adapters when flag enabled. `Executor` now resolves checks, attacks, and damage via `MCPClient` when `features.mcp` is true.
  - [x] `TASK-AVA-TEST-25` — Add tests confirming MCP adapters produce identical results to direct calls (`tests/test_mcp_executor_parity.py`).
- **DoR.**
  - MCP contract reviewed with systems architecture stakeholders.
  - Test comparison cases enumerated.
- **DoD.**
  - MCP adapter documentation added to architecture doc.
  - Tests run in CI covering adapter parity (`tests/test_mcp_executor_parity.py`).

### STORY-AVA-001I — Tiered planning scaffolding
*Epic linkage:* Lays groundwork for multi-step planning while keeping Level 1 behavior.

- **Summary.** Introduce scaffolding for higher-tier planning and ensure Plan serialization supports guards metadata.
- **Acceptance criteria.**
  - Level 1 remains default with explicit placeholders for HTN/GOAP expansions.
  - PlanStep `guards` populated (possibly empty) with serialization stability tests.
  - Feature flag disables Level 2+ paths.
- **Tasks.**
  - [ ] `TASK-AVA-TIER-26` — Implement tier selection scaffolding with flags controlling Level 2/3 entry points.
  - [ ] `TASK-AVA-GUARD-27` — Populate guards metadata and document serialization expectations. *(PlanStep `guards` field exists but remains empty in practice.)*
  - [ ] `TASK-AVA-TEST-28` — Add tests ensuring Plan serialization stability and guards formatting.
- **DoR.**
  - Planning roadmap for Level 2/3 reviewed and documented.
  - Serialization changes communicated to downstream consumers.
- **DoD.**
  - Documentation updated describing tier behavior and guard semantics.
  - Tests stored with golden fixtures verifying Plan JSON.

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | [#124](https://github.com/crashtestbrandt/Adventorator/issues/124) | EPIC-AVA-001 Action Validation Pipeline Enablement. |
| Story 001G | [#131](https://github.com/crashtestbrandt/Adventorator/issues/131) | STORY-AVA-001G ActivityLog mechanics capture. Tasks: #154 |

Update the table as GitHub issues are created to preserve AIDD traceability.
