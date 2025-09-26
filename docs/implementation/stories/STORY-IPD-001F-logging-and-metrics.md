# STORY-IPD-001F — Logging, metrics, and ActivityLog linkage

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Partially Done (not properly initiated)
Owner: Observability WG

## Summary
Standardize logs and counters for /ask and tagging; integrate with ActivityLog when Phase 6 assets exist.
 
---

## Implementation assessment (evidence-based)

This section applies the repository’s review template (PROMPT-VALIDATE-STORY-IMPLEMENTATION) to assess current state and specify the remaining work precisely.

- Basic Info
	- Story: STORY-IPD-001F — Logging, metrics, and ActivityLog linkage
	- Feature flags in scope (defaults from `config.toml`):
		- `[features].improbability_drive=true`
		- `[features].ask.enabled=true` with sub-flags: `nlu_rule_based=true`, `kb_lookup=false`, `nlu_debug=true`
		- `[features].activity_log=true` (linkage pending — see gaps below)
		- `[features].events=false` (CDA event substrate staged off by default)
	- Affected modules:
		- Handler: `src/Adventorator/commands/ask.py`
		- NLU scaffold: `src/Adventorator/ask_nlu.py`
		- Logging helpers: `src/Adventorator/action_validation/logging_utils.py`
		- Metrics shim: `src/Adventorator/metrics.py`
		- Config/knobs: `config.toml` under `[features]`, `[features.ask]`, `[ask.kb]`, `[logging]`

- Overall Status: Partial
	- Implemented: structured logs via `log_event(...)`, counters for ask lifecycle, a duration histogram, and unit tests asserting metric increments and user-visible behavior.
	- Missing: log field assertions in tests; `kb.lookup.hit/miss` counters (only `kb.lookup.integration_error` present); ActivityLog persistence path behind `features.activity_log` (planned, not wired).
	- Defaults policy misalignment: IPD flags are enabled by default in `config.toml`, while repo guidance favors new behavior defaulting to disabled; capture and justify (dev-only) or adjust in follow-up.

### Section Results (with evidence)

1) Project Guidelines — Status: Meets (partial)
	 - Evidence:
		 - Command registry/responder used: `@slash_command(...)` in `src/Adventorator/commands/ask.py`.
		 - Structured logging via helpers: `from Adventorator.action_validation.logging_utils import log_event` and calls at “initiated”, “failed”, “kb_lookup”, “completed”.
		 - Metrics via repo shim: `inc_counter("ask.received")`, `inc_counter("ask.failed")`, `inc_counter("ask.ask_report.emitted")`, `observe_histogram("ask.handler.duration", ms)`.
		 - FastAPI + repos patterns not directly implicated here; no inline SQL.
		 - Defaults policy: see “Configuration & Flags” below for divergence notes.

2) Architecture Designs — Status: Aligned
	 - Evidence:
		 - Observability centralized in helpers (`logging_utils.py`, `metrics.py`).
		 - CDA events remain disabled (`[features].events=false`), avoiding premature coupling; logs/metrics use `ask.*` namespace per story scope.

3) Story Details — Status: Partial
	 - Evidence vs acceptance criteria:
		 - Structured logs: present via `log_event` in `ask.py` and `ask_nlu.py` (debug-only). Tests don’t assert fields yet.
		 - Metrics counters: present for `ask.received`, `ask.failed`, `ask.ask_report.emitted`; histogram `ask.handler.duration` recorded. `kb.lookup.hit/miss` not implemented (gap).
		 - ActivityLog linkage: not implemented; flagged in Tasks as TODO.

4) Implementation Status — Status: Exercised via unit tests (metrics asserted)
	 - Evidence:
		 - `tests/test_ask_handler.py` asserts increments of `ask.received` and `ask.ask_report.emitted`, and disabled-path behavior with zero counters.
		 - `tests/test_ask_handler_empty_input.py` asserts `ask.failed` increment for empty input when enabled.
		 - `tests/test_ask_handler_echo.py` validates safe echo and truncation logic.

5) Acceptance Criteria — Status: Partial
	 - Deterministic behavior: NLU scaffold deterministic and offline.
	 - Metrics/logging: key ask.* counters exist and are asserted; `kb.lookup.*` partial; tests don’t capture structured logs.
	 - ActivityLog linkage: missing.

6) Contracts & Compatibility — Status: Compatible
	 - No breaking changes to existing handlers; `/ask` remains fully gated behind `features.improbability_drive` and `features.ask`.
	 - CDA contracts not impacted; events remain disabled by default. See CDA alignment below.

7) Test Strategy — Status: Adequate for current scope, expand for logs/KB
	 - Existing: metric increments and content assertions.
	 - Needed: tests for log fields (using a structlog test sink) and KB lookup counters once implemented.

### Configuration & knobs to verify

- `[features]` (from `config.toml`)
	- `improbability_drive=true` (Enabled by default — diverges from “defaults off” guidance; either justify as dev-only or flip to false outside dev profiles.)
	- `events=false` (CDA off)
	- `activity_log=true` (linkage not yet wired; safe to keep true while no-op)
	- `ask = { enabled=true, nlu_rule_based=true, nlu_debug=true, kb_lookup=false }`
- `[ask.kb]` (used only when `features.ask.kb_lookup=true`)
	- `timeout_s=0.05`, `max_candidates=5`, `cache_ttl_s=60`, `cache_max_size=1024`, `max_terms_per_call=20`
- Observability
	- `ask.*` counters; histogram name `ask.handler.duration` (flattened under `histo.ask.handler.duration.*` in metrics endpoint).

## Acceptance Criteria
- Structured logging schema established for ask lifecycle events:
	- `ask.initiated`, `ask.failed` (with `error_code`), `ask.kb_lookup`, `ask.completed`.
	- Required fields include stable IDs (e.g., request_id, actor_id when available), tags_count, duration_ms, and kb_source when applicable.
	- Logs conform to the repo logging helpers and redaction policy from Story H (no PII leakage).
- Metrics published via repo shim:
	- Counters: `ask.received`, `ask.failed`, `ask.ask_report.emitted`, `ask.tags.count`.
	- KB counters (only when `features.ask.kb_lookup=true`): `kb.lookup.hit`, `kb.lookup.miss`, and `kb.lookup.integration_error` for exception paths.
	- Histogram: `ask.handler.duration` recorded per request; buckets documented with an expected P95 budget.
- ActivityLog audit-only record (flag-gated):
	- When `features.activity_log=true`, persist a minimal Ask audit record with redaction; when disabled, no writes occur.
	- CDA event substrate remains disabled; no dependency on event tables.
- Disabled path behavior: with IPD or ask flags disabled, `/ask` does not emit counters beyond a disable notice and does not persist ActivityLog.

## Tasks
- [x] **TASK-IPD-LOG-16 — Structured logging via repo helpers.** Present in `/ask` flow and KB adapter; conforms to helper API.
- [x] **TASK-IPD-METRIC-17 — Lifecycle counters and helpers.** ask.* counters exist; tests assert increments; histogram recorded.
- [ ] **TASK-IPD-ACTLOG-18 — ActivityLog audit-only linkage (flag-gated).** Wire persistence behind `features.activity_log`; include redaction and tests for on/off behavior.

### New/clarified tasks from this assessment
- [ ] **TASK-IPD-LOGTEST-19 — Structlog field assertions.** Add tests capturing `ask.initiated/failed/completed/kb_lookup` and assert key fields inc. `error_code` on failures.
- [ ] **TASK-IPD-KBMETRIC-20 — KB hit/miss counters.** Implement `kb.lookup.hit` / `kb.lookup.miss`; retain `kb.lookup.integration_error`; add unit tests for both paths.
- [ ] **TASK-IPD-FLAGS-21 — Defaults policy documentation/flip.** Justify dev-on defaults or flip to disabled-by-default in non-dev profiles; update docs/tests accordingly.
- [ ] **TASK-IPD-OBS-22 — Latency budgets & histogram buckets.** Document SLOs for `ask.handler.duration` and bucket strategy in the observability guide.
- [ ] **TASK-IPD-TAGCOUNT-23 — Tag count metric.** Emit `ask.tags.count` by adding the number of tags per request; add assertions in tests.

## Definition of Ready
- Observability acceptance criteria reviewed; logging schema and metric names enumerated here with owners.
- Alignment with CDA observability taxonomy documented (reuse `events.*` patterns later when events enable; keep CDA off now).
- Privacy/redaction rules from Story H available for ActivityLog audit record.
- Flag plan documented (dev-on justification vs disabled-by-default decision recorded).
- Test plan updated to include logs, KB hit/miss, tag count, and flag-off behavior.
## Definition of Done
- Logging: repository logging guide references new ask events and owners; structlog tests assert required fields including `error_code` on failures.
- Metrics: increments validated for `ask.received/failed/ask_report.emitted`, `ask.tags.count`, and KB `hit/miss` when enabled; histogram presence verified.
- ActivityLog: audit-only record persisted when `features.activity_log=true`; redaction verified; no writes when disabled.
- Documentation: this story updated with final schema, tasks, and results; observability guide notes histogram SLOs; flag defaults documented or flipped.
- Quality gates: make format, lint, type, and test all PASS; results summarized in PR.
 - Traceability: references and links to code/tests updated; CDA remains disabled and unaffected.

## Test Plan
- Log field tests: capture structlog via a test sink and assert presence/shape of fields for `ask.initiated/failed/completed/kb_lookup` (incl. `error_code` on failures).
- Counter tests: assert increments for `ask.received`, `ask.failed`, and `ask.ask_report.emitted` on enabled paths; zero on disabled paths.
- KB metrics tests: with `features.ask.kb_lookup=true`, simulate adapter replies to drive `kb.lookup.hit/miss`; ensure `integration_error` path increments only that counter.
- Tag count tests: assert `ask.tags.count` increments by the number of tags per request produced by the deterministic NLU scaffold.
- Disabled path tests: with relevant flags off, ensure no ActivityLog writes and minimal/no counters beyond disable notice.

## Observability
- Counters and histogram: ask.* and kb.* counters via shim; `ask.handler.duration` histogram; SLO budgets documented.
- Structured logs: INFO-level with standardized keys via logging helpers; redaction applied per Story H.
- Traces: add span `interactions/ask.handle` with tracing backend (scoped to this handler).

Note on status: This story was not formally initiated; metrics/logging were implemented opportunistically alongside other work. ActivityLog linkage and tracing remain open.

## Risks & Mitigations
- Over-logging PII: use redaction filters from Story H; review/limit log keys to stable IDs and counts.
- Defaults confusion: document or flip IPD defaults to avoid accidental enablement outside dev environments.
- Future CDA coupling: keep ActivityLog and ask.* observability independent until events are enabled (CDA off by default).

## Dependencies
 - Story B (/ask handler) and Story H (privacy redaction).
 - CDA CORE epic for later event observability parity; do not enable `[features].events` as part of this story.

## Feature Flags
- Gating: `features.improbability_drive` and `features.ask.*` control `/ask`; ActivityLog gated by `features.activity_log`; CDA events remain off (`features.events=false`).
- KB metrics: only active when `features.ask.kb_lookup=true`.
- Defaults: use values from `config.toml` (document rationale or flip to disabled-by-default outside dev profiles).

## Traceability
- Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
- Handler: `src/Adventorator/commands/ask.py`; NLU scaffold: `src/Adventorator/ask_nlu.py`.
- Logging/Metrics helpers: `src/Adventorator/action_validation/logging_utils.py`, `src/Adventorator/metrics.py`.
- Tests: `tests/test_ask_handler.py`, `tests/test_ask_handler_empty_input.py`, `tests/test_ask_handler_echo.py` (and new tests to be added for logs/KB/tag count).

## Story decomposition and implementation plan (test- and contract-first)

Contract overview
- Inputs: `/ask` interaction with text; config flags under `[features]` and `[features.ask]`; optional KB adapter when `kb_lookup=true`.
- Outputs: structured log events (`ask.initiated`, `ask.failed`, `ask.kb_lookup`, `ask.completed`), counters (`ask.*`, `kb.lookup.*`), histogram (`ask.handler.duration`), optional ActivityLog audit record when enabled.
- Error modes: empty input (validation failure), KB timeout/integration error, feature flags disabled.
- Success criteria: tests assert counters/log fields deterministically; ActivityLog gated and redacted; no CDA event dependency.

Implementation steps (phased)
1) Finalize logging schema and metric names (no code changes)
	- Document fields (actor_id, request_id, error_code, tags_count, kb_source, duration_ms) inline in this story and reference logging utils.
	- Map to tasks: LOGTEST-19, TAGCOUNT-23, KBMETRIC-20.

2) Add test fixtures and unit tests for logs (no new prod behavior)
	- Create a structlog test sink/fixture; capture and assert fields for `ask.initiated/failed/completed/kb_lookup`.
	- Update tests to reset counters per-test and assert histogram presence.
	- Task: LOGTEST-19.

3) Implement KB hit/miss counters behind `features.ask.kb_lookup`
	- In KB path, increment `kb.lookup.hit` when results returned, `kb.lookup.miss` when none; retain `kb.lookup.integration_error` on exceptions.
	- Add tests toggling `features.ask.kb_lookup=true` to exercise both paths.
	- Task: KBMETRIC-20.

4) Emit tag count metric
	- After NLU/tagging, increment `ask.tags.count` by number of tags for the request.
	- Add assertions in existing `test_ask_handler*` or a new test.
	- Task: TAGCOUNT-23.

5) ActivityLog audit-only wiring (flag-gated)
	- When `features.activity_log=true`, persist a minimal Ask audit record with redaction (per Story H) and no CDA dependency.
	- Add tests for flag off/on and redaction behavior.
	- Task: ACTLOG-18.

6) Defaults policy clarity
	- Either justify dev-on defaults in epic/story or flip to disabled-by-default in non-dev profiles; adjust tests/docs accordingly.
	- Task: FLAGS-21.

7) Document latency budgets
	- Specify expected SLO and histogram buckets for `ask.handler.duration`; add note to observability guide.
	- Task: OBS-22.

Edge cases to cover in tests
- Flags disabled: no counters beyond a disable notice; no ActivityLog writes.
- Empty input: `ask.failed` increment, appropriate `error_code` in logs.
- KB integration error: `kb.lookup.integration_error` increment; no hit/miss increments.
- Large tag lists: `ask.tags.count` sums correctly without overflow; ensure truncation where applicable.
- Concurrency: counters remain thread-safe under quick successive calls (basic smoke via small loop if needed).

Quality gates for this story slice
- Build/lint/type/test pass via Makefile targets; new tests stable and isolated.
- No public API changes; flags defaults behavior documented.

## Alignment analysis — IPD ↔ CDA CORE

- Events remain gated (`features.events=false`) to preserve separation of IPD observability from the CDA event substrate in this phase.
- Metric taxonomy: when CDA is enabled later, reuse/bridge metric names (for example, `events.*`) for append/idempotency; current story confines metrics to `ask.*` and `kb.*`.
- ActivityLog linkage: audit-only AskRecord behind `features.activity_log` with redaction (Story H); no dependency on CDA event tables.
- Defaults policy: acknowledge current dev-on defaults for IPD; either justify in epic/story or flip to disabled-by-default outside dev profiles.
- Adopt CDA event observability patterns later (chain tip, idempotency) once events are enabled; until then, keep `/ask` observability isolated and privacy-safe.
- Epic: EPIC-IPD-001
- Implementation Plan: spans Phases 1, 6

---

## References (evidence)
- Handler and observability
	- `src/Adventorator/commands/ask.py` — uses `log_event`, `inc_counter`, `observe_histogram`.
	- `src/Adventorator/ask_nlu.py` — deterministic NLU; optional debug logging via structlog.
	- `src/Adventorator/action_validation/logging_utils.py` — `log_event`, `log_rejection` helpers.
	- `src/Adventorator/metrics.py` — counters and `observe_histogram` implementation; histogram flattening under `histo.*`.
- Tests
	- `tests/test_ask_handler.py` — asserts `ask.received`, `ask.ask_report.emitted`.
	- `tests/test_ask_handler_empty_input.py` — asserts `ask.failed` on empty input.
	- `tests/test_ask_handler_echo.py` — echo/truncation behavior.
- Configuration
	- `config.toml` — `[features]`, `[features.ask]`, `[ask.kb]`, `[logging]` defaults.
- Cross-Analysis
	- `docs/dev/Cross-Analysis-Alignment-CDA-IPD.md` — flags status, CDA disabled, contract gaps, and alignment recommendations consumed above.
