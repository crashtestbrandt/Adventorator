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

