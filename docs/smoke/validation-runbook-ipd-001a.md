# Validation Runbook — STORY-IPD-001A (Contracts and feature flag scaffolding)
Status: Draft | Audience: Dev / Reviewer / QA
Scope: Validate Ask contracts placement, runtime schema alignment, feature flags, and non-regression.

> Docs-only branch note: On the `ADR-for-EPIC-IPD-001` branch, validate contracts and flags only. The `/ask` handler and NLU are delivered in Story B/C branches.

## 1. Preconditions
- Fresh clone or clean working tree on branch: `180-story-ipd-001a---contracts-and-feature-flag-scaffolding`.
- Python 3.12+ and Docker (Desktop) installed.
- Optional: Discord app credentials for integration path (can be skipped).
- Ports available: 18000 (app), 19000 (CLI webhook sink).

## 2. Environment Setup

### 2.1 Local
1) Create and activate a virtual environment.
```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
```
2) Install deps.
```powershell
pip install -r requirements.txt
```
3) Configure local env (.env.local recommended) with safe defaults.
```powershell
@"
DISCORD_APP_ID=dev-app-id
DISCORD_DEV_PUBLIC_KEY=0000000000000000000000000000000000000000000000000000000000000000
DISCORD_PRIVATE_KEY=0000000000000000000000000000000000000000000000000000000000000000
DISCORD_WEBHOOK_URL_OVERRIDE=http://127.0.0.1:18000/dev-webhook
APP_PORT=18000
"@ | Out-File -Encoding ascii .env.local
```
4) Run quality gates.
```powershell
ruff check src tests ; ruff format --check src tests ; pytest -q
```
5) Start the app.
```powershell
make run
```

### 2.2 Docker
1) Build and run via Docker Compose.
```powershell
docker compose up -d --build
```
2) Verify health.
```powershell
docker compose ps ; docker logs adventorator-app -n 50
```

## 3. Feature Flags / Config Matrix
Flags (defaults preserve current behavior):
- `features_improbability_drive` (bool; default=false)
- `features_ask` (bool or table.enabled; default=false)
- `features_ask_nlu_rule_based` (default=true)
- `features_ask_kb_lookup` (default=false)
- `features_ask_planner_handoff` (default=false)

Env precedence (highest → lowest): init > OS env > .env(.local) > TOML > file secrets.

Matrix (minimal for this story):
- Baseline: all flags off (no behavior change).
- Contracts-only validation: flags can remain off; schema round-trips still pass.

Set via env (example):
```powershell
$env:FEATURES_IMPROBABILITY_DRIVE=$false ; $env:FEATURES_ASK=$false
```

## 4. Core Validation Scenarios

### 4.1 Contract Registry Placement
- Purpose: Ensure canonical contract file exists and is versioned.
- Steps:
  ```powershell
  Test-Path contracts/ask/v1/ask-report.v1.json
  ```
- Expected: File exists; JSON contains `openapi`, `title`, and `required` keys.
- Observability: N/A (artifact check).

### 4.2 Runtime Schema Alignment
- Purpose: Runtime models match registry contract for v1.
- Steps:
  ```powershell
  pytest tests/ask/test_contracts_round_trip.py -q
  ```
- Expected: Tests pass; JSON round-trip equals input; nulls excluded from serialization.
- Observability: Test output PASS.

### 4.3 Flags Default Off (Config Defaults)
- Purpose: Confirm flags default to safe state.
- Steps:
  ```powershell
  pytest tests/ask/test_config_flags_defaults.py -q
  ```
- Expected: Flags default off; sub-flags as specified (rule-based true, others false).
- Observability: Test output PASS.

### 4.4 CLI Wire-Up Sanity (No /ask on this branch)
- Purpose: Ensure CLI tooling runs and application responds to interactions.
- Steps:
  1) With app running, list commands via web CLI (will discover existing slash commands):
     ```powershell
     python .\scripts\web_cli.py --help
     ```
   2) Optionally run an existing command (e.g., `help`):
     ```powershell
     python .\scripts\web_cli.py help
     ```
- Expected: HTTP 2xx; follow-up message printed by CLI sink.
- Observability: CLI prints request and follow-up; app logs a request.

### 4.5 Discord Integration (Optional)
- Purpose: Validate Discord path if creds configured.
- Steps:
  - Ensure `.env.local` has valid `DISCORD_APP_ID`, `DISCORD_DEV_PUBLIC_KEY`, and `DISCORD_PRIVATE_KEY` (dev-only).
  - Ensure `DISCORD_WEBHOOK_URL_OVERRIDE` points to `http://127.0.0.1:18000/dev-webhook` for local echo.
  - Trigger an existing command via web_cli (as above) — this signs like Discord and posts to the app.
- Expected: Similar to 4.4; if override not set, messages won’t echo (fake token); this is acceptable for this story.
- Observability: App logs show signature headers; sink or dev-webhook prints content.

## 5. Negative / Edge Cases

### 5.1 Env Precedence
- Purpose: Ensure OS env overrides `.env.local`.
- Steps:
  ```powershell
  $env:FEATURES_ASK=$true ; pytest tests/ask/test_config_flags_defaults.py -q
  ```
- Expected: Test that relies on defaults should adapt when env overrides; revert after.
- Observability: PASS with env influence; unset to restore defaults.

### 5.2 Missing Keys in .env
- Purpose: Validate CLI startup error messaging.
- Steps:
  - Temporarily move `.env.local` aside; run `python .\scripts\web_cli.py --help`.
- Expected: Friendly error about missing DISCORD_APP_ID or DISCORD_PRIVATE_KEY.
- Observability: CLI prints red error message and exits.

## 6. Observability (Logs & Metrics)
- Logs: `logs/adventorator.jsonl` (controlled via `logging_*` settings). Expect entries for HTTP interactions.
- Metrics: None newly added in this story. If `metrics_endpoint_enabled=true`, app exposes a metrics endpoint (implementation-dependent; not required here).

## 7. Rollback / Disable Procedure
- All changes are behind feature flags defaulted off. To force disable:
```powershell
$env:FEATURES_IMPROBABILITY_DRIVE=$false ; $env:FEATURES_ASK=$false
```
- No DB migrations introduced; revert by checking out previous commit if needed.

## 8. Golden / Snapshot Integrity
- Golden-style assertions live in round-trip tests under `tests/ask/`. Ensure they pass:
```powershell
pytest tests/ask/test_contracts_round_trip.py -q
```
- Contract artifact stability can be monitored via a parity test (to be added) comparing Pydantic `model_json_schema()` to `contracts/ask/v1/ask-report.v1.json`.

## 9. Failure Triage
| Symptom | Likely Cause | Action |
| --- | --- | --- |
| CLI shows connection error to /interactions | App not running or wrong APP_PORT | Start app; verify `APP_PORT` and `http://127.0.0.1:18000` reachable |
| No follow-up printed by CLI | Missing `DISCORD_WEBHOOK_URL_OVERRIDE` or sink port collision | Set override to `/dev-webhook`; check 19000 port or use `--sink-port` |
| Tests fail on flags default | Local env overriding defaults | Clear conflicting env vars; re-run tests |
| Schema round-trip test fails | Manual edits broke model fields | Reconcile `src/Adventorator/schemas.py` with `contracts/ask/v1/ask-report.v1.json` |

## 10. Completion Checklist
- [ ] Contract file present at `contracts/ask/v1/ask-report.v1.json`.
- [ ] Runtime models exist in `src/Adventorator/schemas.py` (AskReport, IntentFrame, AffordanceTag).
- [ ] Round-trip tests PASS.
- [ ] Flag defaults verified (off; sub-flags per spec).
- [ ] CLI interaction sanity PASS.
- [ ] (Optional) Discord echo verified or explicitly skipped.
- [ ] Logs captured for at least one interaction.
- [ ] No new dependencies added; no DB changes.

## 11. Future Hooks
- Add parity test to ensure Pydantic schema remains in lockstep with JSON artifact.
- Implement `/ask` handler under `src/Adventorator/commands/` behind flags; add observability counters (`ask.received`, `ask.emitted`, `ask.failed`).

## 12. Appendices / References
- Epic: `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md`
- Story: `docs/implementation/stories/STORY-IPD-001A-contracts-and-flags.md`
- Contracts registry: `contracts/ask/v1/ask-report.v1.json`
- Runtime models: `src/Adventorator/schemas.py`
- CLI tool: `scripts/web_cli.py`

---

Meta-checklist for this runbook:
- [x] All required sections present in final doc.
- [x] Each scenario lists Purpose / Steps / Expected / Observability.
- [x] At least one rollback path documented.
- [x] Feature flags explicitly addressed.
- [x] Failure triage table includes symptom, likely cause, action.
- [x] Completion checklist uses `[ ]` boxes and is exhaustive.

Summary: No known blocking issues. Watch items: add contract-parity test in follow-up; metrics for `/ask` will arrive with Story B. Current changes are fully gated by flags defaulted to off, minimizing regression risk.
