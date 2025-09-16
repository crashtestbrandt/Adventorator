## Action Validation Architecture

-----

### **1. Overview**

This document outlines the architecture for a system designed to parse, validate, and execute free-form player actions within a rules-driven, simulated world. The primary challenge is to bridge the gap between creative, natural-language player intent and the deterministic mechanics of a game engine, providing a system that is at once flexible, robust, and explainable.

The proposed solution is a four-stage, state-machine-based pipeline that combines deterministic logic with semantic inference. It processes user commands through distinct phases of possibility assessment, formal planning, policy orchestration, and transactional execution. This architecture allows for a high degree of player freedom while ensuring all outcomes remain coherent and consistent with the established world rules, whether they are laws of physics or laws of magic.

### **2. Guiding Principles**

The design of this architecture is guided by the following core principles:

  * **Modularity & Decoupling:** Components should be independent and communicate through well-defined interfaces. The game's "brain" (logic) must be decoupled from its "physics" (rules engine), allowing for swappable backends.
  * **Explainability:** The system must be able to explain *why* an action succeeds or fails. Every decision point should be traceable to a specific rule, predicate, or policy.
  * **Hybrid Reasoning:** The system must handle both mechanical possibility (physics, rules) and narrative plausibility (magic, story). It will use deterministic logic for the former and semantic inference for the latter.
  * **Robustness & Safety:** All state-changing operations must be transactional, idempotent, and reproducible. The system must be resilient to errors and invalid or duplicate inputs.
  * **Scalable Complexity:** The system should handle simple actions efficiently while providing the power to deconstruct and solve complex, multi-step goals when required.

### **3. Core Architecture**

The system is implemented as a state machine that processes user actions through four distinct components. Slash commands (`/ask`, `/plan`, `/do`) serve as entry points into specific stages of this pipeline.

#### **3.1. High-Level Flow**

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
      └──────────────┘      └───────────────────────────┘
```

#### **3.2. Component Breakdown**

**1. ImprobabilityDrive (formerly PossibilityEngine)**

  * **Entry Point:** `/ask`
  * **Responsibilities:**
      * Parses raw natural language into a structured `IntentFrame`.
      * Performs semantic analysis to enrich the intent with `AffordanceTags` (e.g., `[absurd]`, `[somatic]`, `[narrative_causality]`), identifying potential hooks into non-obvious game mechanics, magic, or narrative rules.
      * Queries the World Knowledge Base to disambiguate entities and assess high-level affordances.
  * **Input:** Raw user text.
  * **Output:** An `AskReport` containing the normalized intent, semantic tags, and any identified narrative/magical candidates.

**2. Planner**

  * **Entry Point:** `/plan`
  * **Responsibilities:**
      * Receives an `AskReport` and determines the concrete feasibility of the intent.
      * Executes a **Predicate Gate**: a series of fast, hard-logic checks (e.g., `exists`, `reachable`, `can_lift`) against the world state via read-only MCP tool calls.
      * If feasible, generates a `Plan` containing an ordered sequence of executable steps.
      * Utilizes a **Tiered Planning Strategy** to select the appropriate planning algorithm based on goal complexity.
      * If infeasible, generates a report of failed predicates and suggests potential repairs or alternatives.
  * **Input:** `AskReport`, read-only World Snapshot.
  * **Output:** A `Plan` object, which is either ready for execution or contains a detailed failure analysis.

**3. Orchestrator**

  * **Entry Point:** `/do`
  * **Responsibilities:**
      * Acts as the final policy and approval layer before execution.
      * Validates the received `Plan` against the current world state to check for drift (i.e., has the world changed since the plan was made?).
      * Enforces game-wide policies (e.g., violence caps, resource limits, GM-level overrides).
      * Selects a course of action from the `Plan`'s suggestions (e.g., apply a repair, prompt the user with an alternative, or approve for execution).
  * **Input:** `Plan`.
  * **Output:** An `ExecutionRequest` sent to the Executor.

**4. Executor**

  * **Responsibilities:**
      * Executes a validated `ExecutionRequest` deterministically. It is a "dumb worker" that follows instructions without making decisions.
      * Acts as an **MCP Client**, calling tools exposed by the `RulesEngine` and other backend services.
      * Wraps all state-changing operations in a transaction to ensure atomicity (all steps succeed or all fail).
      * Enforces idempotency to prevent duplicate executions of the same request.
  * **Input:** `ExecutionRequest`.
  * **Output:** An `ExecutionResult` containing a log of events and a summary of the final state delta.

### **4. Key Paradigms & Concepts**

#### **4.1. Dual-Paradigm Validation**

The architecture's core innovation is its ability to validate actions against two different models of reality simultaneously:

  * **Predicates (Mechanical Possibility):** These are formal, logical statements about the physical world (`distance(a,b) < 10`, `mass(a) < strength(b) * 8`). They are evaluated by a deterministic engine (like an SMT solver) and represent the hard "laws of physics" and game rules. They answer the question: *"Can this happen?"*
  * **Semantic Tags (Narrative Plausibility):** These are metadata labels on entities that represent abstract or magical properties (`[feywild]`, `[trigger:absurd]`, `[effect:summoning]`). They are used by the ImprobabilityDrive to find creative, non-obvious pathways for actions that might be mechanically impossible but narratively or magically plausible. They answer the question: *"Does it make sense for this to happen here?"*

#### **4.2. Tiered Planning Strategy**

To ensure efficiency, the Planner does not default to a single, heavyweight algorithm.

1.  **Level 1 (Single Operator):** For simple actions like "attack goblin," the system directly compiles the intent into a single-step `Plan` after passing the Predicate Gate.
2.  **Level 2 (Hierarchical Task Network - HTN):** For short, tactical goals like "get the goblin into the pit," an HTN planner is used to decompose the task into a known sequence of steps (e.g., `pickup` -\> `move_to` -\> `drop`).
3.  **Level 3 (GOAP/PDDL):** For complex, open-ended goals like "steal the artifact without being seen," a more powerful search-based planner is used to discover a valid sequence of actions from a set of primitives.

#### **4.3. The Multi-Component Protocol (MCP)**

The MCP is the API layer that decouples Adventorator's core logic from its simulation backend(s).

  * The **Executor** is the sole **MCP Client** for write operations.
  * The **Planner** is an **MCP Client** for read-only operations.
  * The **RulesEngine** and **Simulation Engine (Godot)** are **MCP Servers**, exposing their capabilities (e.g., `rules.apply_damage`, `sim.raycast`) as discrete, stateless tools.

This design allows the entire game backend to be replaced without changing the core architecture.

### **5. Data Contracts & Schemas**

The following Pydantic-style schemas define the immutable data structures passed between components.

```python
# Output of ImprobabilityDrive -> Input to Planner
class AskReport:
    intent: IntentFrame
    candidates: list[IntentFrame]
    policy_flags: dict
    rationale: str

# Central data structure for intent
class IntentFrame:
    action: str
    actor: str
    object_ref: str | None
    target_ref: str | None
    params: dict
    tags: set[str]
    guidance: dict

# Output of Planner -> Input to Orchestrator
class Plan:
    feasible: bool
    plan_id: str  # hash(intent + snapshot_digest + versions)
    steps: list[PlanStep]
    failed_predicates: list[dict]
    repairs: list[str]
    alternatives: list[IntentFrame]
    rationale: str

class PlanStep:
    op: str  # e.g., "move_to", "apply_damage"
    args: dict
    guards: list[str] # Predicates satisfied

# Output of Orchestrator -> Input to Executor
class ExecutionRequest:
    plan_id: str
    steps: list[PlanStep]
    context: dict  # trace_id, idempotency_key, etc.

# Output of Executor
class ExecutionResult:
    ok: bool
    events: list[dict]
    state_delta: dict
    narration_cues: list[str]
```

### **6. Technology Stack & Dependencies**

| Capability | Recommended Candidate(s) | Role in Architecture |
| :--- | :--- | :--- |
| **Natural Language Understanding** | Google Gemini / OpenAI GPT APIs | ImprobabilityDrive: Parsing & Tagging |
| **Constrained LLM Output** | `outlines`, `guidance` libraries | ImprobabilityDrive: Generating valid `IntentFrame`s |
| **Constraint Solving (SMT)** | `z3-solver`, `Google OR-Tools` | Planner: Predicate Gate evaluation |
| **Automated Planning** | `unified-planning` | Planner: HTN/GOAP for multi-step goals |
| **Simulation / Spatial Logic** | Headless Godot instance | MCP Server: Physics probes, raycasting, pathfinding |
| **Inter-Service Communication** | `gRPC` or `FastAPI` | The MCP implementation |
| **State Persistence** | `PostgreSQL` with `SQLAlchemy` | World Knowledge Base and event log storage |
| **State Machine Management** | `transitions` library | Orchestrator: Managing the core pipeline |

### **7. Operational Considerations**

  * **Ontology Management:** The vocabulary of `AffordanceTags` must be managed as a formal ontology. This should be stored in a version-controlled format (e.g., YAML files in a Git repository) and serve as a single source of truth for the ImprobabilityDrive and the content authoring pipeline.
  * **Configuration Management:** Policies, planner timeouts, and other operational parameters should be externalized from the code base into a configuration system to allow for dynamic adjustment.
  * **Observability:** A distributed tracing solution (e.g., `OpenTelemetry`) is critical for debugging requests as they flow through the entire pipeline, from the LLM call in the ImprobabilityDrive to the final database commit by the Executor.

### **8. Future Opportunities & Extensions**

This architecture is designed for growth and provides a foundation for several powerful future capabilities:

  * **Swappable Game Systems:** By creating new MCP servers, the Adventorator "brain" could be used to run campaigns in entirely different rule systems (e.g., Pathfinder, Cyberpunk) with minimal changes to the core logic.
  * **Procedural Content Generation (PCG):** The rich semantic information in the tagged Knowledge Base can be used to drive the generation of quests, items, and narrative encounters that are thematically consistent with the world.
  * **Community Modding:** A well-documented MCP tool API and tag ontology would empower a community to create and share new content (items, spells, locations, mechanics) that integrates seamlessly into the system.