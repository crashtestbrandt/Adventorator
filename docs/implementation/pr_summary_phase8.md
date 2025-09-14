# PR: Phase 8 — Pending Actions and Confirmation Flow

Summary
- Add PendingAction confirmation loop with TTL and idempotency.
- Application- and DB-level idempotency via normalized `dedup_hash` and composite unique index `(scene_id, user_id, dedup_hash)` (partial for Postgres; compatible with SQLite).
- Feature flag `features.executor_confirm` to gate persistence and confirm/cancel commands; requires `features.executor`.
- Orchestrator integrates Executor preview; persists pending only if any step `requires_confirmation`.
- Commands: `/confirm`, `/cancel`, `/pending` (latest-only) wired.
- Metrics: `pending.created`, `pending.create.duplicate`, `pending.confirmed`, `pending.canceled`, `pending.expired`, plus existing executor/orchestrator timings.
- Repo handles IntegrityError on unique collisions by returning existing pending and incrementing duplicate counter.
- CLI: `scripts/expire_pending.py` for TTL expiry.

Migrations
- New Alembic migration: composite unique index `(scene_id, user_id, dedup_hash)` on `pending_actions`.
- Note: run Alembic after deploy.

Quality gates
- Tests: 72 passed locally; includes `test_pending_dedup_and_expiry.py` and confirm/cancel flows.
- Lint: ruff clean.
- Types: mypy clean.

Feature flags
- `features.executor` (must be true to exercise preview/confirm flows).
- `features.executor_confirm` (can be disabled for dev/testing; defaults true per config).

Notes
- Nice-to-have follow-ups: multi-item `/pending` list with pagination; concurrency stress tests around DB constraint.
