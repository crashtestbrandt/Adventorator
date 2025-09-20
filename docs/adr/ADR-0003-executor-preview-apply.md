# Architecture Decision Record (ADR)

## Title
ADR-0003 — Executor preview/apply lifecycle and event ledger integration

## Status
Accepted — 2024-05-09 (Owner: Adventure Systems WG)

## Context
The executor manages tool chain previews (dry-run) and applies (state mutation) for actions produced by the orchestrator. Encounter rollout and core system hardening require a contract-first definition for tool chains, confirmation flows, and event logging so that feature flags can be graduated safely and audits can replay state changes.

## Decision
- Tool chains are serialized as ordered lists of `ToolStep` objects (`tool`, `args`, `requires_confirmation`, `visibility`).
- Validation occurs through the `ToolRegistry`; schemas live alongside tool definitions and are versioned under `contracts/executor/toolchain.v{n}.json`.
- Preview runs never mutate state and emit `executor.preview.*` metrics; apply runs append events to `models.Event` with the serialized tool chain payload.
- Feature flag `features.executor_confirm` must remain enabled for mutating steps; without confirmation, apply is rejected.
- Concurrency is enforced via advisory locks keyed by encounter or resource identifiers; lock metrics feed observability budgets.

## Rationale
- Contract-first schemas support consumer-driven tests, ensuring new tools or args remain backward compatible.
- Persisting tool chains in the event ledger enables deterministic replay, fulfilling compliance and troubleshooting needs.
- Mandatory confirmation for mutating actions reduces accidental state corruption while maintaining auditable consent.

## Consequences
- Positive: Reliable preview/apply semantics, reproducible event trail, alignment with encounter turn engine requirements.
- Negative: Additional complexity around schema versioning and lock management.
- Future: Evaluate partial apply support or batched confirmations once encounter scale increases.

## References
- [EPIC-CORE-001 — Core AI Systems Hardening](../implementation/epics/core-ai-systems.md)
- [EPIC-ENC-002 — Encounter Turn Engine Rollout](../implementation/epics/encounter-turn-engine.md)
- Executor module: [`src/Adventorator/executor.py`](../../src/Adventorator/executor.py)
- Events ledger: [`src/Adventorator/models.py`](../../src/Adventorator/models.py)

## Integration with Action Validation (2025-09)
ARCH-AVA-001 introduces `ExecutionRequest` as the canonical, auditable container emitted by the Orchestrator before executor preview/apply operations.

| Previous Assumption | Updated Model | Rationale |
| ------------------- | ------------- | --------- |
| Orchestrator passes ToolChain directly | Orchestrator passes `ExecutionRequest.steps` (PlanStep → ToolStep mapping) | Decouples policy/feasibility from execution transport. |
| Preview/apply aware only of ToolSteps | Preview/apply accept `ExecutionRequest` and derive ToolSteps | Supports future MCP server substitution & replay fidelity. |
| Event ledger stores raw ToolChain | Event ledger stores serialized `ExecutionRequest` plus resulting events | Strengthens replay + ActivityLog correlation. |

ActivityLog Alignment:
- When enabled (Phase 6 AVA), approvals create ActivityLog entries referencing `ExecutionRequest.plan_id`.
- Executor append operations include the ActivityLog ID for joined analytics and rollback inspection.

MCP Adapters:
- Early phases keep adapters in-process; this ADR inherits their evolution without contract change.
- Future out-of-process MCP servers (rules/simulation) consume `ExecutionRequest` invariants, not legacy ToolChain structures.

Migration Steps:
1. Treat incoming legacy ToolChain payloads as transitional; wrap them into `ExecutionRequest` for internal processing.
2. Ensure new tools register schemas under the unified contracts namespace referenced by both `PlanStep` and `ExecutionRequest`.
3. Add metrics: `executor.execution_request.steps.count`, `executor.execution_request.preview.seconds`, `executor.execution_request.apply.seconds`.

Deprecated Terminology: Direct cross-layer references to “ToolChain from Orchestrator” should be updated to “ExecutionRequest”.
