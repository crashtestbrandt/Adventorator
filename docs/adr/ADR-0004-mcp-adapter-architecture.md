# Architecture Decision Record (ADR)

## Title
ADR-0004 — MCP adapter architecture for Action Validation executor integration

## Status
Proposed — 2025-02-14 (Owner: Action Validation Working Group)

## Context
Phase 7 of [EPIC-AVA-001 — Action Validation Pipeline Enablement](../implementation/epics/action-validation-architecture.md) requires STORY-AVA-001H to introduce Multi-Component Protocol (MCP) adapters so the executor can route deterministic tool calls through a swap-friendly interface. Today the executor directly invokes rules and simulation helpers, bypassing the MCP contracts documented in [ARCH-AVA-001 — Action Validation Architecture](../architecture/action-validation-architecture.md). Only the `features.mcp` flag exists; no adapter modules, contracts, or tests enforce parity with the existing tool chain behavior. We must define the in-process MCP architecture now to unblock adapter scaffolding while keeping forward compatibility for future out-of-process MCP servers.

## Decision
- Introduce a dedicated MCP client layer inside the executor that mediates all tool execution when `features.mcp` is enabled. The client wraps each `ExecutionRequest` step, resolves the correct MCP adapter, and handles retry/metrics concerns before delegating to the underlying server shim.
- Define adapter interfaces under `src/Adventorator/mcp/`:
  - `interfaces.py` specifies synchronous/async call signatures for deterministic rule operations (`apply_damage`, `roll_attack`, `compute_check`) and simulation hooks (placeholder `raycast`).
  - `registry.py` maps tool identifiers to adapter implementations and guards unknown tools with explicit feature-flagged errors.
  - `inprocess/rules.py` and `inprocess/simulation.py` provide initial in-process server shims that call the existing rules/simulation helpers without network I/O.
- Update executor tool handlers so that when `features.mcp` is false they maintain current direct calls, and when true they exclusively use the MCP client APIs. The executor remains the sole writer; planner-only read calls may be added later but must route through the same interfaces for consistency.
- Version MCP contracts alongside existing action validation schemas (e.g., `contracts/mcp/{tool}.v1.json` for payloads and deterministic outputs). Contracts must include invariants inherited from `ExecutionRequest` so adapters can be validated in isolation.
- Add golden parity tests that execute representative tool calls both through the legacy direct path and the MCP adapters, asserting identical results and event logs. These tests run under `features.mcp` enabled and disabled to guarantee safe rollout gating.
- Instrument MCP calls with structured logs (`executor.mcp.tool`, `executor.mcp.duration_ms`, `executor.mcp.error`) and counters (`executor.mcp.call`, `executor.mcp.failure`) aligned with the observability plan in Phase 7.

## Rationale
- A thin in-process MCP layer satisfies STORY-AVA-001H’s Definition of Done by routing executor calls through adapters without expanding the trust boundary yet. This keeps deterministic parity with existing rules helpers while exercising the contracts and rollout controls needed for later externalization.
- Centralizing adapter resolution in a registry allows feature-flagged enablement, safe fallbacks, and future dependency injection (e.g., swapping to gRPC clients) without touching executor business logic.
- Versioned contracts and parity tests enforce backward compatibility and auditability, ensuring ActivityLog correlation when MCP becomes the canonical execution path.
- Alternatives considered:
  - **Continue direct executor→rules calls:** rejected because it blocks MCP feature delivery and prevents contract validation before external servers arrive.
  - **Immediate networked MCP services:** deferred; introducing network hops now would delay Phase 7, complicate deterministic testing, and violate the incremental rollout strategy described in ARCH-AVA-001.
  - **Adapters per tool without a registry:** rejected; would duplicate wiring logic across handlers and hinder observability/feature-flag control.

## Consequences
- **Positive:**
  - Establishes the scaffold required to unlock STORY-AVA-001H tasks (`TASK-AVA-MCP-23`, `TASK-AVA-EXEC-24`, `TASK-AVA-TEST-25`).
  - Enables deterministic parity testing and metrics ahead of external MCP deployments.
  - Decouples executor logic from concrete rule helpers, simplifying future adoption of third-party or modded MCP servers.
- **Negative:**
  - Adds an additional indirection layer that must be maintained until MCP is fully adopted.
  - Requires new contracts and tests, increasing near-term implementation effort.
- **Future considerations:**
  - Evaluate network isolation, authentication, and timeout budgets once MCP servers move out-of-process (Phase 8+).
  - Extend planner read-only integrations and simulation streaming once the adapter scaffolding proves stable.
  - Monitor adapter performance metrics to decide when to retire the legacy direct execution path.

## References
- [EPIC-AVA-001 — Action Validation Pipeline Enablement](../implementation/epics/action-validation-architecture.md)
- [ARCH-AVA-001 — Action Validation Architecture](../architecture/action-validation-architecture.md)
- [STORY-AVA-001H — MCP adapter scaffold](../implementation/epics/action-validation-architecture.md#story-ava-001h--mcp-adapter-scaffold)
- [Manual validation runbook for EPIC-AVA-001](../smoke/manual-validation-EPIC-AVA-001.md)
- [`docs/implementation/action-validation-implementation.md` — Phase 7 MCP scaffold requirements](../implementation/action-validation-implementation.md#phase-7--mcp-scaffold-local-in-process-servers)
