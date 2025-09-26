# STORY-IPD-001A — Contracts and feature flag scaffolding

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: In Progress
Owner: Contracts/Config WG

## Summary
Introduce canonical Pydantic v2 models for AskReport, IntentFrame, and AffordanceTags with serialization helpers and adapters as needed. Add feature flags to gate rollout. See ADR-0005 for the governance decision on contract registry placement and settings precedence.

## Acceptance Criteria
- Models align with ARCH-AVA-001 contracts and pass round-trip serialization tests.
- Feature flags `features.improbability_drive` and `features.ask` default to false (policy: new behavior defaults disabled). If enabling for dev convenience, the exception MUST be documented in this story and the epic with rationale and rollout notes.
- Contract versioning documented (semver-like), with converters for any legacy planner inputs.
- Settings dataclass and TOML mapping shapes are specified in this story and epics; no code change required yet.
- Ask JSON contract artifact exists under `contracts/ask/v1/` and is validated by the repo validation script (schema parity with runtime models enforced by tests).

## Tasks
- [x] TASK-IPD-SCHEMA-01 — Implement AskReport/IntentFrame/AffordanceTags models and JSON helpers. (Implemented in `src/Adventorator/schemas.py`)
- [x] TASK-IPD-TEST-03 — Add round-trip tests using deterministic fixtures. (See tests under `tests/ask/` and parity test for contract artifact)
- [x] TASK-IPD-CONTRACT-05 — Add Ask JSON contract artifact under `contracts/ask/v1/ask-report.v1.json` and wire to validation script. (Present; ensure script integration is green in CI)
- [ ] TASK-IPD-FLAGS-02 — Extend config.toml and config dataclass with flags (default off) and docs. (Note: current `config.toml` sets `improbability_drive=true` and `ask.enabled=true` in dev; document the exception or flip defaults to false)
- [ ] TASK-IPD-DOC-04 — Add commented TOML examples and update configuration docs.

## Definition of Ready
- Contract change proposal reviewed with planner maintainers.
- Test plan outlines identity fixtures and error handling.
- Alignment inputs captured from CDA substrate (canonical JSON, idempotency policy) to ensure future persistence paths won’t violate CDA rules.
- Feature-flag policy confirmed (defaults disabled) or a documented, time-bound exception recorded with owner and rollback.

## Definition of Done
- Conversion tests committed with golden outputs; schema parity test ensures `AskReport.model_json_schema()` matches `contracts/ask/v1/ask-report.v1.json`.
- Flag documentation updated in feature flag guide; defaults disabled OR documented exception with rollback noted.
- Validation script includes ask contract checks and runs in CI; local `make` quality gates include contract validation.
- Security/lint/type/test gates green; no floats/NaN introduced in AskReport-like paths.

## Test Plan
- Unit tests: round-trip serialize/deserialize; versioned schema compatibility; invalid payload rejection.
- Golden fixtures stored under tests/fixtures/ask/.
 - Ensure stable ordering in JSON serialization where needed for golden comparisons.

## Observability
- None required in this story beyond test logging.

## Risks & Mitigations
- Schema drift: enforce via golden tests and contract version gates.
- Flag misconfiguration: defaults off and config docs updated.

## Dependencies
- ARCH-AVA-001 contracts.
 - ADR-0005 ImprobabilityDrive contracts and flags.

## Feature Flags
- features.improbability_drive (default=false)
- features.ask (default=false)
 - features.ask_nlu_rule_based (default=true)
 - features.ask_kb_lookup (default=false)
 - features.ask_planner_handoff (default=false)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 0 — Contracts & Flags

## Implementation notes (non-binding, to reduce ambiguity)

- Settings dataclass fields in `src/Adventorator/config.py` (add later when implementing):
	- `features_improbability_drive: bool = False`
	- `features_ask: bool = False`
	- `features_ask_nlu_rule_based: bool = True`
	- `features_ask_kb_lookup: bool = False`
	- `features_ask_planner_handoff: bool = False`
- TOML mapping in `_toml_settings_source()`:
	- `[features]` keys: `improbability_drive`, `ask`
	- `[features.ask]` keys: `nlu_rule_based`, `kb_lookup`, `planner_handoff`
- Contracts module (runtime models): `src/Adventorator/schemas.py` (AskReport, IntentFrame, AffordanceTag)
- Contract registry (artifact): `contracts/ask/v1/` JSON schema, validated by `scripts/validate_prompts_and_contracts.py`
- Tests: `tests/ask/` with golden round-trip fixtures

Follow-ups proposed:
- Add a parity test ensuring `AskReport.model_json_schema()` remains in sync with `contracts/ask/v1/ask-report.v1.json`.

---

## Alignment analysis — IPD↔CDA (embedded)

- Contracts placement and validation: Ensures `contracts/ask/v1/` artifacts exist and are validated like other CDA contracts. This reduces drift when later emitting audit events.
- Canonical JSON policy awareness: Although AskReport is not persisted yet, any future AskReport→event adapter must reject floats/NaN and apply canonical encoding per CDA. DoD now guards against introducing incompatible numeric types.
- Feature flag policy alignment: Mirrors CDA’s conservative default-disabled stance for new behavior; deviations must be explicitly documented with rationale.
