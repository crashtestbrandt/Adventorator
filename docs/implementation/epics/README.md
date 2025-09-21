# Adventorator Feature Epics

This directory captures Feature Epics aligned with the AI-Driven Development (AIDD) pipeline. Each epic:

- Summarises player or operator outcomes and key risks.
- Links to authoritative architecture assets (C4 diagrams, ADRs, contracts).
- Breaks work into Story-sized slices with explicit Definition of Ready (DoR) and Definition of Done (DoD) gates.
- Enumerates per-prompt Tasks that agents and contributors can pick up independently.

Use the GitHub issue templates located in [`.github/ISSUE_TEMPLATE/`](../../.github/ISSUE_TEMPLATE/) when instantiating these epics, stories, and tasks as tracked work. Cross-link live issues back to the markdown source so traceability is maintained.

| Epic | Objective | Primary Systems | Reference Assets |
| --- | --- | --- | --- |
| [EPIC-CORE-001](./core-ai-systems.md) | Harden the core planner → orchestrator → executor loop for hybrid AI + deterministic play. | Planner, Orchestrator, Executor, Action Validation | [ADR-0001](../../adr/ADR-0001-planner-routing.md), [ADR-0002](../../adr/ADR-0002-orchestrator-defenses.md), [ADR-0003](../../adr/ADR-0003-executor-preview-apply.md), [Core Systems C4](../../architecture/core-systems-context.md) |
| [EPIC-AVA-001](./EPIC-AVA-001-action-validation-architecture.md) | Roll out the Action Validation pipeline with deterministic guardrails and feature-flagged stages. | Planner, Orchestrator, Executor, MCP | [ARCH-AVA-001](../../architecture/ARCH-AVA-001-action-validation-architecture.md), [Implementation Plan](../action-validation-implementation.md) |
| [EPIC-ENC-002](./encounter-turn-engine.md) | Deliver a feature-flagged encounter and turn engine that is observable, testable, and safe for live campaigns. | Encounter mechanics, Executor, Events Ledger | [ADR-0003](../../adr/ADR-0003-executor-preview-apply.md), [Encounter Observability Guide](../observability-and-flags.md) |

When a new initiative emerges, add a markdown file here with the same structure, then create the associated GitHub issues.
