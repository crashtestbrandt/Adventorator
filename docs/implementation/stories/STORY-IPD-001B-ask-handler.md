# STORY-IPD-001B — /ask command handler and responder

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Interactions/Responder WG

## Summary & Scope
What this Story delivers. Include both in-scope and out-of-scope.

- In scope:
	- Introduce `/ask` command handler behind feature flags `features.improbability_drive` AND `features.ask` (both must be true).
	- Implement using registry decorators and responder abstraction per AGENTS.md (e.g., `@slash_command`, `inv.responder.send(...)`).
	- When enabled, accept free-form input and return an ephemeral acknowledgement that safely echoes/truncates the input (no intent/target inference).
	- Minimal validation: reject empty/whitespace-only input with a friendly ephemeral message.
	- Observability stubs: structured logs and counters (`ask.received`, `ask.ask_report.emitted`, `ask.failed`) and a duration histogram for the handler.
	- Configuration gating via existing Settings with defaults preserving current behavior (flags off by default).
- Out of scope:
	- NLU/tagging, KB lookups, and planner handoff (Stories C, D, G).
	- ActivityLog persistence/linkage beyond basic structured logs (Story F).
	- Privacy redaction and size/time bounds (Story H).
	- External network/ML dependencies.

Epic Link: #TBD (EPIC-IPD-001)

## Acceptance Criteria
Concrete, testable criteria (Gherkin welcome):

- [ ] Given `features.improbability_drive=false` OR `features.ask=false` When a user invokes `/ask` via Web CLI or Discord Then the response is an ephemeral "This feature is disabled" message and no other side effects occur.
- [ ] Given `features.improbability_drive=true` AND `features.ask=true` When a user invokes `/ask` with non-empty text Then the bot returns an ephemeral acknowledgement including a safe echo of the text (truncated) and no planner/NLU effects occur.
- [ ] Given the enabled state When `/ask` is invoked Then metrics `ask.received` and `ask.ask_report.emitted` are incremented and logs `ask.initiated` and `ask.completed` are emitted with correlation/request_id if available.
- [ ] Given invalid input (empty/whitespace-only) When `/ask` is invoked with flags enabled Then an ephemeral validation message is returned; `ask.failed` is incremented and `ask.failed` log is emitted.
- [ ] Given concurrent invocations When 10 `/ask` calls are made rapidly Then the handler responds within the p95 latency budget (<= 200ms) with no errors recorded.
 - [ ] Given a dev webhook override (header or settings) When the sink is unreachable Then the command completes without raising; a `discord.followup.network_error` is logged with `base_url_source != default`.

## Contracts & Compatibility
- OpenAPI/Protobuf/GraphQL deltas: None for Story B; this adds a new interaction command only. Ask contract reference: `contracts/ask/v1/ask-report.v1.json` (v1).
- CDCs (consumer/provider): No changes to existing external consumers. `/ask` emits an internal AskReport-shaped payload for observability only; planner consumption is deferred to Story G.
- Versioning & deprecation plan: Continue using AskReport v1; no deprecations introduced in this story.

## Test Strategy
- Unit & property-based tests
	- Unit tests for flag gating, empty-input validation, and responder output shape.
	- Lightweight property tests for input echo truncation (e.g., length cap, unicode handling).
- Contract tests (provider/consumer)
	- Validate any emitted AskReport-shaped payload conforms to `contracts/ask/v1/ask-report.v1.json` (schema presence only; fields minimal in this story).
- Integration slice (service + datastore + 1 dependency)
	- Web CLI and Discord integration tests: disabled path and enabled path ephemeral responses; assert no DB writes.
- Performance budget checks
	- Simple timing around handler path, asserting p95 <= 200ms on CI hardware for short inputs.
- Security/abuse cases
	- Ensure no secrets or full raw input are logged without truncation; reject empty input; no external network calls.
- AI evals (if applicable)
	- N/A in this story (no NLU or model inference).

## Observability
- Metrics
	- ask.received (counter)
	- ask.ask_report.emitted (counter)
	- ask.failed (counter)
	- ask.handler.duration (histogram), p95 budget 200ms
- Logs
	- Structured events via repo helpers: `ask.initiated`, `ask.completed`, `ask.failed` with `request_id`/`correlation_id` when available and an `error_code` on failure.
- Traces
	- Deferred in this story; add span `interactions/ask.handle` in Story F with tracing backend.
- Dashboards/alerts to update
	- Add `/ask` metrics to the interactions dashboard; alert on sustained `ask.failed` rate > 5% or p95 > 200ms for 5m.
	- Note: Dev webhook override network/HTTP errors are logged and non-fatal

## Tasks
- [ ] TASK-IPD-SCHEMA-01 — Define contract deltas (N/A for this story; reference v1 at `contracts/ask/v1/ask-report.v1.json`).
- [ ] TASK-IPD-TEST-06 — Write acceptance tests (Web CLI + Discord; unit/property tests for gating and validation).
- [ ] TASK-IPD-HANDLER-04 — Implement `/ask` handler against tests using registry decorators and responder abstraction.
- [ ] TASK-IPD-OBS-05 — Add metrics/logs/traces per Observability section.
- [ ] TASK-IPD-DOC-07 — Update developer docs/runbook on enabling flags and verifying metrics/logs.

## Definition of Ready (DoR)
- [ ] Acceptance criteria defined
- [ ] Contracts drafted and reviewed (No deltas; using AskReport v1 reference)
- [ ] Test strategy approved
- [ ] Observability plan documented

## Definition of Done (DoD)
- [ ] Acceptance criteria verified by automated tests (unit + integration)
- [ ] Contracts versioned & backward compatible (no changes; schema reference validated)
- [ ] Observability signals implemented and documented (metrics, logs, trace span)
- [ ] Security/SCA/SAST/secrets checks pass; perf within budget (p95 <= 200ms)
- [ ] Docs updated; PR merged with all quality gates green

---

References
- Epic: [/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
- ADR: [/docs/adr/ADR-0005-improbabilitydrive-contracts-and-flags.md](/docs/adr/ADR-0005-improbabilitydrive-contracts-and-flags.md)
- Contract: [/contracts/ask/v1/ask-report.v1.json](/contracts/ask/v1/ask-report.v1.json)
