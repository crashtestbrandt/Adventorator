# STORY-IPD-001C — NLU and tagging scaffold (rule-based baseline)

Status: Planned
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

- [ ] Given a user utterance containing an action, actor, and target When parsed Then the same IntentFrame is produced deterministically across runs with no network calls.
- [ ] Given tokens that map to ontology entries When tags are extracted Then tags include ontology IDs; unknown tokens surface as `unknown:*` tags.
- [ ] Given empty or ambiguous input When parsed Then ambiguity is surfaced in structured fields and tests assert expected fallbacks.
- [ ] Unit tests cover varied phrasing and edge cases using fixtures under `tests/fixtures/ask/`.
- [ ] Implementation avoids external NLP libraries (e.g., spaCy); solution is strictly rule-based and offline.
- [ ] Behavior is gated by `features.improbability_drive` and `features.ask_nlu_rule_based` (default true for the latter) in `config.toml`.

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
- Logs: Optional structured debug logs with `error_code` for parse/ontology lookup failures; controlled by a dev flag.
- Traces: Not introduced in this story.
- Dashboards/alerts: No updates required.

## Tasks
- [ ] #IPD-NLU-Contracts — Define contract deltas (if any) and seed ontology details under `contracts/ontology/`.
- [ ] TASK-IPD-TEST-09 — Write acceptance tests (fixture-driven with golden outputs).
- [ ] TASK-IPD-NLU-07 / TASK-IPD-TAGS-08 — Implement parser and tag extractor against tests.
- [ ] #IPD-NLU-Obs — Add optional debug logs (no new metrics/traces in this story).
- [ ] TASK-IPD-DOC-10 — Update docs/runbook (normalization rules and examples in `docs/dev/`).

## Definition of Ready (DoR)
- [ ] Acceptance criteria defined
- [ ] Contracts drafted and reviewed (ontology MVP defined; normalization rules agreed)
- [ ] Test strategy approved
- [ ] Observability plan documented

## Definition of Done (DoD)
- [ ] Acceptance criteria verified by automated tests
- [ ] Contracts versioned & backward compatible (unknown tokens tolerated; CDC checks pass where applicable)
- [ ] Observability signals implemented and documented (debug logging behind dev flag)
- [ ] Security/SCA/SAST/secrets checks pass; basic perf sanity holds
- [ ] Parser/extractor documented with examples and limitations; PR merged with all quality gates green

## Risks & Mitigations
- Overfitting rules: keep coverage broad; add fixtures iteratively.

## Dependencies
- ADR-0005 (contracts/flags/rollout)
- Story E (ontology) may run in parallel for seed ontology.
- Story D (KB adapter) for future normalization enhancements.

## Feature Flags
- features.improbability_drive (gates behavior)
- features.ask_nlu_rule_based (default=true)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 2 — NLU & Tagging Scaffold (Deterministic)
