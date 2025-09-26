# STORY-IPD-001C — NLU and tagging scaffold (rule-based baseline)

Status: Implemented
Owner: NLU/Ontology WG

## Summary & Scope
Implement a deterministic, rule-based parser for action, actor, and object/target references, plus AffordanceTags extraction from a small seed ontology; include entity normalization hooks. Own the initial token/stopword heuristic. No external NLP or network calls.

- In scope:
	- Deterministic, rule-based parser producing an IntentFrame (action, actor, object/target refs).
	- AffordanceTags extractor with ontology lookups and normalization hooks.
	- Tokenization and stopword heuristic; configurable via code/fixtures (no external models).
	- Fixture-driven unit tests with golden outputs and paraphrase coverage.
	- Optional structured debug logging behind a dev flag; documented limitations and examples.
	- Feature-flag gating via `config.toml` under `[features]`.
- Out of scope:
	- External NLP libraries (e.g., spaCy, NLTK) or ML models; any network calls.
	- Full knowledge-base adapter integration (beyond seed ontology lookup hooks).
	- New metrics/dashboards or tracing; performance tuning beyond basic sanity checks.
	- Security classification/PII detection; advanced normalization beyond seed rules.

Epic Link: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)

## Acceptance Criteria
Concrete, testable criteria (Gherkin welcome):

- [x] Given a user utterance containing an action, actor, and target When parsed Then the same IntentFrame is produced deterministically across runs with no network calls.
- [x] Given tokens that map to ontology entries When tags are extracted Then tags include ontology IDs; unknown tokens surface as `unknown:*` tags.
- [x] Given empty or ambiguous input When parsed Then ambiguity is surfaced in structured fields and tests assert expected fallbacks.
- [x] Unit tests cover varied phrasing and edge cases using fixtures under `tests/fixtures/ask/`.
- [x] Implementation avoids external NLP libraries (e.g., spaCy); solution is strictly rule-based and offline.
- [x] Behavior is gated by `features.improbability_drive` and `features.ask_nlu_rule_based` (default true for the latter) in `config.toml`; optional developer debug aided by `features.ask.nlu_debug` (ephemeral output only).

## Contracts & Compatibility
- OpenAPI/Protobuf/GraphQL deltas: None for this story (no new external API). Seed ontology lives under `contracts/ontology/` (v0.1 seed).
- CDCs (consumer/provider): Internal consumer is the Ask/Interactions layer expecting an `IntentFrame` and `AffordanceTags`. Parser must be backward-compatible with unknown tokens via `unknown:*` sentinel tags.
- Versioning & deprecation plan: Additive-only; unknown tokens tolerated. Behavior behind feature flags to allow safe rollout and rollback.

## Test Strategy
- Unit & fixture-based tests with golden outputs (including paraphrases and edge cases like empty/ambiguous).
- Contract tests: validate shape of `IntentFrame` and `AffordanceTags` against contracts in `contracts/ask/` and ontology expectations in `contracts/ontology/`.
- Integration slice: minimal flow through the Ask handler/responder with the rule-based parser enabled (no network, no external deps).
- Performance: lightweight parsing; no explicit budget in this story, but include a sanity assertion that typical inputs parse within tens of milliseconds on dev hardware.
- Security/abuse cases: input validation; ensure logs do not leak secrets; baseline repository scanners apply.
- AI evals: N/A for this deterministic scaffold.

## Observability
- Metrics: None added in this story (per current decision).
- Logs: Optional structured debug logs with `error_code` for parse/ontology lookup failures; controlled by a dev flag (`features.ask.nlu_debug`).
- Traces: Not introduced in this story.
- Dashboards/alerts: No updates required.

Notes:
- The `/ask` handler currently increments lightweight counters (`ask.received`, `ask.ask_report.emitted`, `ask.failed`) and duration histogram. These are compatible with EPIC-IPD-001F and can remain; they do not introduce coupling or external dependencies.

## Tasks
- [x] #IPD-NLU-Contracts — Define seed ontology under `contracts/ontology/` (v0.1) and align models.
- [x] TASK-IPD-TEST-09 — Acceptance tests (fixture-driven with golden outputs and property-based determinism).
- [x] TASK-IPD-NLU-07 / TASK-IPD-TAGS-08 — Implement deterministic parser and tag extractor.
- [x] #IPD-NLU-Obs — Optional debug logs via `features.ask.nlu_debug`.
- [x] TASK-IPD-DOC-10 — Update docs/runbook (see `docs/dev/ask-nlu-normalization.md`).

## Implementation status and artifacts

Implemented components and their locations:

- Rule-based parser and tagging:
	- `src/Adventorator/ask_nlu.py` — tokens/stopwords, action/target synonym matching, modifier capture, `unknown:*` tags, deterministic and offline.
- Contracts and runtime models:
	- Contract artifact: `contracts/ask/v1/ask-report.v1.json` (OpenAPI marker present per ADR-0005).
	- Runtime models (Pydantic): `src/Adventorator/schemas.py` (`AskReport`, `IntentFrame`, `AffordanceTag`).
	- Schema parity test: `tests/ask/test_contract_parity_with_json_artifact.py`.
- Seed ontology and governance:
	- `contracts/ontology/seed-v0_1.json` (version `0.1`), used by the parser; aligns with Story E placement. Additional schemas and docs live under `contracts/ontology/`.
- Feature flags and gating (per ADR-0005 and Epic config mapping):
	- Settings loader: `src/Adventorator/config.py` (`features_improbability_drive`, `features_ask`, sub-flags incl. `features_ask_nlu_rule_based`, `features_ask_nlu_debug`).
	- Example toggles: `config.toml` under `[features]` and `[features.ask]`.
- Ask command integration slice (behind flags):
	- `src/Adventorator/commands/ask.py` — uses registry decorators and responder abstraction; ephemeral summary; dev debug details when `nlu_debug` enabled.
- Tests and fixtures:
	- Unit/property tests: `tests/ask/test_property_nlu.py`, `tests/ask/test_golden_fixtures.py`, plus fixture-driven parsing tests.
	- Golden fixtures: `tests/fixtures/ask/*.json`.

Quality gates (local run snapshot):
- Unit tests (ask scope) — PASS. Property and fixture tests confirm determinism and expected tags. Round-trip `AskReport` serialization verified.
- Lint/format/type — repository-standard tools apply; no new style/type issues introduced in the touched areas during this story. Full repo checks will continue under CI for broader surfaces.

Alignment checks against ADR-0005 and EPIC-IPD-001:
- Placement: Contracts under `contracts/`; runtime models in `src/Adventorator/schemas.py`; `/ask` handler in `src/Adventorator/commands/` — conforms.
- Feature flags: Implemented with defaults preserving current behavior; sub-flags supported via `[features.ask]` table — conforms.
- Settings precedence: `init > OS env > .env(.local) > TOML > file secrets` — implemented in `Settings.settings_customise_sources` — conforms.
- Observability: Minimal counters and optional debug logs; richer metrics deferred to Story F — conforms.
- No external NLP/network calls — confirmed.

## Definition of Ready (DoR)
- [x] Acceptance criteria defined
- [x] Contracts drafted and reviewed (ontology MVP defined; normalization rules agreed)
- [x] Test strategy approved
- [x] Observability plan documented (debug logs only)

## Definition of Done (DoD)
- [x] Acceptance criteria verified by automated tests
- [x] Contracts versioned & backward compatible (unknown tokens tolerated; CDC checks pass where applicable)
- [x] Observability signals implemented and documented (debug logging behind dev flag)
- [x] Security/SCA/SAST/secrets checks pass; basic perf sanity holds
- [x] Parser/extractor documented with examples and limitations; PR merged with all quality gates green

## Risks & Mitigations
- Overfitting rules: keep coverage broad; add fixtures iteratively.

Additional notes:
- Ontology evolution is governed in Story E; parser reads from the seed file and can tolerate unknown tokens via `unknown:*` tags to preserve forward compatibility.

## Dependencies
- ADR-0005 (contracts/flags/rollout)
- Story E (ontology) may run in parallel for seed ontology.
- Story D (KB adapter) for future normalization enhancements.

## Feature Flags
- features.improbability_drive (gates behavior)
- features.ask_nlu_rule_based (default=true)

## Traceability
---

## Alignment analysis — IPD↔CDA (embedded)

- Determinism and offline operation ensure that if/when AskReport is persisted as an event, payload formation won’t introduce nondeterminism.
- Tagging outputs avoid floats/NaN; any numeric fields introduced later must follow CDA integer-only policy.
- Ontology governance links to importer/ontology registration stories on the CDA side to avoid drift between runtime tags and registered ontology artifacts.
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 2 — NLU & Tagging Scaffold (Deterministic)
