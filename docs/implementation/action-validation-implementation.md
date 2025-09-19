# Implementation Plan — Action Validation Architecture

> **Traceability**
> - Architecture: [ARCH-AVA-001 — Action Validation Architecture](../architecture/action-validation-architecture.md)
> - Epic: [EPIC-AVA-001 — Action Validation Pipeline Enablement](./epics/action-validation-architecture.md)
> - Workflow Templates: [Feature Epic](../../.github/ISSUE_TEMPLATE/feature_epic.md), [Story](../../.github/ISSUE_TEMPLATE/story.md), [Task](../../.github/ISSUE_TEMPLATE/task.md)

The phases below correspond to Story-level slices captured in [EPIC-AVA-001](./epics/action-validation-architecture.md). Each story aggregates the Definition of Ready/Done expectations from the AIDD framework and references the tasks enumerated here.

## Phase Breakdown


Phase 0 — Contracts, Shims, and Flags *(Story: STORY-AVA-001A)*
Goal: Introduce the new data contracts and interop shims without breaking current flows.

- Add schemas (no behavior change)
  - New module with Pydantic v2 models mirroring section 5 of the design: IntentFrame, AskReport, Plan, PlanStep, ExecutionRequest, ExecutionResult.
  - Provide converters to/from existing types:
    - Planner: to/from `Adventorator.planner_schemas.PlannerOutput`.
    - Orchestrator: to/from its LLM output types inside `Adventorator.orchestrator.run_orchestrator`.
    - Executor: to/from `Adventorator.executor.ToolStep` and the ToolCallChain.
- Feature flags
  - Add flags in config.toml: features.action_validation, features.predicate_gate, features.mcp (all default false).
- Tests
  - Round-trip conversions (legacy → new → legacy) are identity-safe for common cases (roll/check/attack).
- Rollback
  - Flip features.action_validation=false to keep legacy shapes end-to-end.

Phase 1 — Logging and Metrics Foundations (defensible by design) *(Story: STORY-AVA-001B)*
Goal: Ensure traceability for all new decisions while staying within existing logging patterns.

- Planner and orchestrator logging
  - Confirm existing logs in `Adventorator.planner.plan` and `Adventorator.orchestrator.run_orchestrator` align with the logging plan in logging-improvement-plan-overview.md (initiated/completed, rejection reasons, durations).
- Add counters
  - planner.allowlist.rejected, predicate.gate.ok/error, plan.steps.count.
- Tests
  - Unit: assert metrics via metrics.reset_counters()/get_counter().
- Rollback
  - Logging only; no user-visible changes.

Phase 2 — Planner Interop: “Plan” as internal representation *(Story: STORY-AVA-001C)*
Goal: Keep the existing planner behavior but represent the decision as a Plan with single-step semantics.

- Planner returns Plan (behind flag)
  - Wrap the existing `Adventorator.planner.plan` result into a single-step Plan (Level 1 in the design) with an op mirroring the target command (e.g., roll/check/do).
  - Preserve the allowlist already enforced by the planner and command option validation in `Adventorator.commands.plan.plan_cmd`.
- Dispatcher continuation
  - In `Adventorator.commands.plan.plan_cmd`, when features.action_validation=true, log and store the Plan but continue dispatching via today’s command handlers (no change in user-visible behavior).
- Tests
  - Ensure cached decisions still hit `_cache_get/_cache_put` in `Adventorator.planner` and route identically for roll/check/do.
- Rollback
  - Flip feature flag off; planner returns legacy output.

Phase 3 — Orchestrator adopts ExecutionRequest (shimmed) *(Story: STORY-AVA-001D)*
Goal: Populate an ExecutionRequest from orchestrator decisions without changing executor behavior.

- Internal mapping
  - Inside `Adventorator.orchestrator.run_orchestrator`, when features.action_validation=true, convert the approved (defended) result into ExecutionRequest (a single PlanStep today).
  - Maintain all current defenses: ability whitelist, DC bounds, banned verbs, unknown actors. Keep existing counters and logs (llm.defense.rejected).
- Formatting path
  - Preserve user-facing preview text exactly; ExecutionRequest exists only in-memory/logs.
- Tests
  - Unit: Orchestrator rejection paths carry reason fields and preserve today’s counters.
- Rollback
  - Disable features.action_validation; no ExecutionRequest created.

Phase 4 — Executor interop with ExecutionRequest (no API break) *(Story: STORY-AVA-001E)*
Goal: Validate ExecutionRequest → ToolCallChain → Executor path and keep dry-run/apply behavior unchanged.

- Adapter
  - Add a thin adapter (module-level function) that converts ExecutionRequest to the current ToolCallChain and ToolStep shapes used by `Adventorator.executor.Executor` and `Adventorator.tool_registry`.
- Idempotency and bounds
  - Reuse existing idempotency/dedup patterns and argument clamps already present in executor tools (e.g., attack bounds in `Adventorator.executor.Executor`).
- Tests
  - Integration: orchestrator builds ExecutionRequest → adapter → executor.dry_run produces identical previews for roll/check; where enabled, confirm/apply still append events.
- Rollback
  - Remove adapter usage by flag; executor continues with legacy ToolCallChain.

Phase 5 — Predicate Gate v0 (read-only, in-process) *(Story: STORY-AVA-001F)*
Goal: Introduce a fast “Predicate Gate” with deterministic checks that do not call external services.

- Predicates module
  - Implement simple read-only predicates using repos/rules: exists(actor), exists(target), known_ability, dc_in_bounds, actor_in_allowed_actors.
  - No DB writes; only reads through repos helpers (wrap in async with session_scope() if needed).
- Planner invocation
  - Before building the Plan, evaluate selected predicates; if any fail, set feasible=false with failed_predicates and no steps. Keep existing planner allowlist and option model validation.
- Tests
  - Unit: each predicate has clear pass/fail tests with seeded data; planner returns infeasible plans correctly.
- Rollback
  - Gate behind features.predicate_gate; off → bypass predicates.

Phase 6 — ActivityLog integration (defensible audit of mechanics) *(Story: STORY-AVA-001G)*
Goal: Record mechanics decisions in a structured ledger as we evolve planning/execution.

- Adopt the plan in ActivityLog-plan-overview.md.
  - When an ExecutionRequest is approved (even if not applied), write a compact ActivityLog row describing mechanics preview (no prompts, no large blobs).
  - Link transcripts to ActivityLog ids when mechanics drive the bot message.
- Tests
  - E2E: /roll, /check produce ActivityLog with stable payloads; counters increment.
- Rollback
  - Keep writes disabled via feature flag; fall back to logs/metrics only.

Phase 7 — MCP scaffold (local, in-process servers) *(Story: STORY-AVA-001H)*
Goal: Establish the boundary and contracts without networking complexity.

- MCP interface shape
  - Define a minimal MCP interface (sync/async Python callables) for:
    - rules.apply_damage, rules.roll_attack, rules.compute_check (read-only and write-preview).
    - sim.raycast (placeholder, returns not_implemented).
  - Implement “servers” as plain modules calling the existing rules in rules.
- Executor as MCP client
  - Swap tool handlers to call MCP adapters internally (function calls). No network I/O yet; same determinism.
- Tests
  - Unit: MCP adapter results match direct rules engine calls; same seeds → same outcomes.
- Rollback
  - features.mcp=false keeps the direct rules path.

Phase 8 — Tiered Planning scaffold (Level 1 only) *(Story: STORY-AVA-001I)*
Goal: Prepare for multi-step planning while keeping current single-step behavior.

- Plan.step generation policy
  - Maintain Level 1 (single operator) as default.
  - Add scaffolding for Level 2 later (HTN) but explicitly disabled by flag; include placeholders for guards on steps.
- Tests
  - Plan serialization/stability; guards array present and well-formed (even if empty).
- Rollback
  - Only Level 1 enabled; HTN code paths remain dead code with tests.

Phase 9 — Ops hardening and rollout *(Story: STORY-AVA-001J)*
Goal: Safe rollout with clear rollback paths and observability.

- Timeouts and bounds
  - Apply soft timeouts to planner/orchestrator calls; preserve the fallback behavior (e.g., safe /roll 1d20).
  - Enforce size caps on Plan, ExecutionRequest, ActivityLog payloads (clamp/redact as needed).
- Metrics
  - planner.feasible/infeasible, predicate.gate.fail_reason, executor.preview/apply, activity_log.created/failed.
- Rollout
  - Dev: enable features.action_validation=true, features.predicate_gate=true; shadow test in a dev guild.
  - Canary: enable in one guild; monitor counters and p95 preview/apply latency.
  - GA: enable broadly; retain flags for rapid rollback.

Mapping from current code to target concepts
- AskReport: Not introduced yet; can be an optional pre-step before planner. For now, rely on existing planner input string and extend later (flagged) inside `Adventorator.planner.plan`.
- Plan/PlanStep: Introduced in Phase 0 and used (behind flags) starting Phase 2.
- ExecutionRequest/ExecutionResult: Introduced in Phase 0; adapted into ToolCallChain for `Adventorator.executor.Executor` in Phase 4.
- Predicate Gate: Implemented in-process in Phase 5; kept minimal and deterministic; invoked by planner.
- MCP: Internal adapters in Phase 7; no network boundary until future work.
- Auditing: ActivityLog in Phase 6; complements existing events ledger created by executor apply.

Acceptance criteria (per phase)
- Contracts (Phase 0): Round-trip conversions succeed; no user-visible changes.
- Planner interop (Phase 2): /plan routes identically; Plan logged; cache still effective.
- Orchestrator (Phase 3): ExecutionRequest produced; defenses unchanged; counters stable.
- Executor (Phase 4): Previews and apply paths identical to baseline on seeded runs.
- Predicates (Phase 5): Infeasible plans blocked with clear reasons; no false positives in existing tests.
- ActivityLog (Phase 6): Mechanics consistently captured; no PII; payload bounds enforced.
- MCP (Phase 7): Deterministic parity with rules; no latency regressions.
- Rollout (Phase 9): Canary metrics healthy; rollback flips flags to prior behavior.

Key implementation touchpoints (files/symbols)
- Edge/dispatch:
  - app.py
  - command_loader.py, commanding.py
- Planner:
  - `Adventorator.planner.plan`
  - plan.py
- Orchestrator:
  - `Adventorator.orchestrator.run_orchestrator`
- Execution:
  - `Adventorator.executor.Executor`
  - tool_registry.py
- Rules:
  - dice.py, checks.py, engine.py
- Observability:
  - logging-improvement-plan-overview.md
  - ActivityLog-plan-overview.md

Why this is defensive and defensible
- Deterministic-first: Predicates and MCP adapters use existing deterministic rules.
- Strict validation: Commands still validate via option models; planner allowlist unchanged.
- Deep logs/metrics: Standardized initiated/completed and rejection logs; fine-grained counters.
- Safe rollbacks: Every phase is behind feature flags; flipping them restores current behavior.
- Testability: Unit/integration/E2E coverage grows per phase; seeded RNG ensures reproducibility.