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
