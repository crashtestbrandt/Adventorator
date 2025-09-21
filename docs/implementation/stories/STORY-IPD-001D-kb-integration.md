# STORY-IPD-001D — World Knowledge Base (KB) integration (read-only)

Epic: [EPIC-IPD-001 — ImprobabilityDrive Enablement](/docs/implementation/epics/EPIC-IPD-001-improbability-drive.md)
Status: Planned
Owner: Data/Repos WG

## Summary
Add a read-only KB adapter leveraging existing repos to resolve entity references and suggest alternatives; cache common lookups.

## Acceptance Criteria
- KB adapter functions return normalized IDs and candidate alternatives.
- Deterministic resolution for seeded data; caches bounded and instrumentation added.
- Timeouts and payload bounds are configurable with safe defaults.

## Tasks
- [ ] TASK-IPD-KB-10 — Implement KB adapter with repo-backed lookups.
- [ ] TASK-IPD-CACHE-11 — Add caching with metrics for hit/miss.
- [ ] TASK-IPD-TEST-12 — Unit tests for canonical entities and ambiguous cases.

## Definition of Ready
- Data fixtures prepared; timeout/bounds knobs defined.

## Definition of Done
- Docs describe KB data sources and cache behavior.

## Test Plan
- Unit tests using fixtures and mocked repos; timeout/limit tests.

## Observability
- Metrics: kb.lookup.hit, kb.lookup.miss; logs for resolution decisions.

## Risks & Mitigations
- Stale cache: bounded TTL and size; counters for hit/miss to monitor.

## Dependencies
- Story C (tagging) for normalized tag targets.

## Feature Flags
- features.improbability_drive
- features.ask_kb_lookup (default=false)

## Traceability
- Epic: EPIC-IPD-001
- Implementation Plan: Phase 3 — KB Adapter (Read-only) & Caching
