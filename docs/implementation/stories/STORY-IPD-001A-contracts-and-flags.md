# STORY-IPD-001A — Contracts and feature flag scaffolding

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Contracts/Config WG

## Summary
Introduce canonical Pydantic v2 models for AskReport, IntentFrame, and AffordanceTags with serialization helpers and adapters as needed. Add feature flags to gate rollout.

## Acceptance Criteria
- Models align with ARCH-AVA-001 contracts and pass round-trip serialization tests.
- Feature flags `features.improbability_drive` and `features.ask` default to false.
- Contract versioning documented (semver-like), with converters for any legacy planner inputs.
 - Settings dataclass and TOML mapping shapes are specified in this story and epics; no code change required yet.

## Tasks
- [ ] TASK-IPD-SCHEMA-01 — Implement AskReport/IntentFrame/AffordanceTags models and JSON helpers.
- [ ] TASK-IPD-FLAGS-02 — Extend config.toml and config dataclass with flags (default off) and docs.
- [ ] TASK-IPD-TEST-03 — Add round-trip tests using deterministic fixtures.
 - [ ] TASK-IPD-DOC-04 — Add commented TOML examples and update configuration docs.

## Definition of Ready
- Contract change proposal reviewed with planner maintainers.
- Test plan outlines identity fixtures and error handling.

## Definition of Done
- Conversion tests committed with golden outputs.
- Flag documentation updated in feature flag guide.

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
