# Validation Runbook — Tiered Planning (AVA-001I)
Status: Draft | Audience: Dev / Reviewer / QA
Scope: Validate tiered planning scaffolding (levels, expansion, guards) and ensure no regression in baseline planning behavior.

## 1. Preconditions
- Fresh clone of repository.
- Python 3.11+ available (see `pyproject.toml`).
- Docker + Docker Compose installed (for container path).
- (Optional) Discord application credentials if validating Discord pathway: `DISCORD_APP_ID`, `DISCORD_PRIVATE_KEY`, `DISCORD_PUBLIC_KEY` (or `DISCORD_DEV_PUBLIC_KEY`).
- Network access to pull base images (Docker) and any model/LLM endpoints (if enabling LLM features – not required for this story).

## 2. Environment Setup
### 2.1 Local
```bash
# Clone
git clone https://github.com/crashtestbrandt/Adventorator.git
cd Adventorator

# (Recommended) create virtualenv
python -m venv .venv
source .venv/bin/activate

# Install deps
pip install -U pip
pip install -r requirements.txt || pip install -e .

# Run formatting / lint / type to ensure clean baseline
make format lint type

# Run tests (optional upfront baseline)
make test

# Start database (if needed for other features; tiered planning itself can use sqlite)
make db-up || true

# Launch server with default config (tiers disabled by default)
make run
```
Server will bind to `APP_PORT` (default 18000). Logs at `logs/adventorator.jsonl`.

### 2.2 Docker
```bash
# Build and start (includes app + sidecars if defined)
docker compose up --build -d
# Tail logs
docker compose logs -f adventorator
```
To override feature flags in Docker, set environment variables in `docker-compose.yml` or via:
```bash
docker compose exec adventorator bash -lc 'export FEATURES_PLANNING_TIERS=true; kill -HUP 1'
```
(Prefer full container restart to guarantee reload.)

## 3. Feature Flags / Config Matrix
| Flag | Default | Purpose | Enabled Expectation | Disabled Expectation |
|------|---------|---------|---------------------|----------------------|
| `FEATURES_PLANNING_TIERS` | false | Activate tiered planning scaffold | Level resolution uses `PLANNER_MAX_LEVEL`; expansion + guards applied | Planner remains single-step baseline; no guards injected |
| `PLANNER_MAX_LEVEL` | 1 | Upper bound for planning tier | Level 2 triggers prepare step injection (if single base step) | Ignored (forced to 1) when tiers flag false |
| `FEATURES_ACTION_VALIDATION` | false | Enables validation pipeline producing plan snapshots & metrics | Plan snapshot log events, metrics counters increment | Snapshot may still appear but guards empty (baseline) |
| `FEATURES_PREDICATE_GATE` | false | Enables predicate gating (future use) | Guard list may include predicates if added later | No predicate guards |

Safe baseline for rollback parity: all four flags false.

## 4. Core Validation Scenarios
### 4.1 Baseline Single-Step Plan (Tiers Disabled)
- Purpose: Confirm disabling tiers yields original single-step plan with no guards.
- Inputs:
  - Environment: `FEATURES_PLANNING_TIERS=false` (default), `PLANNER_MAX_LEVEL=2` (optional), other flags off.
  - Command: `./scripts/web_cli.py plan "roll a d20"`
- Steps:
```bash
export FEATURES_PLANNING_TIERS=false
export PLANNER_MAX_LEVEL=2
python scripts/web_cli.py plan "roll a d20"
```
- Expected Result: Plan log snapshot has `step_count=1`, `guard_total=0`, no prepare.* step.
- Observability: `planner.tier.selected` log with `tiers_enabled=false`; absence of `planner.tier.expansion.level2_applied` event; `planner.plan_snapshot` has `tiers_enabled=false`.

### 4.2 Level Resolution With Tiers Enabled
- Purpose: Ensure enabling tiers + `PLANNER_MAX_LEVEL=2` selects level 2.
- Inputs: `FEATURES_PLANNING_TIERS=true`, `PLANNER_MAX_LEVEL=2`.
- Steps:
```bash
export FEATURES_PLANNING_TIERS=true
export PLANNER_MAX_LEVEL=2
python scripts/web_cli.py plan "roll a d20"
```
- Expected Result: `planner.tier.selected` log shows `level=2`.
- Observability: Log events `planner.tier.selected` and optionally `planner.tier.expansion.level2_applied` if expansion occurs.

### 4.3 Two-Step Expansion (Prepare Injection)
- Purpose: Validate level 2 expansion injects deterministic `prepare.<base>` step when starting from exactly one step.
- Inputs: Same as 4.2.
- Steps:
```bash
python scripts/web_cli.py --raw plan "roll a d20" | grep -A5 "planner.plan_snapshot" || true
```
- Expected Result: Snapshot plan `steps[0].op` starts with `prepare.`, `steps[1].op` is original operation.
- Observability: `planner.tier.expansion.level2_applied` log event with `new_steps=2`.

### 4.4 Guard Injection
- Purpose: Ensure capability guard attached when tiers enabled.
- Inputs: `FEATURES_PLANNING_TIERS=true`.
- Steps:
```bash
python scripts/web_cli.py --json-only plan "roll a d20" > /tmp/plan.json
jq '.steps[].guards' /tmp/plan.json
```
- Expected Result: Each step guard array contains `"capability:basic_action"` (baseline guard) when tiers enabled.
- Observability: `planner.tier.guards_applied` debug log; `planner.plan_snapshot.guard_total` > 0.

### 4.5 Environment Precedence (Server vs CLI)
- Purpose: Confirm server-start flags override per-invocation env attempts.
- Inputs: Start server with tiers disabled; invoke CLI with overrides.
- Steps:
```bash
# Terminal A
export FEATURES_PLANNING_TIERS=false
export PLANNER_MAX_LEVEL=2
make run
# Terminal B (attempt override)
FEATURES_PLANNING_TIERS=true python scripts/web_cli.py plan "roll a d20"
```
- Expected Result: Log file still shows `"features_planning_tiers": false` in startup configuration section; plan remains single-step.
- Observability: Absence of expansion / guards; test `tests/test_planner_env_precedence.py` passes.

### 4.6 Metrics Counters
- Purpose: Validate metrics increment patterns.
- Inputs: Tiers enabled; run plan command twice.
- Steps:
```bash
export FEATURES_PLANNING_TIERS=true PLANNER_MAX_LEVEL=2
python scripts/web_cli.py plan "roll a d20"
python scripts/web_cli.py plan "roll a d20"
grep 'planner.tier.selected' logs/adventorator.jsonl | wc -l
```
- Expected Result: Count equals number of invocations; if expansion occurred, `planner.tier.expansion.level2_applied` count matches or is at least 1.
- Observability: Structured log events + any metrics endpoint (if `METRICS_ENDPOINT_ENABLED=true`).

## 5. Negative / Edge Cases
- Missing Flags: Running without exporting flags should default to level 1 (no guards).
```bash
unset FEATURES_PLANNING_TIERS PLANNER_MAX_LEVEL
python scripts/web_cli.py plan "roll a d20"
```
Expected: Single step, no guards.
- Invalid Level (e.g., `PLANNER_MAX_LEVEL=0`): Clamped to 1.
- Multi-step Source Plan (future): Expansion no-op (log `planner.tier.expansion.noop`).

## 6. Observability (Logs & Metrics)
- Primary log file: `logs/adventorator.jsonl` (rotated, JSON lines).
- Key Events:
  - `planner.tier.selected` (level, tiers_enabled)
  - `planner.tier.expansion.level2_applied` (only when expansion performed)
  - `planner.tier.guards_applied` (guard counts per step)
  - `planner.plan_snapshot` (final plan, guard_total)
- Metrics (if enabled): `planner.tier.level.<n>`, `planner.plan.steps.count`, `planner.plan.guards.count` (names approximate; confirm actual metric IDs in code before release).

## 7. Rollback / Disable Procedure
- Immediate rollback: Set `FEATURES_PLANNING_TIERS=false` and restart server (or container) → reverts to single-step baseline with no guards.
- Hard disable: Remove `planner_tiers` references or set `PLANNER_MAX_LEVEL=1` across environments (infrastructure config) until feature iteration resumes.
- Validation of rollback: Repeat Scenario 4.1 and confirm parity with pre-feature snapshots (no prepare step, zero guards).

## 8. Golden / Snapshot Integrity
- Golden tests (`tests/test_encounter_events_golden.py`, related planner tests) must remain passing.
- Run selective planner tests:
```bash
pytest -q tests/test_planner_tier_metrics_and_guards.py tests/test_planner_env_precedence.py
```
- Compare a `planner.plan_snapshot` log line before/after enabling tiers (only differences: `tiers_enabled`, `step_count`, `guard_total`, added prepare step).

## 9. Failure Triage
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| No `planner.tier.selected` log | Feature flags not loaded or logging disabled | Verify env vars and `logging_enabled` setting |
| Expecting 2 steps but still 1 | Expansion conditions not met (multi-step baseline or tiers off) | Confirm `FEATURES_PLANNING_TIERS=true` and `PLANNER_MAX_LEVEL=2` |
| Guards absent when tiers enabled | Guard injection logic changed or flags not active | Check `planner.tier.guards_applied` log for guard_counts |
| CLI override changed behavior unexpectedly | Server restarted with new env, not pure override | Inspect startup log block for flag values |
| JSON-only output empty | No snapshot emitted (action_validation disabled) | Enable `FEATURES_ACTION_VALIDATION=true` |

## 10. Completion Checklist
- [ ] Baseline single-step scenario passes (4.1).
- [ ] Level selection logs show level=2 when enabled (4.2).
- [ ] Prepare step injection validated or explicitly absent with justification (4.3).
- [ ] Guard injection validated for tiers enabled (4.4).
- [ ] Environment precedence confirmed (4.5 / test passes).
- [ ] Metrics counters increment as expected (4.6).
- [ ] Negative cases behave as documented (Section 5).
- [ ] Rollback procedure executed (Section 7) and parity confirmed.
- [ ] Golden / snapshot tests green (Section 8).
- [ ] Failure triage table reviewed / updated if discrepancies.
- [ ] All feature flags documented with defaults (Section 3).

## 11. Future Hooks
- Level >2 decomposition (HTN/GOAP) to replace prep step stub.
- Rich predicate guards once predicate gate feature matures.
- Metrics cardinality review before scaling step counts.
- Discord pathway deep validation (currently optional for this story).

## 12. Appendices / References
- ADRs: See `docs/adr/` for decision records related to planning evolution.
- Epic / Implementation Plan: `docs/implementation/epics/` (tiered planning story reference AVA-001I).
- Scripts: `scripts/web_cli.py`, planner logic in `src/Adventorator/planner_tiers.py` and `planner.py`.

---
Meta Verification:
- All required sections present.
- Each scenario lists Purpose / Inputs / Expected / Observability.
- Rollback path documented (Section 7).
- Feature flags matrix included (Section 3).
- Failure triage table provided (Section 9).
- Completion checklist with `[ ]` boxes included (Section 10).

Known Watch Items / Non-blocking Deviations:
- Guard injection may be optional if upstream logic changes; runbook allows flexibility.
- Metrics naming may drift; validate actual counter names before release note.
