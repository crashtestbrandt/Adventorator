# STORY-IPD-001D — World Knowledge Base (KB) integration (read-only)

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Implemented
Owner: Data/Repos WG

## Summary
Add a read-only KB adapter leveraging existing repos to resolve entity references and suggest alternatives; cache common lookups.
- Read-only, deterministic, offline relative to external services (repo-backed only).
- Async, no inline SQL; follow existing repo patterns and feature-flag gating.

## Interfaces & Placement
- Module placement:
  - `src/Adventorator/kb/adapter.py` (adapter + interface types)
  - Uses existing repo access patterns in `src/Adventorator/repos.py` (async context managers).
- Interface (finalized for this story):
  - Signature contracts
    - `async def resolve_entity(term: str, *, limit: int = 5, timeout_s: float | None = None) -> KBResolution`
    - `async def bulk_resolve(terms: list[str], *, limit: int = 5, timeout_s: float | None = None, max_terms: int | None = None) -> list[KBResolution]`
  - Types (Python typing)
    - `KBResolution`: mapping with fields
      - `canonical_id: str | None`
      - `candidates: list[Candidate]`
      - `reason: str | None`
      - `source: str` (constant e.g., "repo")
    - `Candidate`: mapping with fields
      - `id: str`
      - `label: str`
  - Determinism requirement: given seeded repo data, results must be stable and ordered.
  - Candidate ordering: stable order by `(label ASC, id ASC)` unless an existing repo method guarantees a canonical deterministic sort; no randomized ordering.
  - bulk_resolve contract:
    - Returns a list aligned 1:1 with the input `terms` order.
    - Empty/whitespace-only terms yield `KBResolution(canonical_id=None, candidates=[], reason="empty-term", source="repo")`.
    - If number of `terms` exceeds `max_terms_per_call`, process only the first `max_terms_per_call` terms; emit a debug log describing truncation. Excess terms are ignored in this call.
- Integration slice (behind flags):
  - If `[features.ask].kb_lookup` is true and `features.improbability_drive` is true, the `/ask` flow may invoke KB resolution for tokens/tags produced by the rule-based NLU (Story C). When disabled, there is no behavior change.

## Configuration
- Feature flags (defaults preserve current behavior):
  - `features.improbability_drive = false`
  - `features.ask = false`
  - `features.ask_kb_lookup = false` (via `[features.ask].kb_lookup`)
- Adapter knobs (safe defaults; bounded):
  - `ask.kb.timeout_s` (default: 0.05)
  - `ask.kb.max_candidates` (default: 5)
  - `ask.kb.cache_ttl_s` (default: 60)
  - `ask.kb.cache_max_size` (default: 1024)
  - `ask.kb.max_terms_per_call` (default: 20)
- Example TOML:
```toml
[features]
improbability_drive = false
ask = false

[features.ask]
kb_lookup = false

[ask.kb]
timeout_s = 0.05
max_candidates = 5
cache_ttl_s = 60
cache_max_size = 1024
max_terms_per_call = 20
```
- Settings precedence follows ADR-0005: init > OS env > .env(.local) > TOML > file secrets.

Implementation notes:
- Map `[ask.kb]` into `Settings` in `src/Adventorator/config.py` with safe defaults above.
- Gate the `/ask` integration under both `features.improbability_drive` and `[features.ask].kb_lookup`.
- Ensure defaults in `config.toml` reflect disabled flags and the adapter knobs above.

## Developer Workflow & Quality Gates
- Prefer Makefile targets:
  - `make format`, `make lint`, `make type`, `make test` (required for code changes)
  - If prompts/contracts are changed: `make quality-gates` and `PYTHONPATH=./src scripts/validate_prompts_and_contracts.py`
  - Database tasks only if needed (not expected here): `make db-up`, `make alembic-up`
- PRs must summarize quality-gate outcomes and map evidence to acceptance criteria (see Issue & Branch Metadata).

## Acceptance Criteria
- KB adapter functions return normalized IDs and candidate alternatives with deterministic results for seeded data.
- Gated by `features.improbability_drive` and `features.ask_kb_lookup`; disabling flags bypasses KB without side effects.
- Uses async repos (no inline SQL in handlers); respects `timeout_s`, `max_candidates`, and `max_terms_per_call`.
- Cache behavior is bounded by TTL and size; hit/miss metrics recorded.
- Timeouts and payload bounds are enforced with safe defaults; timeouts recorded without raising unhandled exceptions.
- Logs use repo helpers (`log_event`/`log_rejection`); metrics via `Adventorator.metrics.inc_counter`.

Acceptance tests mapping (indicative):
- Determinism: `tests/kb/test_kb_resolution.py::test_deterministic_resolution`
- Ambiguity ordering: `tests/kb/test_kb_resolution.py::test_candidates_stable_order`
- Cache metrics: `tests/kb/test_kb_cache.py::test_hit_miss_counters`
- Timeout/bounds: `tests/kb/test_kb_limits.py::test_timeout_and_bounds`

## Tasks
- [x] TASK-IPD-KB-10 — Implement KB adapter with repo-backed lookups (async; no inline SQL).
- [x] TASK-IPD-CACHE-11 — Add bounded caching (TTL/size) with `kb.lookup.hit/miss` counters.
- [x] TASK-IPD-TEST-12 — Unit tests for canonical entities, ambiguous cases, cache hit/miss, and timeout/bounds.
- [x] TASK-IPD-CONFIG-13 — Add config knobs under `[ask.kb]` and map into `Settings` (`src/Adventorator/config.py`).
- [x] TASK-IPD-INTEG-14 — Wire optional KB step into `/ask` flow behind `features.ask_kb_lookup`.
- [x] TASK-IPD-DOCS-15 — Update docs/runbook and link in EPIC; note defaults and rollback.

Out of scope (for this story):
- Write operations or KB mutation.
- External service calls; only repo-backed data sources permitted.
- New DB migrations (should not be required for this slice).

## Definition of Ready
- Data fixtures prepared for canonical/ambiguous entities and seeded repo data.
- Config knobs defined and reviewed (timeouts, bounds, cache size/TTL).
- Repo methods identified for lookups; no new migrations required.
- Test plan approved with fixture locations and performance sanity.

Implementation-ready checklist (to complete before starting):
- [ ] Confirm `config.toml` contains default-disabled flags and `[ask.kb]` knobs as specified.
- [ ] Confirm `src/Adventorator/config.py` has dataclass fields for `[ask.kb]` with defaults and validation.
- [ ] Confirm repository access points in `src/Adventorator/repos.py` suitable for lookups (no inline SQL in handlers).
- [ ] Create test fixture directory `tests/kb/fixtures/` with canonical/ambiguous samples and golden outputs.
- [ ] Add placeholder tests named in Acceptance tests mapping to drive TDD.

## Definition of Done
- Quality gates pass (`make format`, `make lint`, `make type`, `make test`); docs-only edits may skip code gates per AGENTS.md.
- Acceptance criteria validated by automated tests, including determinism and cache metrics.
- Feature flags wired with defaults; disabling flags yields no behavior change.
- Docs updated (KB data sources, cache behavior, configuration, and rollback).

## Test Plan
- Unit tests using fixtures and mocked repos; assert:
  - Deterministic resolution for seeded inputs.
  - Ambiguous results return candidates in stable order.
  - Cache hit/miss counters increment as expected; TTL expiry evicts entries.
  - Respect for `timeout_s`, `max_candidates`, and `max_terms_per_call`.
- Performance sanity: typical lookup in tens of milliseconds on dev hardware.
- Fixture locations: `tests/kb/fixtures/` (new), with golden outputs similar to `tests/ask/` style.

Manual smoke (flag OFF → ON):
1) OFF: Run `make run` and exercise `/ask` flow; verify no KB calls or metrics related to `kb.lookup.*`.
2) ON: Enable `features.improbability_drive=true` and `[features.ask].kb_lookup=true`; restart and exercise `/ask` with terms present in fixtures; verify `KBResolution` outputs, stable candidate order, metrics `kb.lookup.hit/miss`, and timeout behavior under constrained `timeout_s`.

## Edge Cases & Constraints
- Empty/whitespace term: produce `KBResolution` with `canonical_id=None`, no candidates, `reason="empty-term"`.
- Duplicate terms in `bulk_resolve`: allowed; cache should yield hits; output preserves input order.
- Non-ASCII/unicode terms: supported; normalization should not crash; if not found, return empty candidates deterministically.
- Oversized `terms` payload: enforce `ask.kb.max_terms_per_call` by truncation with a debug log (no exception).
- Timeouts: enforce `ask.kb.timeout_s` using async timeout; record `kb.lookup.timeout`; return best-effort results without raising unhandled exceptions.
- Cache: TTL + max size (LRU or equivalent); evictions may increment `kb.cache.evicted` (optional); ensure bounded memory.
- Source field: always `"repo"` for this story (no external services).

## Observability
- Metrics:
  - `kb.lookup.hit`, `kb.lookup.miss`
  - `kb.lookup.timeout`, `kb.cache.evicted` (optional)
- Logs:
  - Structured debug/info logs for resolution decisions and cache outcomes via repo helpers.
- Tracing: not introduced in this story.

## Risks & Mitigations
- Stale cache: bounded TTL/size; counters to monitor; optional manual flush in tests.
- Repo latency/downtime: short timeouts and safe fallbacks (no hard failures); feature flag to disable.
- Nondeterminism: seeded data with stable ordering; tests assert determinism.

## Dependencies
- Story C (tagging) for normalized tag targets and inputs to KB.
- Postgres via `make db-up` and existing repos; no external services.
- Alembic state current; no new migrations in this story.

## Feature Flags
- features.improbability_drive
- features.ask_kb_lookup (default=false; `[features.ask].kb_lookup`)

## Issue & Branch Metadata
- Proposed GitHub Issue title: "STORY-IPD-001D: Read-only KB integration (adapter, cache, flag-gated)"
- Labels: `story`, `improbability-drive`, `backend`, `kb`, `good-first-slice`
- Suggested branch name: `feature/ipd-001d-kb-adapter`
- PR checklist: follow `.github/pull_request_template.md` and include quality gate summaries; map evidence to acceptance criteria.

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 3 — KB Adapter (Read-only) & Caching
