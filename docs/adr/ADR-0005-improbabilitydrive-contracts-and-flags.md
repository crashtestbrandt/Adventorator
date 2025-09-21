# Architecture Decision Record (ADR)

## Title
ADR-0005 — ImprobabilityDrive (/ask): contracts, flags, and rollout (EPIC-IPD-001)

## Status
Accepted — 2025-09-20 (Owner: NLU/Planner WG)

## Context
The ImprobabilityDrive (/ask) feature spans EPIC-IPD-001 and Stories A–I, introducing structured interpretation of free-form player input (AskReport with IntentFrame and AffordanceTags), optional KB disambiguation, planner handoff, observability, privacy controls, and an operational rollout. We require:
- A governed source of truth for public contracts that is language-agnostic.
- Clear placement for runtime models and the `/ask` command handler.
- A consistent feature-flag strategy and configuration precedence to ensure safe rollout and testability.
- Deferral of external NLP libraries until a deterministic baseline and governance exist.

Early work briefly placed Pydantic models under `src/Adventorator/ask/`, conflicting with repository governance that requires canonical contracts under `contracts/` and keeps runtime models separate. Parity tests revealed the need for OS env to override `.env` in Settings precedence.

## Decision
- Contracts and interfaces (Epic-wide)
  - Canonical Ask contract artifact lives in `contracts/ask/v1/ask-report.v1.json`. Include an `openapi` marker to satisfy existing validation.
  - Runtime models (Pydantic) for app use live in `src/Adventorator/schemas.py` (AskReport, IntentFrame, AffordanceTag). The registry artifact is the source of truth; models must not diverge (add a parity test in follow-up).
- Component placement
  - `/ask` command handler belongs under `src/Adventorator/commands/`, using existing registry decorators and responder abstraction.
  - Rule-based NLU and KB adapters will follow existing service/module patterns under `src/Adventorator` (no network/ML dependencies; deterministic and testable). Exact module paths are left to Story C/D implementation but must avoid introducing new architectural layers without an ADR.
  - Ontology governance artifacts will be versioned and validated per Story E under repo-managed locations (`prompts/` or `contracts/` as decided in that story), integrating with `scripts/validate_prompts_and_contracts.py`.
  - Branch hygiene: this ADR branch is documentation-only; code for `/ask` and NLU/tagging will land in Story B/C branches.
- Feature flags and rollout
  - Flags (defaults preserve current behavior):
    - `features_improbability_drive` (default=false)
    - `features_ask` (default=false; boolean or `[features.ask].enabled` table)
    - Sub-flags: `features_ask_nlu_rule_based` (default=true), `features_ask_kb_lookup` (default=false), `features_ask_planner_handoff` (default=false)
  - TOML mapping supports `[features]` toggles and optional `[features.ask]` table for sub-flags.
  - Rollout will use canary toggles; Story I will document runbooks and SLOs; disable flags to rollback.
- Settings precedence
  - Source order (highest→lowest): init > OS env > .env(.local) > TOML > file secrets — to ensure tests and dev overrides work reliably.
- Observability (Epic-level)
  - Logging and metrics for `/ask` will use repository helpers; initial metrics include `ask.received`, `ask.ask_report.emitted`, `ask.failed`, plus KB cache hit/miss. These are introduced in Story F; not required for Story A.
- Privacy and safety
  - Redaction, size/time bounds, and safe rejection behaviors will be added in Story H with defaults favoring privacy and safety.
- External NLP
  - External NLP libraries (e.g., spaCy) remain deferred behind disabled flags until benchmarks and privacy review exist.
  
- Implementation sequencing
  - Story A: contracts + feature flags (docs/config scaffolding).
  - Story B: `/ask` handler under `src/Adventorator/commands/`, behind flags (separate PR).
  - Story C: deterministic rule-based NLU baseline (token/stopword heuristic) behind flags.
  - Story F/H/I: observability, privacy/safety, rollout.

## Rationale
- Governance: `contracts/` is the reviewed, validated registry for public artifacts; CI validators and cross-language consumers rely on it.
- Separation of concerns: Runtime models are implementation detail; artifacts in `contracts/` provide durable compatibility guarantees.
- Safety & rollout: Flags default off; sub-flags enable staged delivery (NLU, KB, planner handoff) without regressions.
- Developer experience: OS env overriding `.env` ensures reliable test toggling and fixed prior parity issues.

Alternatives considered:
- Single-source generation (derive JSON schema from Pydantic or vice versa). Deferred to avoid build complexity; parity test proposed as follow-up.
- Embedding contracts under `src/`. Rejected per governance and cross-language needs.

## Consequences
- Positive:
  - Epic-wide clarity on placement, gating, and observability reduces churn across Stories A–I.
  - Single source of truth for contracts; consumers can integrate without Python dependencies.
  - Safer rollout with explicit, documented flags and precedence.
- Negative:
  - Until parity testing/codegen lands, duplication between JSON artifact and Pydantic models can drift.
  - Ontology validation may require extending the contracts validator (format not strictly OpenAPI).
- Future considerations:
  - Add automated parity check between Pydantic `model_json_schema()` and `contracts/ask/v1/ask-report.v1.json`.
  - Consider code generation or a unified schema source to remove duplication.
  - Extend validation tooling to cover ontology artifacts per Story E.

## References
- Epic: [../implementation/epics/EPIC-IPD-001-improbability-drive.md](../implementation/epics/EPIC-IPD-001-improbability-drive.md)
- Stories:
  - [../implementation/stories/STORY-IPD-001A-contracts-and-flags.md](../implementation/stories/STORY-IPD-001A-contracts-and-flags.md)
  - [../implementation/stories/STORY-IPD-001B-ask-handler.md](../implementation/stories/STORY-IPD-001B-ask-handler.md)
  - [../implementation/stories/STORY-IPD-001C-nlu-tagging-baseline.md](../implementation/stories/STORY-IPD-001C-nlu-tagging-baseline.md)
  - [../implementation/stories/STORY-IPD-001D-kb-integration.md](../implementation/stories/STORY-IPD-001D-kb-integration.md)
  - [../implementation/stories/STORY-IPD-001E-ontology-management.md](../implementation/stories/STORY-IPD-001E-ontology-management.md)
  - [../implementation/stories/STORY-IPD-001F-logging-and-metrics.md](../implementation/stories/STORY-IPD-001F-logging-and-metrics.md)
  - [../implementation/stories/STORY-IPD-001G-planner-handoff.md](../implementation/stories/STORY-IPD-001G-planner-handoff.md)
  - [../implementation/stories/STORY-IPD-001H-privacy-and-safety.md](../implementation/stories/STORY-IPD-001H-privacy-and-safety.md)
  - [../implementation/stories/STORY-IPD-001I-operational-rollout.md](../implementation/stories/STORY-IPD-001I-operational-rollout.md)
- Contract: [../../contracts/ask/v1/ask-report.v1.json](../../contracts/ask/v1/ask-report.v1.json)
- Runtime models: [../../src/Adventorator/schemas.py](../../src/Adventorator/schemas.py)
- Validation: [../../scripts/validate_prompts_and_contracts.py](../../scripts/validate_prompts_and_contracts.py)
- Smoke runbook: [../smoke/validation-runbook-ipd-001a.md](../smoke/validation-runbook-ipd-001a.md)
