# ARCH-AVA-001 — Action Validation Architecture

**Status:** Active — Phases 0–6 implemented/in progress; remaining phases (7–9) planned behind feature flags  \
**Last Updated:** 2025-09-19  \
**Primary Epic:** [EPIC-AVA-001 — Action Validation Pipeline Enablement](../implementation/epics/EPIC-AVA-001-action-validation-architecture.md)  \
**Implementation Plan:** [Action Validation Implementation Plan](../implementation/action-validation-implementation.md)  \
**Related Governance:** [AIDD DoR/DoD Rituals](../implementation/dor-dod-guide.md)

---

## Summary

The Action Validation architecture introduces a modular, state-machine-driven pipeline that accepts free-form player intent, validates it deterministically, and executes the outcome through Multi-Component Protocol (MCP) adapters. The system balances narrative creativity with mechanical safety by separating natural-language understanding, feasibility analysis, policy enforcement, and transactional execution into distinct components. Feature flags and intermediate adapters allow each phase to roll out defensively without disrupting the existing `/plan → /do` experience.

## Architectural Context

### Guiding Principles

* **Modularity & Decoupling.** Each component communicates via versioned contracts so implementations can evolve independently.
* **Explainability.** Every decision produces auditable logs, metrics, and (when enabled) ActivityLog entries.
* **Hybrid Reasoning.** Deterministic predicates and semantic tags collaborate to judge both mechanical possibility and narrative plausibility.
* **Robustness & Safety.** Execution remains transactional and idempotent, backed by feature-flag rollbacks.
* **Scalable Complexity.** Tiered planning supports single-step defaults today while leaving room for HTN/PDDL expansion.

### High-Level Pipeline

```
      User Input (e.g., /ask "...")
             │
             ▼
┌───────────────────────────┐
│ 1. ImprobabilityDrive     │ NLU, Tagging, Intent Framing
└────────────┬──────────────┘
             │ (AskReport)
             ▼
┌───────────────────────────┐
│ 2. Planner                │ Predicate Gate, Feasibility, Step Generation
└────────────┬──────────────┘
             │ (Plan)
             ▼
┌───────────────────────────┐
│ 3. Orchestrator           │ Policy, Approval, Drift Check
└────────────┬──────────────┘
             │ (ExecutionRequest)
             ▼
┌───────────────────────────┐
│ 4. Executor (MCP Client)  │ Transactional Tool Calls
└────────────┬──────────────┘
             │
             ├───────────[ Multi-Component Protocol (MCP) ]───────────►
             │
      ┌──────────────┐      ┌───────────────────────────┐
      │ RulesEngine  │      │ Simulation Engine         │
      │ (MCP Server) │      │ (e.g., Headless Godot)    │
      └──────────────┘      └───────────────────────────
```

## Component Responsibilities

### 1. ImprobabilityDrive (formerly PossibilityEngine)

* **Entry Point:** `/ask`
* **Responsibilities:**
  * Parse natural language into a structured `IntentFrame` and enrich with semantic `AffordanceTags`.
  * Consult the World Knowledge Base to disambiguate entities and surface narrative or magical affordances.
* **Input:** Raw user text.  
* **Output:** `AskReport` containing normalized intent, semantic tags, and candidate alternatives.

### 2. Planner

* **Entry Point:** `/plan`
* **Responsibilities:**
  * Evaluate feasibility via a deterministic **Predicate Gate** backed by repos/rules helpers.
  * Generate a `Plan` consisting of ordered `PlanStep` items (Level 1 single operator by default).
  * Produce rich rationale, failed predicate metadata, and suggested repairs when infeasible.
* **Input:** `AskReport` (or current planner inputs) plus read-only world snapshot.  
* **Output:** `Plan` ready for policy review or containing a failure report.

### 3. Orchestrator

* **Entry Point:** `/do`
* **Responsibilities:**
  * Validate `Plan` data against current world state to detect drift.
  * Enforce global policies (ability allowlists, DC bounds, banned verbs) with structured rejection logs.
  * Approve, repair, or request clarification before issuing an `ExecutionRequest`.
* **Input:** `Plan`.  
* **Output:** `ExecutionRequest` forwarded to the Executor.

### 4. Executor

* **Responsibilities:**
  * Deterministically process `ExecutionRequest` payloads through MCP adapters (initially in-process shims).
  * Maintain idempotency, transactional guarantees, and parity with existing ToolCallChain previews/apply flows.
* **Input:** `ExecutionRequest`.  
* **Output:** `ExecutionResult` summarizing events, state deltas, and narration cues.

## Key Paradigms & Concepts

### Dual-Paradigm Validation

* **Predicates (Mechanical Possibility):** Deterministic checks (`exists`, `reachable`, `dc_in_bounds`) answered via repos/rules modules, ensuring “can this happen?”.
* **Semantic Tags (Narrative Plausibility):** Metadata describing magical, narrative, or contextual affordances to explore “does this make sense here?”.

### Tiered Planning Strategy

1. **Level 1 (Single Operator):** Default mode mapping intents directly to one executable step.
2. **Level 2 (HTN):** Future expansion for tactical, multi-step goals (disabled until feature flag flips).
3. **Level 3 (GOAP/PDDL):** Long-term ambition for complex objectives.

### Multi-Component Protocol (MCP)

* Executor is the sole MCP client for write operations; Planner uses read-only calls.
* RulesEngine and Simulation Engine expose deterministic tools as MCP servers.
* In Phase 7 the adapters remain in-process functions; future phases can swap in networked services without altering contracts.

## Data Contracts

```python
class AskReport:
    intent: IntentFrame
    candidates: list[IntentFrame]
    policy_flags: dict
    rationale: str

class IntentFrame:
    action: str
    actor: str
    object_ref: str | None
    target_ref: str | None
    params: dict
    tags: set[str]
    guidance: dict

class Plan:
    feasible: bool
    plan_id: str
    steps: list[PlanStep]
    failed_predicates: list[dict]
    repairs: list[str]
    alternatives: list[IntentFrame]
    rationale: str

class PlanStep:
    op: str
    args: dict
    guards: list[str]

class ExecutionRequest:
    plan_id: str
    steps: list[PlanStep]
    context: dict

class ExecutionResult:
    ok: bool
    events: list[dict]
    state_delta: dict
    narration_cues: list[str]

### Legacy Contract Evolution

- Replaces legacy `PlannerOutput` (ADR-0001) with single-step `Plan` (Level 1) while preserving command catalog validation.
- Introduces `ExecutionRequest` as intermediary replacing direct ToolChain handoff described in ADR-0003.
- Ensures event ledger + ActivityLog entries reference `plan_id` for replay integrity.
- See amended sections in ADR-0001 (Post-AVA Evolution) and ADR-0003 (Integration with Action Validation) for migration specifics.
```

## Operational Considerations

* **Ontology Management.** Store and version `AffordanceTags` alongside planner prompts and contracts.
* **Configuration Management.** Externalise feature toggles (`features.action_validation`, `features.predicate_gate`, `features.mcp`) and planner/orchestrator timeouts.
* **Observability.** Standardise structured logs, counters (`planner.feasible`, `predicate.gate.fail_reason`, `executor.preview/apply`), and ActivityLog records (Phase 6). Detailed mechanics ledger rollout tracked in [EPIC-ACTLOG-001](../implementation/epics/activitylog-mechanics-ledger.md).

## Traceability and Roadmap Alignment

* Implementation slices, rollouts, and rollback levers are captured in the [Action Validation Implementation Plan](../implementation/action-validation-implementation.md).
* Work is tracked under [EPIC-AVA-001](../implementation/epics/EPIC-AVA-001-action-validation-architecture.md) with Story/Task checklists for each phase.
* Contract updates should reference or extend relevant ADRs once authored; placeholder links will be updated during Phase 0.

## Future Opportunities

* **Swappable Game Systems.** Add new MCP servers to support rule variants (Pathfinder, Cyberpunk) without changing the pipeline.
* **Procedural Content Generation.** Reuse semantic tags to drive quest and encounter generation.
* **Community Modding.** Publish MCP tool contracts and tag ontology to enable third-party content creation.
