# Changelog

## Unreleased

### Added
- Metrics: `planner.allowlist.rejected` emitted when planner selects a command outside the allowlist.
- Predicate gate metrics: `predicate.gate.ok`, `predicate.gate.error`, and per‑failure `predicate.gate.fail_reason.<code>` for each failing predicate (e.g. `predicate.gate.fail_reason.dc_out_of_bounds`).
- Planner cache metrics: `planner.cache.miss`, `planner.cache.hit`, `planner.cache.expired`, `planner.cache.store`.
- Structured logging events across planner lifecycle: `planner.initiated`, `planner.context_ready`, `planner.request.initiated`, `planner.parse.valid`, `planner.request.completed`, `planner.decision`, `planner.plan_built`, `planner.completed`, and cache events (`planner.cache.*`).
- Predicate gate logging events: `predicate_gate.initiated`, `predicate_gate.completed` with outcome metadata and failures list when applicable.
- Early cache write for planner outputs (both raw planner output and normalized Plan) so identical follow‑ups within TTL avoid a second LLM call even if later validation rejects.

### Changed
- Planner cache key refactored from scene-based to `(guild_id, channel_id, message)` to reduce coupling to scene lifecycle and enable reuse across scene context resets.
- `reset_counters()` now also clears the planner rate limiter internal state to prevent cross‑test interference causing false cache miss / hit metric assertions.
- Predicate gate now sets `Plan.feasible = False` and clears steps on failure while attaching structured failure metadata under `failed_predicates`.

### Fixed
- Intermittent missing `planner.cache.hit` metric under `features_action_validation=True` due to leftover rate limiting state between tests; resolved by clearing rate limiter in `reset_counters()`.
- Duplicate planner cache hit increments removed; single canonical increment now occurs exclusively inside `_cache_get`.

### Internal / Maintenance
- Introduced `action_validation.logging_utils.log_event` / `log_rejection` helpers to standardize structured logging payload shape.
- Added defensive normalization for legacy planner cache entries to migrate them in-place to the new `_CacheEntry` dataclass format on first access.
- Removed temporary planner debug counters (`planner.cache.debug.*`) and diagnostic `cache_keys` field from cache miss logs after stabilizing cache hit behavior.

### Notes
- Planner cache metrics are now stable; further instrumentation should be added only if new behaviors are introduced.

### Validation Matrix

| Capability | Plan Reference | Status | Evidence in Branch | Notes / Follow-ups |
| --- | --- | --- | --- | --- |
| Phase 0 — Contracts, shims, and feature flags | Implementation Phase 0 | ✅ Complete | `src/Adventorator/action_validation/schemas.py` defines the new models, `tests/test_action_validation_schemas.py` covers round-trip conversions, and `src/Adventorator/config.py` wires the feature flags. | Contracts mirror the design schemas and can be disabled via `features.action_validation` for rollback. |
| Phase 1 — Logging & metrics foundations | Implementation Phase 1 | ✅ Complete | `src/Adventorator/action_validation/logging_utils.py`, planner instrumentation in `src/Adventorator/commands/plan.py`, and helpers in `src/Adventorator/action_validation/metrics.py` provide the structured events and counters. | Structured logs now exist for initiated/completed/rejected flows, and counters expose acceptance, cache, and predicate metrics. |
| Phase 2 — Planner interop (`Plan` as internal representation) | Implementation Phase 2 | ✅ Complete | The `/plan` command converts planner output into `Plan` objects, registers them in `src/Adventorator/action_validation/registry.py`, and continues dispatch when the flag is enabled. | Planner cache still functions while emitting normalized plans for later stages. |
| Phase 3 — Orchestrator emits ExecutionRequest | Implementation Phase 3 | ✅ Complete | `src/Adventorator/orchestrator.py` builds `ExecutionRequest` payloads, logs plan metadata, and preserves defenses before handing off to the executor shim. | Mechanics previews reuse existing executor logic without changing user-visible output. |
| Phase 4 — Executor adapter for ExecutionRequest | Implementation Phase 4 | ✅ Complete | Adapter helpers in `src/Adventorator/action_validation/schemas.py` translate between `ExecutionRequest` and `ToolCallChain`, with parity tests in `tests/test_action_validation_schemas.py`. | Executor dry-run/apply flows continue unchanged behind the feature flag. |
| Phase 5 — Predicate gate v0 | Implementation Phase 5 | ✅ Complete | Deterministic checks in `src/Adventorator/action_validation/predicate_gate.py` drive the gate path in `src/Adventorator/commands/plan.py`, including per-failure counters. | Gate currently covers in-process lookups; future predicates can extend the helper without altering planner wiring. |
| Phase 6 — ActivityLog integration | Implementation Phase 6 | ✅ Complete | `src/Adventorator/orchestrator.py` persists ActivityLog rows via `src/Adventorator/repos.py` when mechanics are approved behind the feature flag. | Transcript linkage remains TODO, but mechanics payloads and failure handling exist for auditing. |
| Phase 7 — MCP scaffold | Implementation Phase 7 | ⏳ Not started | Only the `features.mcp` toggle is present in `src/Adventorator/config.py`; no MCP adapters or executor integrations exist yet. | Add in-process MCP servers and swap executor tool calls once adapters are ready. |
| Phase 8 — Tiered planning scaffold | Implementation Phase 8 | ⚠️ Partial | `PlanStep.guards` placeholders exist in `src/Adventorator/action_validation/schemas.py`, but plan generation still emits single-step Level 1 plans with no HTN scaffolding. | Introduce multi-step planners and guard population once higher-tier strategies are ready. |
| Phase 9 — Ops hardening & rollout | Implementation Phase 9 | ⚠️ Partial | Planner and orchestrator enforce soft timeouts and clamp mechanics inputs in `src/Adventorator/commands/plan.py` and `src/Adventorator/orchestrator.py`, yet payload size caps and canary automation remain. | Follow up with explicit payload bounding, latency histograms, and rollout playbooks. |
| Design alignment — ImprobabilityDrive & AskReport stage | Architecture §§3-5 | ⏳ Not started | `AskReport` is defined as a schema stub in `src/Adventorator/action_validation/schemas.py`, but no ImprobabilityDrive module or tagging/ontology integration feeds the planner per the roadmap. | Future work should introduce the `/ask` stage, semantic tagging, and ontology-backed affordances before multi-stage planning. |
