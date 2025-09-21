# Validation Runbook — STORY-AVA-001I Tiered Planning Scaffolding

Status: Draft (manual validation)
Scope: Ensures Tiered Planning scaffolding (Level 1 baseline, Level 2 prepare-step expansion, guards field + metrics + logs) is functioning and regressions are not introduced.
Audience: Developers and reviewers performing pre-merge or pre-release checks.

---
## 1. Preconditions
- Fresh clone OR clean working tree; no uncommitted changes.
- Python 3.11+ available locally (project uses a virtualenv via `make` targets).
- Docker (optional path) installed and running.
- (Optional) Discord bot credentials if validating via Discord (token, guild/server, channel).
- Feature flags controlled via environment variables or `.env` / shell export.

Environment Variables Used:
- `FEATURES_PLANNING_TIERS` ("true" / "false")
- `PLANNER_MAX_LEVEL` (integer >=1)

---
## 2. Fresh Clone & Local Setup
```bash
# Clone
git clone https://github.com/crashtestbrandt/Adventorator.git
cd Adventorator
# (Optionally checkout branch under review)
# git checkout <branch>

# Create & activate virtualenv via make
make venv  # if provided; else rely on implicit in other targets
make install  # or: pip install -e .

# Sanity: lint, type, tests
make lint
make type
make test
```
Acceptance gate: Test suite green (Tier tests included): look for passing tests `test_planner_tiers`, `test_planner_tier_metrics_and_guards`, `test_planner_tier_expansion_logging`, `test_planner_tier_expand_noop`.

---
## 3. Running Locally (Non-Docker)
```bash
# Start local dev server (if used for interactive endpoints)
make run  # or: make dev (depending on Makefile aliases)
```
Verify server starts without stack traces. Capture logs in a second terminal if desired:
```bash
tail -f logs/adventorator.jsonl
```

---
## 4. Running with Docker
```bash
# Build image
docker build -t adventorator:local .
# Run (example exposing expected port 8000)
docker run --rm -it -p 8000:8000 \
  -e FEATURES_PLANNING_TIERS=false \
  adventorator:local
```
Optional: override level 2 test mode
```bash
docker run --rm -it -p 8000:8000 \
  -e FEATURES_PLANNING_TIERS=true -e PLANNER_MAX_LEVEL=2 \
  adventorator:local
```

---
## 5. Web CLI Manual Validation (`scripts/web_cli.py`)
The web CLI provides an internal interaction path without Discord.

### 5.1 Baseline Level 1 (Flag Off)
```bash
export FEATURES_PLANNING_TIERS=false
python scripts/web_cli.py plan "roll a d20"
```
Expected:
- Plan JSON shows exactly one step: `roll.d20`.
- `guards` list is present and empty: `"guards": []`.
- Logs contain `planner.tier.selected` with `tiers_enabled=false`.
- No `planner.tier.expansion.level2_applied` event.

### 5.2 Deterministic Guard Injection (Flag On, Level 1)
```bash
export FEATURES_PLANNING_TIERS=true
export PLANNER_MAX_LEVEL=1
python scripts/web_cli.py plan "roll a d20"
```
Expected:
- Still one step.
- Guards contains `capability:basic_action`.
- Counter behavior if metrics endpoint/print inspected (optional): `plan.guards.count == 1`.

### 5.3 Level 2 Expansion (Prepare Step)
```bash
export FEATURES_PLANNING_TIERS=true
export PLANNER_MAX_LEVEL=2
python scripts/web_cli.py plan "roll a d20"
```
Expected:
- Two steps: first `prepare.roll`, second `roll.d20`.
- Each step has `"guards": ["capability:basic_action"]`.
- Structured log includes `planner.tier.expansion.level2_applied` with `requested_level=2` and `new_steps=2`.

### 5.4 Rollback Behavior
```bash
export FEATURES_PLANNING_TIERS=true
export PLANNER_MAX_LEVEL=2
python scripts/web_cli.py plan "roll a d20" > /tmp/plan_enabled.json
export FEATURES_PLANNING_TIERS=false
unset PLANNER_MAX_LEVEL
python scripts/web_cli.py plan "roll a d20" > /tmp/plan_disabled.json
```
Diff expectations:
- `/tmp/plan_enabled.json` has 2 steps & guards populated.
- `/tmp/plan_disabled.json` has 1 step & empty guards.
- No residual prepare step or guards after disable.

### 5.5 Monkeypatched Guard Enrichment (Optional Dev Check)
Run the existing test directly for demonstration:
```bash
pytest -k monkeypatched_guards_population -q
```
Shows second guard (`predicate:exists:actor`) via monkeypatch simulating future enrichment.

---
## 6. Discord Bot Validation (Optional)
Prerequisites:
- Discord bot token and necessary intents configured.
- Bot invited to test server with message content intent.

Environment setup example:
```bash
export DISCORD_BOT_TOKEN=XXXXXXXX
export FEATURES_PLANNING_TIERS=true
export PLANNER_MAX_LEVEL=2
make run  # assuming Discord integration auto-starts or separate task
```
In a test channel send: `!plan roll a d20` (replace prefix if different).
Expected Bot Reply (conceptual):
- Shows planned action or preview referencing two steps (current user-facing copy may only show final action; verify logs for expansion event).
Log inspection (separate terminal):
```bash
grep -i "planner.tier" logs/adventorator.jsonl | tail -n 5
```
Should include:
- `planner.tier.selected` (tiers_enabled true, level>=2)
- `planner.tier.expansion.level2_applied`
Toggle flag off and repeat; confirm single-step plan and absence of expansion log.

---
## 7. Metrics & Observability Spot Checks
If metrics are exported in-process (e.g., via internal registry or endpoint):
- Trigger successive plans at different levels.
- Confirm counters increment:
  - `planner.tier.level.1` increments when level resolves to 1.
  - `planner.tier.level.2` increments when expansion occurs.
  - `plan.steps.count` equals number of steps emitted.
  - `plan.guards.count` equals total guards across steps.
Dev helper (Python REPL snippet):
```python
from Adventorator.metrics import get_counter
print(get_counter("planner.tier.level.1"))
print(get_counter("planner.tier.level.2"))
print(get_counter("plan.steps.count"))
print(get_counter("plan.guards.count"))
```

---
## 8. Golden Fixture Integrity
Validate golden fixtures still match code output:
```bash
pytest tests/test_planner_tiers.py::test_plan_serialization_level1_stable -q
pytest tests/test_planner_tiers.py::test_level2_expansion_inserts_prepare_step -q
```
If a deliberate change occurs in Plan structure, update fixture(s):
- `tests/golden/plan_single_step_level1.json`
- `tests/golden/plan_level2_two_steps.json`
- `tests/golden/plan_single_step_with_guards.json`
Run full suite again before committing.

---
## 9. Failure Triage Guidelines
| Symptom | Likely Cause | Action |
| ------- | ------------ | ------ |
| Missing `prepare.roll` step at level 2 | Flag not set or `PLANNER_MAX_LEVEL` misconfigured | Re-export env vars; inspect `planner.tier.selected` log |
| Guards absent when tiers enabled | Regression in `guards_for_steps` or env var not exported | Print `FEATURES_PLANNING_TIERS`; rerun plan; run targeted test |
| Expansion log missing | Level resolved to 1 or logging suppressed | Verify `PLANNER_MAX_LEVEL` and logs directory/level |
| Rollback retains 2 steps | Stale process reusing cached plan | Restart server / CLI; ensure new request id |
| Golden test failure | Fixture drift or unintended change | Inspect diff, decide fixture update vs. revert |

---
## 10. Completion Checklist
- [ ] Level 1 single-step validated (flag off) — empty guards.
- [ ] Deterministic guard present (flag on, level 1).
- [ ] Level 2 expansion inserts prepare step + log event.
- [ ] Rollback (disable flag) returns to single-step & empty guards.
- [ ] Metrics counters increment as expected.
- [ ] Golden fixtures pass unchanged.
- [ ] Optional Discord validation (if applicable) completed.

If all boxes checked, manual validation for STORY-AVA-001I passes.

---
## 11. Updating Epic Task Status
After validation, update `STORY-AVA-001I` tasks in `docs/implementation/epics/action-validation-architecture.md` from `[ ]` to `[x]` for:
- `TASK-AVA-TIER-26`
- `TASK-AVA-GUARD-27`
- `TASK-AVA-TEST-28`
- `TASK-AVA-METRIC-33`
- `TASK-AVA-DOC-32`

Provide a short commit message, e.g.:
```
chore(ava-001i): complete manual validation runbook and mark tasks done
```

---
## 12. Future Story Hooks
Prepared surfaces for next iterations:
- Replace deterministic guard with real predicate-derived guards.
- Extend multi-step decomposition logic (HTN/GOAP) beyond single prepare step.
- Add log assertions for future Level 3+ expansions.

End of runbook.
