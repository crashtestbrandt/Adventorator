# Core Systems Context Diagram

This document provides a C4-inspired context view of the planner → orchestrator → executor flow. The source of truth is [`core-systems-context.puml`](./core-systems-context.puml); render it with PlantUML (`plantuml core-systems-context.puml`) or your preferred diagram tooling.

## Overview

- **External actors.** Discord users issue slash commands via the Discord Interactions API; LLM providers supply JSON proposals.
- **Edge layer.** FastAPI verifies signatures, acknowledges interactions, and routes to the command registry.
- **AI layer.** The planner resolves `/plan` intents, the orchestrator enforces defenses and crafts narration/mechanics, and the executor validates and applies tool chains.
- **Data & observability.** Tool registry schemas, the events ledger, and Postgres store state; metrics and tracing capture latency, rejection rates, and locks.

## Traceability

- Linked Epics: [EPIC-CORE-001](../implementation/epics/core-ai-systems.md)
- ADRs: [ADR-0001](../adr/ADR-0001-planner-routing.md), [ADR-0002](../adr/ADR-0002-orchestrator-defenses.md), [ADR-0003](../adr/ADR-0003-executor-preview-apply.md)
- Prompts: `prompts/planner/` (catalog), `prompts/orchestrator/` (narration defense matrix)

Keep the PlantUML diagram updated when ADRs evolve to preserve C4 traceability.
