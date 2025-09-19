# Architecture Decision Record (ADR)

## Title
ADR-0002 — Orchestrator defense and rejection policy

## Status
Accepted — 2024-05-09 (Owner: Adventure Systems WG)

## Context
The orchestrator mediates narrative actions for `/do`, combining AI-generated narration with deterministic mechanics. Without enforced defenses, the system risks unsafe narration, unauthorized actors, or rule-breaking mechanics. EPIC-CORE-001 and the Encounter Epic both depend on a documented defense matrix so Stories can measure rejection coverage and observability budgets.

## Decision
- Maintain a defense matrix enumerating validation steps: schema validation, actor allowlist, banned verbs, DC bounds, and feature flag gating.
- All orchestrator proposals must pass through `validate_orchestrator_output` which produces structured rejection reasons (`unknown_actor`, `unsafe_verb`, `dc_out_of_bounds`, `invalid_action`, `invalid_schema`).
- Rejection events increment metrics (`orchestrator.request.total{result="rejected"}`, `llm.defense.rejected`) and produce structured logs with scene and actor context.
- Observability budgets target ≤10% rejection rate per scene type; thresholds defined in [Observability & Feature Flags](../implementation/observability-and-flags.md).
- Feature flag `features.executor` toggles whether mechanics call into the executor; when disabled the orchestrator falls back to local ruleset evaluation.

## Rationale
- Explicit defense matrix supports traceability and keeps AI outputs within deterministic guardrails.
- Structured rejections enable dashboards/alerts and align with DoR/DoD checklists.
- Feature flag coupling offers an escape hatch if executor integration introduces regressions.

## Consequences
- Positive: Safer AI narration, measurable defense coverage, clearer incident response.
- Negative: Additional maintenance to keep defense list in sync with new mechanics and verbs.
- Future: Evaluate adaptive defenses or policy configuration when new content types (e.g., spells, exploration) are added.

## References
- [EPIC-CORE-001 — Core AI Systems Hardening](../implementation/epics/core-ai-systems.md)
- [Observability & Feature Flags](../implementation/observability-and-flags.md)
- Orchestrator module: [`src/Adventorator/orchestrator.py`](../../src/Adventorator/orchestrator.py)
