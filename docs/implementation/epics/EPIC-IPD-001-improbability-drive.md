# EPIC-IPD-001 — ImprobabilityDrive Enablement (/ask + NLU/Tagging)

**Objective.** Deliver the ImprobabilityDrive component (formerly PossibilityEngine) that parses free-form player input into a structured AskReport with IntentFrame(s) and AffordanceTags, enabling deterministic feasibility checks upstream and preserving current behavior behind feature flags.

**Owner.** NLU/Planner working group (planner/orchestrator maintainers, ontology/KB, observability, contracts).

**Key risks.** Tag ontology drift, inadequate disambiguation leading to unsafe or confusing plans, privacy/PII exposure in logs, and rollout regressions when enabling /ask and tagging.

**Linked assets.**
- [ARCH-AVA-001 — Action Validation Architecture](../../architecture/ARCH-AVA-001-action-validation-architecture.md)
- [Implementation Plan — ImprobabilityDrive](../improbability-drive-implementation.md)
- [EPIC-AVA-001 — Action Validation Pipeline Enablement](./EPIC-AVA-001-action-validation-architecture.md)
- AIDD governance: [DoR/DoD](../dor-dod-guide.md)
- ADR: [ADR-0005 — ImprobabilityDrive (/ask): contracts, flags, and rollout](../../adr/ADR-0005-improbabilitydrive-contracts-and-flags.md)

**Definition of Ready.** Stories satisfy cross-team DoR plus:
- Proposed contracts for AskReport/IntentFrame/AffordanceTags enumerated with versioning.
- Feature flags and rollback toggles defined (defaults off), including metrics/logging expectations.
- NLU baseline, ontology scope, and KB data sources identified with privacy review initiated.

**Definition of Done.**
- Contracts, prompts, and flags merged and linked here; architecture references updated if needed.
- Quality gates (format, lint, type, test) run green with new assets included. Docs-only edits may skip code gates per AGENTS.md.
- Observability updates documented (structured logs, counters) and ActivityLog integration points identified.
- Smoke runbook: [Validation Runbook — STORY-IPD-001A](../../smoke/validation-runbook-ipd-001a.md)

---

## Current decisions

- 2025-09-20: Defer external NLP libraries (e.g., spaCy). Proceed with deterministic rule-based NLU and KB lookups in Phases 2–3. Any future evaluation remains parked behind a disabled flag and will require benchmarks, privacy review, and an ADR.

---

> Branch scope note: The `ADR-for-EPIC-IPD-001` branch is documentation-only (ADR + epic/stories/runbook). Source changes for `/ask` and NLU will land in Story B/C branches.

## Stories

### Status snapshot (as of 2025-09-25)

**Status Overview (2025-09-25):**

- **Done:**  
    - Story A — Contracts & Flags (models, JSON artifact, tests, flags)  
    - Story B — /ask Handler (handler, gating, metrics/logs, tests)  
    - Story C — NLU/Tagging Baseline (rule-based parser, golden fixtures)  
    - Story D — KB Adapter (read-only; adapter, cache, limits, tests)

- **Partially Done (not properly initiated):**  
    - Story E — Ontology Mgmt (schemas, seed, docs; validator extension pending)  
    - Story F — Logging/Metrics/ActivityLog (metrics/logs implemented; ActivityLog linkage pending)

- **Pending:**  
    - Story G — Planner Handoff  
    - Story H — Privacy/Redaction/Safety  
    - Story I — Operational Rollout

### STORY-IPD-001A — Contracts and feature flag scaffolding
Story doc: [/docs/implementation/stories/STORY-IPD-001A-contracts-and-flags.md](/docs/implementation/stories/STORY-IPD-001A-contracts-and-flags.md)
*Epic linkage:* Establishes AskReport/IntentFrame contracts and flags for phased rollout.

Status: In Progress

- Summary. Introduce canonical Pydantic v2 models for AskReport, IntentFrame, and AffordanceTags with serialization helpers and adapters as needed.
- Acceptance criteria.
  - New models align with ARCH-AVA-001 data contracts and pass round-trip serialization tests.
  - Feature flags `features.improbability_drive` and `features.ask` default to false.
  - Contract versioning documented (semver-like), with converters for any legacy planner inputs.
- Tasks.
  - [x] `TASK-IPD-SCHEMA-01` — Implement AskReport/IntentFrame/AffordanceTags models and JSON helpers.
  - [ ] `TASK-IPD-FLAGS-02` — Extend config.toml and config dataclass with `features.improbability_drive`, `features.ask` (default off) and docs. (Dev config currently enabled; document exception or flip defaults.)
  - [x] `TASK-IPD-TEST-03` — Add round-trip tests using deterministic fixtures.
  - [x] `TASK-IPD-CONTRACT-05` — Add Ask JSON contract artifact under `contracts/ask/v1/` and wire to validation script.

- DoR.
  - Contract change proposal reviewed with planner maintainers.
  - Test plan outlines identity fixtures and error handling.
- DoD.
  - Conversion tests committed with golden outputs.
  - Flag documentation updated in feature flag guide.

### STORY-IPD-001B — /ask command handler and responder
Story doc: [/docs/implementation/stories/STORY-IPD-001B-ask-handler.md](/docs/implementation/stories/STORY-IPD-001B-ask-handler.md)
*Epic linkage:* Wires entry point to emit AskReport while preserving existing flows.

Status: Implemented

- Summary. Add `/ask` handler using registry decorators and responder abstraction; when enabled, constructs AskReport using NLU/tagging scaffold and emits structured logs/metrics.
- Acceptance criteria.
  - `/ask` available behind `features.ask` and `features.improbability_drive`.
  - On success, returns a concise textual summary and emits AskReport-shaped data for observability; full persistence/linkage is deferred to Story F/ActivityLog.
  - On disable, no behavior change to existing commands.
- Tasks.
  - [x] `TASK-IPD-HANDLER-04` — Implement `/ask` handler with config gating and responder usage.
  - [x] `TASK-IPD-OBS-05` — Add structured logs and counters (e.g., `ask.received`, `ask.ask_report.emitted`).
  - [x] `TASK-IPD-TEST-06` — Web CLI and Discord tests for enabled/disabled behavior.
- DoR.
  - Command name/UX reviewed; strings added to prompts/localization if needed.
- DoD.
  - Tests confirm flag gating and output consistency.

### STORY-IPD-001C — NLU and tagging scaffold (rule-based baseline)
Story doc: [/docs/implementation/stories/STORY-IPD-001C-nlu-tagging-baseline.md](/docs/implementation/stories/STORY-IPD-001C-nlu-tagging-baseline.md)
*Epic linkage:* Minimal, deterministic NLU to bootstrap IntentFrame + tags without ML dependencies.

Status: Implemented

- Summary. Implement a rule-based parser for action, actor, object/target refs, plus AffordanceTags extraction from a small ontology; include entity normalization hooks.
- Acceptance criteria.
  - Deterministic parsing with seeded examples; no network calls.
  - Tag extraction maps to ontology IDs; unrecognized tokens surfaced as `unknown:*` tags.
  - Unit tests cover varied phrasing and edge cases (empty/ambiguous).
- Tasks.
  - [x] `TASK-IPD-NLU-07` — Rule-based parser for IntentFrame fields.
  - [x] `TASK-IPD-TAGS-08` — AffordanceTags extractor with ontology lookups.
  - [x] `TASK-IPD-TEST-09` — Fixture-driven tests with golden outputs.
- DoR.
  - Ontology MVP defined; normalization rules agreed.
- DoD.
  - Parser/extractor documented with examples and limitations.

### STORY-IPD-001D — World Knowledge Base (KB) integration (read-only)
Story doc: [/docs/implementation/stories/STORY-IPD-001D-kb-integration.md](/docs/implementation/stories/STORY-IPD-001D-kb-integration.md)
*Epic linkage:* Disambiguates entities and tags using existing repos or KB.

Status: Implemented

- Summary. Add a read-only KB adapter leveraging existing repos to resolve entity references and suggest alternatives; cache common lookups.
- Acceptance criteria.
  - KB adapter functions return normalized IDs and candidate alternatives.
  - Deterministic resolution for seeded data; caches bounded and instrumentation added.
  - Timeouts and payload bounds are configurable with safe defaults.
- Tasks.
  - [x] `TASK-IPD-KB-10` — Implement KB adapter with repo-backed lookups.
  - [x] `TASK-IPD-CACHE-11` — Add caching with metrics for hit/miss.
  - [x] `TASK-IPD-TEST-12` — Unit tests for canonical entities and ambiguous cases.
- DoR.
  - Data fixtures prepared; timeout/bounds knobs defined.
- DoD.
  - Docs describe KB data sources and cache behavior.

### STORY-IPD-001E — Ontology management and versioning
Story doc: [/docs/implementation/stories/STORY-IPD-001E-ontology-management.md](/docs/implementation/stories/STORY-IPD-001E-ontology-management.md)
*Epic linkage:* Ensures AffordanceTags are governed and evolvable.

Status: In Progress

- Summary. Define ontology files under `prompts/` or `contracts/` with versioning, validation script, and governance.
- Acceptance criteria.
  - Ontology schema and linter in place; changes validated via CI script (`scripts/validate_contracts.py`).
  - Tags referenced by NLU and planner documented with migration guidance.
- Tasks.
  - [x] `TASK-IPD-ONTO-13` — Author ontology schema and seed ontology.
  - [ ] `TASK-IPD-VALIDATE-14` — Extend validation script to include ontology checks.
  - [x] `TASK-IPD-DOCS-15` — Author ontology guide under docs/architecture or docs/dev.
- DoR.
  - Stakeholders aligned on taxonomy scope.
- DoD.
  - CI runs ontology validation; docs linked here.

### STORY-IPD-001F — Logging, metrics, and ActivityLog linkage
Story doc: [/docs/implementation/stories/STORY-IPD-001F-logging-and-metrics.md](/docs/implementation/stories/STORY-IPD-001F-logging-and-metrics.md)
*Epic linkage:* Observability aligned with defensibility requirements.

Status: In Progress

- Summary. Standardize logs and counters for /ask and tagging; integrate with ActivityLog when Phase 6 assets exist.
- Acceptance criteria.
  - Structured logs: initiated/completed and rejection reasons; counters like `ask.received`, `ask.failed`, `ask.tags.count`, `kb.lookup.hit/miss`.
  - ActivityLog story linkage mirrors AVA phase 6 patterns; tests assert metric increments.
- Tasks.
  - [x] `TASK-IPD-LOG-16` — Add structured logging via repo helpers.
  - [x] `TASK-IPD-METRIC-17` — Add counters and reset/get helpers in tests.
  - [ ] `TASK-IPD-ACTLOG-18` — Wire ActivityLog entries when feature enabled.
- DoR.
  - Observability acceptance criteria reviewed.
- DoD.
  - Logging guide references new events and owners.

### STORY-IPD-001G — Planner integration handoff (AskReport → Plan)
Story doc: [/docs/implementation/stories/STORY-IPD-001G-planner-handoff.md](/docs/implementation/stories/STORY-IPD-001G-planner-handoff.md)
*Epic linkage:* Connects AskReport output to existing planner path behind flags.

Status: Planned

- Summary. When enabled, planner accepts AskReport; otherwise use existing inputs. Add adapters and parity tests.
- Acceptance criteria.
  - Adapter maps AskReport to current planner inputs with no behavioral regressions.
  - Feature flag gates the new path; preview/apply parity tests pass.
- Tasks.
  - [ ] `TASK-IPD-ADAPT-19` — Implement AskReport → planner adapter.
  - [ ] `TASK-IPD-INTEG-20` — Integration tests around roll/check/attack intents.
- DoR.
  - Test fixtures prepared.
- DoD.
  - Zero-diff confirmed in preview output.

### STORY-IPD-001H — Privacy, redaction, and safety
Story doc: [/docs/implementation/stories/STORY-IPD-001H-privacy-and-safety.md](/docs/implementation/stories/STORY-IPD-001H-privacy-and-safety.md)
*Epic linkage:* Ensures safe handling of user text.

Status: Planned

- Summary. Implement PI/PII redaction for logs, bounded context windows, and configurable retention.
- Acceptance criteria.
  - Redaction in logs enabled by default; opt-out documented.
  - Size/time limits configurable; violations logged and rejected safely.
- Tasks.
  - [ ] `TASK-IPD-PRIV-21` — Redaction filters for logs and AskReport persistence.
  - [ ] `TASK-IPD-LIMITS-22` — Enforce input size/time bounds with metrics.
  - [ ] `TASK-IPD-TEST-23` — Tests for redaction and bounds.

### STORY-IPD-001I — Operational hardening and rollout
Story doc: [/docs/implementation/stories/STORY-IPD-001I-operational-rollout.md](/docs/implementation/stories/STORY-IPD-001I-operational-rollout.md)

Status: Planned

---

## Configuration and flags (explicit)

Target Settings fields in `src/Adventorator/config.py` (defaults preserve current behavior):

- `features_improbability_drive: bool = False`
- `features_ask: bool = False`
- `features_ask_nlu_rule_based: bool = True`
- `features_ask_kb_lookup: bool = False`
- `features_ask_planner_handoff: bool = False`
- `features_ask_nlu_debug: bool = False` (developer-only ephemeral debug output)

TOML mapping in `_toml_settings_source()`:

- Top-level toggles under `[features]`:
  - `improbability_drive = false`
  - `ask = false`
- Optional sub-flags under `[features.ask]` (mirrors existing nested retrieval config):
  - `nlu_rule_based = true`
  - `nlu_debug = false`
  - `kb_lookup = false`
  - `planner_handoff = false`

Example snippet (defaults shown):

```toml
[features]
improbability_drive = false
ask = false

[features.ask]
nlu_rule_based = true
nlu_debug = false
kb_lookup = false
planner_handoff = false
```

KB configuration knobs (used when `features.ask` and `features.ask.kb_lookup` are enabled):

```toml
[ask.kb]
timeout_s = 0.05
max_candidates = 5
cache_ttl_s = 60
cache_max_size = 1024
max_terms_per_call = 20
```

Module placement:

- Contracts (Pydantic models for app use): `src/Adventorator/schemas.py` (AskReport, IntentFrame, AffordanceTag).
- Contract artifacts (registry): `contracts/ask/v1/` (JSON schema or OpenAPI component), validated by `scripts/validate_contracts.py`.
- Tests and fixtures: `tests/ask/` with golden round-trip fixtures.
*Epic linkage:* Safe staged enablement of /ask and tagging.

- Summary. Apply guardrails, SLOs, and rollout plan with canary+rollback.
- Acceptance criteria.
  - Timeouts and payload bounds enforced with safe defaults; observability in place.
  - Rollout plan defines dev, canary, GA with rollback triggers and owner on-call.
- Tasks.
  - [ ] `TASK-IPD-TIMEOUT-24` — Implement timeout/payload knobs.
  - [ ] `TASK-IPD-RUNBOOK-25` — Document rollout/canary plan with escalation.
- DoR.
  - Operations review completed.
- DoD.
  - Runbook linked here; dashboards or mockups attached.

---

## Traceability Log

| Artifact | Link | Notes |
| --- | --- | --- |
| Epic Issue | [TBD](https://github.com/crashtestbrandt/Adventorator/issues/) | Create and link the GitHub issue number when opened. |
| Architecture | ../../architecture/ARCH-AVA-001-action-validation-architecture.md | Component 1 (ImprobabilityDrive) specification. |
| Implementation Plan | ../improbability-drive-implementation.md | Phases, validation, and rollout plan. |

Update the table as GitHub issues are created to preserve AIDD traceability.

---

Note: Stories E and F were partially started without formal initiation due to prior instruction confusion. This epic now reflects their true status and embeds alignment and policy notes to prevent further drift.