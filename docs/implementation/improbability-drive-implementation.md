# Implementation Plan — ImprobabilityDrive (EPIC-IPD-001)

Status: Draft  
Last Updated: 2025-09-20  
Primary Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)

---

## Scope

Implement the ImprobabilityDrive and `/ask` entry point to produce `AskReport` with `IntentFrame`(s) and `AffordanceTags`, all behind feature flags. Integrate read-only KB lookups, ontology management, deterministic NLU baseline, and planner handoff without altering existing `/plan → /do` flows by default.

## Non-Goals

- No external ML dependencies or networked NLU model in Phase 0–2.
- No planner multi-step expansion beyond existing AVA Level 1.
- No write operations through MCP; executor remains the sole write path.

## Phases

### Phase 0 — Contracts & Flags
- Deliverables:
  - Pydantic v2 models for `AskReport`, `IntentFrame`, `AffordanceTags`.
  - Feature flags: `features.improbability_drive`, `features.ask` (default false).
  - Serialization helpers and golden tests.
- Validation:
  - `make test` for round-trip and schema validation.
- Rollback:
  - Flags disabled; no user-visible changes.

### Phase 1 — /ask Handler & Observability
- Deliverables:
  - `/ask` handler with responder abstraction and command registry.
  - Structured logs and counters: `ask.received`, `ask.emitted`, `ask.failed`.
- Validation:
  - Web CLI tests (enabled/disabled), Discord interaction tests if applicable.
- Rollback:
  - Disable flags to route away from `/ask`.

### Phase 2 — NLU & Tagging Scaffold (Deterministic)
- Deliverables:
  - Rule-based parser for action, actor, object/target refs.
  - AffordanceTags extractor referencing a seed ontology.
- Validation:
  - Golden tests with paraphrases, empty/ambiguous cases; coverage for tag counts.
- Rollback:
  - Keep handler but emit minimal AskReport (no tags) when sub-flag disabled.

### Phase 3 — KB Adapter (Read-only) & Caching
- Deliverables:
  - Repo-backed KB adapter for entity normalization and alternative suggestions.
  - Bounded caching with metrics: `kb.lookup.hit`, `kb.lookup.miss`.
- Validation:
  - Unit tests on canonical and ambiguous entities; timeout/bounds.
- Rollback:
  - Disable KB sub-flag to bypass lookups.

### Phase 4 — Ontology Management & Validation
- Deliverables:
  - Ontology schema and seed under `contracts/` or `prompts/`.
  - Linter/validator integrated into `scripts/validate_prompts_and_contracts.py` and CI.
- Validation:
  - Script exits non-zero on invalid changes; docs on governance.
- Rollback:
  - Revert ontology change; tags degrade gracefully to `unknown:*`.

### Phase 5 — Planner Handoff (AskReport → Plan)
- Deliverables:
  - Adapter mapping AskReport to planner inputs under a flag.
  - Parity tests for roll/check/attack previews.
- Validation:
  - Zero-diff comparisons with existing fixtures.
- Rollback:
  - Disable handoff flag to revert to legacy planner input path.

### Phase 6 — Privacy/Redaction & Operational Hardening
- Deliverables:
  - Redaction filters, payload/time bounds, runbook for canary rollout.
- Validation:
  - Unit tests for redaction and limit enforcement; manual smoke checks.
- Rollback:
  - Disable feature flags or reduce bounds via config.

---

## Feature Flags

- features.improbability_drive (bool, default=false)
- features.ask (bool, default=false)
- Sub-flags (optional):
  - features.ask_nlu_rule_based (default=true)
  - features.ask_kb_lookup (default=false)
  - features.ask_planner_handoff (default=false)

All new flags must be plumbed into the existing config dataclass and `config.toml` with comments.

---

## Test Strategy

- Unit tests: models round-trip, parser/tagger/KB adapter with golden fixtures.
- Integration tests: `/ask` handler enabled/disabled, planner handoff parity (preview/apply unaffected).
- Observability tests: metric increments via reset/get helpers; structured logs present with key fields.
- Privacy tests: redaction of PII-like tokens and bounded input enforcement.

---

## Observability

- Logs: ask.initiated, ask.completed, ask.rejected (with reason), tag.count, kb.lookup.{hit,miss}
- Metrics: counters named under `ask.*` and `kb.*` namespaces; percentiles not required initially.
- ActivityLog: mirror AVA Phase 6 patterns when available; include `ask_id` or reuse `plan_id` linkage per ADR updates.

---

## Rollout Plan

1. Dev: Enable `features.improbability_drive` and `features.ask` in dev only; monitor logs and counters.
2. Canary: Enable for a small cohort; ensure zero regression in planner preview/apply parity.
3. GA: Enable by default after stability period; keep rollback toggle for one release cycle.

Rollback triggers: spike in ask.failed, tag.count anomalies, KB timeouts, or privacy filter violations.

---

## Dependencies & Risks

- Depends on AVA contracts and planner adapters; requires logging and metrics helpers.
- Privacy review for input handling and ActivityLog storage.
- Potential schema drift between AskReport and planner inputs; mitigated by adapters and tests.

---

## Open Questions

- Should ontology live under `contracts/` vs `prompts/`? Initial proposal: `contracts/ontology/` with versioning.
- How to identify actors in multi-speaker channels? Candidate: infer from invocation context plus explicit mentions.
- Where to persist AskReport for observability without long-term retention? Candidate: short-lived cache + ActivityLog link.

---

## How to Run (developer)

- Update `config.toml` to enable flags in a dev branch and run the service:

```powershell
# Optional dev overrides; keep defaults off in committed config
# [features]
# improbability_drive = true
# ask = true

# Use Makefile targets per AGENTS.md
make dev
```

Smoke test with Web CLI or Discord stub once `/ask` exists. Validate counters via logs or metrics endpoint if available.

---

## References

- Architecture: /docs/architecture/action-validation-architecture.md
- AVA Epic: /docs/implementation/epics/EPIC-AVA-001-action-validation-architecture.md
- AIDD Governance: /docs/implementation/dor-dod-guide.md
