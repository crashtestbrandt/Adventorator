# ADR-0012 Event Versioning & Migration Protocol

Status: Proposed  
Date: 2025-09-21  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Event schemas will evolve; must preserve replay capability without mutating stored historical payloads.

## Decision
- Registry: event_type → { latest_version, write_enabled, migrator_chain }.
- Each event stores event_schema_version + migrator_applied_from (if upgraded during replay).
- Migrations: pure, deterministic, no I/O, no clocks.
- Write blocked if event_type write_enabled=false.
- Golden corpus fixtures validated in CI after migrations.

## Consequences
Pros:
- Non-destructive evolution.
- Explicit deprecation path.

Cons:
- Additional maintenance overhead for migrators.

## Follow-Up
- Introduce tooling to auto-generate baseline migrator when bumping schema.