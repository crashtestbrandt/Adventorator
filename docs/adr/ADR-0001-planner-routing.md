# Architecture Decision Record (ADR)

## Title
ADR-0001 — Planner routing contract and catalog governance

## Status
Accepted — 2024-05-09 (Owner: Adventure Systems WG)

## Context
The `/plan` command delegates free-form player intent to the AI planner. The planner must stay aligned with the live slash command catalog to avoid hallucinated commands, security gaps, or mismatched schemas. Recent roadmap work (EPIC-CORE-001) requires formalizing the planner contract so Stories can automate validation and prompts can be versioned safely.

## Decision
- The planner produces a `PlannerOutput` object with `{command: str, args: dict}` validated against the command registry schema at runtime.
- A generated command catalog (JSON) is stored in `contracts/planner/catalog.v{n}.json` and updated whenever commands change.
- Planner prompts reference the catalog via explicit version tags stored under `prompts/planner/`.
- CI quality gates compare the catalog to live registry metadata and block merges when drift is detected.
- Feature flag `features.planner` controls rollout; disabling it bypasses planner routing and surfaces manual command selection.

## Rationale
- Contract-first governance reduces planner hallucinations and ensures compatibility with slash command schema changes.
- Versioned catalogs support reproducible prompt evaluations and enable rollbacks.
- Automated drift detection prevents silent regressions and provides a DoR gate for related stories.
- Flag control offers operational safety if LLM behavior becomes unreliable.

## Consequences
- Positive: Traceable link between planner behavior, prompts, and command registry; easier audits and rollbacks.
- Negative: Requires ongoing maintenance of catalog generation tooling and CI gates.
- Future: Revisit when planner supports multiple transports or conditional command availability per guild.

## References
- [EPIC-CORE-001 — Core AI Systems Hardening](../implementation/epics/core-ai-systems.md)
- [`core-systems-context.puml`](../architecture/core-systems-context.puml)
- Planner module: [`src/Adventorator/planner.py`](../../src/Adventorator/planner.py)

## Post-AVA Evolution (2025-09)
The Action Validation architecture (ARCH-AVA-001) supersedes the bare `PlannerOutput {command,args}` shape with a richer, versioned `Plan` contract:

| Legacy Concept | Current Equivalent | Notes |
| -------------- | ------------------ | ----- |
| `PlannerOutput.command` | `Plan.steps[0].op` | Level 1 planning restricts to a single step. |
| `PlannerOutput.args` | `Plan.steps[0].args` | Preserves argument schema; validated against command registry. |
| (none) | `Plan.feasible` / `failed_predicates` | Introduced via Predicate Gate (flag: `features.predicate_gate`). |
| (none) | `Plan.rationale`, `repairs`, `alternatives` | Adds explainability & remediation hints. |
| (none) | `PlanStep.guards` | Placeholder for future tiered planning (HTN/GOAP). |

Implications:
- Catalog drift validation now serves both slash command schema and `PlanStep` argument validation; this ADR remains authoritative for catalog governance while deferring execution semantics to ARCH-AVA-001.
- Stories SHOULD reference the `Plan` abstraction; new usages of `PlannerOutput` are discouraged and will be linted.
- Feature flag alignment: enabling `features.action_validation` transparently wraps the legacy planner output into a single-step `Plan` while preserving existing downstream behavior.

Migration Guidance:
1. Replace internal references to `PlannerOutput` with `Plan` (Level 1 assumption: exactly one `PlanStep`).
2. Surface predicate failures through the `Plan` rather than ad-hoc rejection messages.
3. When adding new commands, update the catalog and ensure `PlanStep` serialization tests cover argument defaults.

This section deprecates the term `PlannerOutput` except when referring to historical context in this ADR.
