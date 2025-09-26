# Cross-Analysis Alignment Report — IPD Epic vs CDA Epic

Date: 2025-09-25
Repo: c:/dev/projects/Adventorator
Domains in scope:
- IPD Epic: EPIC-IPD-001 — ImprobabilityDrive Enablement (/ask + NLU/Tagging)
- CDA Epic: EPIC-CDA-CORE-001 — Deterministic Event Substrate (events, canonical JSON, hash chain, idempotency)

## Executive summary

- The two epics are largely complementary: IPD structures player intent (/ask → AskReport) while CDA provides the deterministic event substrate. Today they are not tightly coupled; IPD emits ephemeral summaries and observability, while CDA’s events are disabled by default.
- Feature flags show IPD enabled (features.improbability_drive=true; features.ask.enabled=true), while CDA events are disabled (features.events=false). This staging minimizes risk but diverges from the “new behavior defaults to disabled” guidance for IPD. Recommendation: flip IPD default to disabled until rollout playbook is ready, or document the rationale for enabling in dev.
- IPD contracts are implemented as Pydantic models in code (`AskReport`, `IntentFrame`, `AffordanceTag`), with strict validation (extra=forbid). JSON schema artifacts under `contracts/ask/v1/` are not found; recommend adding them and integrating into the existing validation script.
- CDA substrate utilities exist (`events/envelope.py`: canonical encoding, payload and envelope hashing, idempotency key v1/v2 helpers, chain verification). Alembic migration files exist; events feature remains gated off in config by default.
- Integration surface: planner and executor stubs can adopt CDA idempotency v2 helper. IPD’s AskReport handoff to planner is planned but not wired; ActivityLog linkage for IPD is also planned. Recommend a bridging story to optionally persist AskReports to ActivityLog or emit audit-only seed events behind flags.
- Observability and defensive programming are strong: strict models (extra=forbid), robust flag gating, try/except fences around KB lookups, no inline SQL in handlers, metrics/logging helpers used consistently. A few gaps remain (ask JSON contract, feature default policy, ActivityLog linkage, event-append logs/metrics when events are later enabled).

## Scope and inputs

- Epics
	- IPD: `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md`
	- CDA: `docs/implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md`
- Key source modules
	- FastAPI entry: `src/Adventorator/app.py` (POST /interactions; GET /healthz, /metrics)
	- IPD: `src/Adventorator/commands/ask.py`, `src/Adventorator/schemas.py`, `src/Adventorator/ask_nlu.py`, `src/Adventorator/kb/adapter.py`
	- CDA: `src/Adventorator/events/envelope.py`, `src/Adventorator/canonical_json.py`, `src/Adventorator/importer.py`
- Contracts & artifacts
	- Entities/Edges: `contracts/entities/entity.v1.json`, `contracts/edges/edge.v1.json`
	- Seed event contracts: `contracts/events/seed/*.v1.json`
	- Encounter OpenAPI: `contracts/http/encounter/v1/encounter-openapi.json`
	- Ask JSON contract: not found under `contracts/ask/v1/` (gap)
- Tests (representative)
	- IPD: `tests/test_ask_handler.py`, `tests/test_ask_handler_echo.py`, `tests/test_ask_handler_empty_input.py`
	- CDA: `tests/test_canonical_json.py`, `tests/test_canonical_json_golden_vectors.py`, `tests/test_action_validation_*`, encounter/executor tests for integration context
- Config & flags
	- `config.toml` (observed flags):
		- `[features] events=false, action_validation=true, predicate_gate=true, improbability_drive=true, ask={ enabled=true, nlu_rule_based=true, nlu_debug=true, kb_lookup=false }`
		- `[ask.kb]` limits: timeouts, cache config
		- `[features.retrieval] enabled=true` (provider=none)

## Domain survey and artifacts

### IPD Epic (EPIC-IPD-001)

- Goals: Parse free-form input into a structured AskReport (IntentFrame + AffordanceTags) to enable planner/tooling while keeping risk gated via flags.
- Entry point: `/interactions` → command registry → `@slash_command("ask")` in `src/Adventorator/commands/ask.py`.
- Models: `AskReport`, `IntentFrame`, `AffordanceTag` in `src/Adventorator/schemas.py` (extra=forbid; helpers to/from JSON).
- Flags (Settings/TOML): `features.improbability_drive`, `features.ask` (+ sub-flags: `nlu_rule_based`, `kb_lookup`, `nlu_debug`, `planner_handoff`).
- Defensive behaviors:
	- Disabled path returns clear “/ask is currently disabled.”, no side effects.
	- Empty input: structured log, counter increment, and user message; exits early.
	- KB adapter guarded by try/except; failures do not break user flow; bounded by timeouts and cache sizing.
	- Ephemeral debug output only when `nlu_debug=true`.
- Observability: `log_event()` calls, counters (`ask.received`, `ask.failed`, `ask.ask_report.emitted`), histogram for handler duration.
- Planned integrations: Planner handoff (Story G), ActivityLog linkage (Story F), ontology validation extension (Story E).

### CDA Epic (EPIC-CDA-CORE-001)

- Goals: Deterministic event substrate with canonical JSON, hash chain, idempotency keys, and replay ordinal guarantees.
- Utilities: `src/Adventorator/events/envelope.py`
	- `canonical_json_bytes(...)` uses dedicated canonical encoder (ADR-0007)
	- `compute_payload_hash`, `compute_envelope_hash`
	- `compute_idempotency_key` (v1) and `compute_idempotency_key_v2` (ADR-aligned)
	- `verify_hash_chain(events)` with structured logging + metric on mismatch
	- `GenesisEvent` helper (genesis invariants)
- Migrations: `migrations/versions/cda001a0001_event_envelope_upgrade.py` (presence indicates envelope work; full constraint details tracked under the epic)
- Flags: `[features].events=false` (CDA is staged off by default)
- Observability: metrics documented (`events.applied`, `events.hash_mismatch`, `events.idempotent_reuse`), structured logs planned (Story 001E)

## Interface and schema compatibility

- IPD AskReport vs CDA Events
	- AskReport is a transient intent summary today. It is not yet persisted as an event. No direct schema binding exists, which reduces coupling risk but delays traceability.
	- CDA events require canonical payload rules (no floats, Unicode NFC, null elision). IPD models already enforce strict typing and extra=forbid, lowering risk of illegal payload shapes if/when a persistence path is added.
	- Recommendation: If persisting AskReport-like audit events later, define a minimal event type (e.g., `ask.intent.parsed`) with an explicit versioned payload schema that aligns with CDA canonical policy.

- Endpoints and command flow
	- `/interactions` (Discord/Web CLI) → command registry → `ask` (IPD) and other commands (e.g., `encounter status`).
	- Health and metrics endpoints exist and are unrelated to cross-domain contracts but useful for smoke checks.

- Contracts repo state
	- Entities/Edges/Seed Events HTTP/Encounter contracts exist; Ask contract artifacts (JSON schema) are not present. The code-first Pydantic approach is sound but should be mirrored by versioned JSON contracts in `contracts/ask/v1/` for consistency with AIDD pipeline and validation scripts.

## Naming, flags, and consistency checks

- Flag mapping (Settings ↔ TOML):
	- IPD: `features.improbability_drive`, `features.ask` (+ nested flags) — correctly reflected in both code and TOML.
	- CDA: `features.events` — disabled in TOML.
- Default policy alignment: AGENTS.md says “new behavior must default to disabled.” Current TOML enables IPD by default in dev: `improbability_drive=true`, `ask.enabled=true`. Either justify in docs (dev-only convenience) or revert defaults to false and instruct enabling via local overrides.
- Logging/metrics: IPD uses `action_validation.logging_utils.log_event` and `Adventorator.metrics` helpers; CDA code references metrics and logging helpers. Names in epics/tests are consistent with present modules.

## Risks and gaps (defensive programming focus)

- R1: Ask JSON contract artifacts missing (contracts/ask/v1). Severity: Medium. Likelihood: High (code evolves without schema lock). Impact: Drift and weak cross-repo compatibility.
- R2: IPD defaults enabled in TOML contradict policy. Severity: Low/Medium. Likelihood: Certain. Impact: Surprise enablement in dev; minor if scoped to dev only.
- R3: No ActivityLog linkage for AskReport. Severity: Medium. Likelihood: Medium. Impact: Reduced traceability of user intent; harder incident triage.
- R4: Idempotency v2 not yet integrated in executor end-to-end. Severity: Medium. Likelihood: High (work planned). Impact: Duplicate events on retries when CDA is enabled later.
- R5: Event-append structured logs/metrics pending (when events on). Severity: Medium. Likelihood: Medium. Impact: Limited observability for chain integrity post-enable.
- R6: Planner handoff (AskReport → Plan) not wired. Severity: Low/Medium. Impact: Limits IPD utility; contained by flags.

## Recommendations (prioritized)

P0 — Before enabling CDA events or broadening IPD usage
- Add Ask JSON contracts and validation
	- Create `contracts/ask/v1/ask-report.v1.json` covering AskReport/IntentFrame/AffordanceTag.
	- Extend `scripts/validate_prompts_and_contracts.py` to validate ask contracts. Tie to make quality-gates.
- Align defaults with policy
	- Either: set `[features].improbability_drive=false` and `ask=false` by default, or document dev-only default-on policy in EPIC-IPD-001 and AGENTS.md references.
- Prepare executor for idempotency v2
	- Adopt `compute_idempotency_key_v2` in executor path (shadow mode if needed) with logging of mismatches vs v1; do not enable events yet.

P1 — Strengthen traceability and observability
- ActivityLog linkage for AskReport
	- When `features.activity_log=true`, persist a compact AskReport audit record (or produce a structured ActivityLog event) with privacy-safe redaction.
- Event-append observability (when events are later enabled)
	- Add structured logs on append with envelope fields (campaign_id, replay_ordinal, idempotency_key hex prefix) and counters (`events.applied`, `events.idempotent_reuse`).
- Planner handoff adapter (flagged)
	- Implement AskReport → Planner adapter under `features.ask.planner_handoff`. Parity tests ensure no behavioral regressions.

P2 — Hardening and governance
- Ontology validation extension
	- Integrate ontology checks into the validation script; ensure NLU tags correspond to governed ontology entries.
- Docs and runbooks
	- Add a short “IPD ↔ CDA alignment” section to each epic summarizing the handshake and flags. Include smoke steps for `/ask` and chain verification.

## Concrete artifacts and references

- IPD Epic: `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md`
- CDA Epic: `docs/implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md`
- Entry/Commands: `src/Adventorator/app.py`, `src/Adventorator/commands/ask.py`, `src/Adventorator/commands/encounter.py`
- Models: `src/Adventorator/schemas.py` (AskReport, IntentFrame, AffordanceTag)
- CDA substrate: `src/Adventorator/events/envelope.py`, `src/Adventorator/canonical_json.py`
- Importer (CDA import path): `src/Adventorator/importer.py`
- Contracts: `contracts/entities/entity.v1.json`, `contracts/edges/edge.v1.json`, `contracts/events/seed/*.v1.json`, `contracts/http/encounter/v1/encounter-openapi.json`
- Config: `config.toml` — `[features] events=false`, `improbability_drive=true`, `ask.enabled=true` (with sub-flags), `[ask.kb]` limits, `[features.retrieval] enabled=true`
- Representative tests: `tests/test_ask_handler*.py`, `tests/test_canonical_json*.py`, `tests/test_action_validation_*`

## Compatibility and edge cases (defensive checklist)

- Empty/null inputs: `/ask` path already guards and logs; ensure future persistence path rejects empty AskReport payloads.
- Large/slow paths: KB lookups bounded by `ask.kb.timeout_s` and cache; maintain safeguards when planner handoff is enabled (timeouts, size limits).
- Auth/permissions: Discord signature verification already enforced at `/interactions`; local dev overrides guarded.
- Concurrency/idempotency: Adopt idempotency v2 in executor before enabling events; add race tests asserting exactly one persisted event.
- Serialization invariants: CDA canonical JSON forbids floats/NaN; ensure any AskReport-to-event adapter applies canonical encoding and rejects unsupported types early.

## Reference log (proposed changes and rationale)

- RL-001 — Add ask contract JSONs under `contracts/ask/v1/` and wire into `scripts/validate_prompts_and_contracts.py`. Rationale: lock schema; enable validation in CI; align with AIDD.
- RL-002 — Update IPD defaults to disabled in `config.toml` (or document dev-only enablement). Rationale: adhere to feature flag policy; reduce surprise activation.
- RL-003 — Integrate `compute_idempotency_key_v2` in executor (shadow then enforce). Rationale: ensure retry collapse; prepare for events enablement.
- RL-004 — Add ActivityLog linkage for AskReport (behind `features.activity_log`). Rationale: traceability and auditability.
- RL-005 — Add event-append logs and counters when events enabled. Rationale: operational visibility and triage.
- RL-006 — Extend ontology validation in the validation script. Rationale: prevent tag drift.

## Ongoing cadence

- The following review breakpoints are enforced by CI and local pre-merge jobs; each defines triggers, checks, and exit criteria tied to RL-001…RL-006.

1) PRs that touch feature flags or `config.toml` (policy guardrail)
	- Trigger: Any change to `[features]` or nested `ask.*` keys.
	- Checks:
	  - Verify new flags default to disabled; detect default-enabled deltas and require justification note in PR description referencing AGENTS.md.
	  - Diff scan for flips of `features.improbability_drive` and `features.ask.enabled` vs policy; warn on enablement outside dev-only contexts.
	- Exit criteria: Policy compliance or documented exception; CI status “Flag policy: PASS”.

2) RL-001 completion and follow-on changes (Ask contracts present and validated)
	- Trigger: Initial addition or modification of files under `contracts/ask/v1/` or `src/Adventorator/schemas.py` models: AskReport/IntentFrame/AffordanceTag.
	- Checks:
	  - Schema presence: `contracts/ask/v1/ask-report.v1.json` (and nested components) must exist.
	  - Contract ⇄ model parity: run the contract validation script to ensure Pydantic models match JSON Schemas (extra=forbid, required fields).
	  - Coverage floor: tests covering Ask schema validation ≥ 90% lines in `schemas.py` touched regions.
	- Exit criteria: Contracts validated, coverage ≥ floor; CI status “Ask contract: PASS”.

3) Idempotency v2 adoption in executor (RL-003) — shadow then enforce
	- Trigger: Any change invoking `compute_idempotency_key_v2` or executor path.
	- Checks:
	  - Shadow-mode metric: mismatch rate between v1 and v2 keys must be 0 across the targeted test suite (`test_action_validation_*`, executor/encounter tests).
	  - Concurrency test: duplicate submit under N≥5 parallel clients yields exactly one persisted effect (simulation tests) when events are enabled in CI sandbox.
	- Exit criteria: 0 mismatches; concurrency test green; then allow switching from shadow to enforce; CI status “Idem v2: PASS”.

4) ActivityLog linkage for AskReport (RL-004) — privacy gating
	- Trigger: Enabling `features.activity_log` path for AskReport audit record.
	- Checks:
	  - Redaction policy: No free-form user text fields persisted without explicit allowlist; hashed/trimmed IDs only.
	  - Observability: counters increment (`ask.audit.persisted`) and structured log record emitted.
	- Exit criteria: Redaction lints PASS; tests confirm record shape; CI status “Ask audit: PASS”.

5) Event substrate readiness before enabling `[features].events=true` (pre-enable gate)
	- Trigger: Any PR proposing to enable events in any environment.
	- Checks:
	  - Canonical JSON invariants: golden vectors unchanged; `tests/test_canonical_json*` all green.
	  - Hash chain: end-to-end chain verification tests PASS; metric `events.hash_mismatch` = 0 in CI run.
	  - Envelope/idempotency budgets: `events.idempotent_reuse` = 0 in replay tests.
	- Exit criteria: All substrate checks PASS in CI; canary plan documented in PR; CI status “CDA pre-enable: PASS”.

6) Event enablement rollout (progressive)
	- Trigger: Merge to enable events.
	- Checks:
	  - Stage 1 (dev): append logs include envelope fields (campaign_id, replay_ordinal, idem_key prefix); counters `events.applied` observed > 0 and no mismatches.
	  - Stage 2 (canary): same checks + rollback instructions validated; smoke replay green.
	  - Stage 3 (full): baseline SLOs stable; no integrity regressions across 24h.
	- Exit criteria: Stage checklist complete and recorded in Reference Log; CI status “CDA rollout: STAGE n/3”.

7) Planner handoff adapter for AskReport (flagged)
	- Trigger: Enabling `features.ask.planner_handoff`.
	- Checks: Timeout bounds respected; adapter unit tests PASS; no behavior change when flag off; parity tests between direct and adapter paths.
	- Exit criteria: Tests PASS; CI status “Planner handoff: PASS”.

8) Ontology validation extension (RL-006)
	- Trigger: NLU tag changes or ontology updates.
	- Checks: All emitted tags resolve against governed ontology; unknowns fail fast in validation script; coverage includes negative cases.
	- Exit criteria: Zero unknown tags; CI status “Ontology: PASS”.

9) Scheduled governance review (weekly) and after each RL item lands
	- Inputs: Trend of key metrics (mismatch/idempotent_reuse), coverage deltas, open exceptions to flag policy.
	- Outputs: Updates to rollout plan, backlog grooming for follow-ups, and confirmation of next-stage gates.

Automation and artifacts
- CI appends RL item status with PR/issue links to `docs/dev/alignment/REFERENCE_LOG.md`.
- Lightweight ADRs updated via templates on material decisions (policy exceptions, rollout gates) and cross-referenced from the epics.

## Quality gates (how to verify locally)

Optional commands for developers:

```powershell
# this specific dev environment cannot run make directly
# instead, activate the virtual environment and run the commands directly 
.\.venv\Scripts\Activate.ps1
# Lint, type-check, tests
ruff check --fix src tests
mypy src
pytest
```

## Completion summary

Requirements coverage
- Inventory and comparison of schemas/interfaces: Done (see “Domain survey and artifacts”).
- Overlaps, risks, and conflicts identified: Done (see “Risks and gaps”).
- Prioritized corrective actions: Done (see “Recommendations”).
- Cadence/protocol for ongoing review: Done (see “Ongoing cadence”).

Notes
- Keep new behavior default-disabled unless explicitly justified for dev-only scenarios, and document any exceptions in epics/AGENTS.md references.
- When enabling CDA events, execute the observability and idempotency steps first to avoid integrity gaps.

