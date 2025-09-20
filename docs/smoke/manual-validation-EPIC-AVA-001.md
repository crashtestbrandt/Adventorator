# Manual Validation Runbook for [EPIC-AVA-001 (Action Validation Architecture)](../implementation/action-validation-implementation.md)

**Overview**

Below is (1) a code-level progress review against ARCH-AVA-001 and Epic stories, then (2) a detailed from-scratch validation guide (fresh clone → configure → run → smoke tests via web CLI and Discord). Gaps and next actions are clearly flagged.

**Progress Review (Architecture → Implementation)**
- Contracts: AskReport / IntentFrame / Plan / PlanStep / ExecutionRequest / ExecutionResult all implemented in schemas.py with deterministic `plan_id` hashing. Guards field present but unused (empty) → STORY-AVA-001I tasks `GUARD-27`/`TEST-28` still pending (no population or serialization test).
- Planner Integration (Phase 3): `/plan` command wraps legacy planner output into `Plan` when `features_action_validation` enabled (see plan.py: usage of `plan_from_planner_output`, registry, metrics). Deterministic cache path supports both legacy and plan schemas.
- Predicate Gate (Phase 5): Implemented in predicate_gate.py with predicates `known_ability`, `dc_in_bounds`, `actor_in_allowed_actors`, `exists(actor|target)`; metrics counters emitted (`predicate.gate.ok/error` and per-failure `predicate.gate.fail_reason.<code>`). Tests confirm acceptance and failure paths (test_predicate_gate_metrics.py, test_action_validation_predicate_gate_phase5.py).
- Metrics & Logging: Helper functions `record_plan_steps`, `record_predicate_gate_outcome` implemented; logs via `log_event`/`log_rejection` in planner. Orchestrator logs structured info for run lifecycle and ExecutionRequest creation. Some planned metrics not yet present (e.g., explicit `planner.feasible`, `executor.preview/apply` counters referenced in architecture doc are partially indirect or missing; executor preview metric recorded as `orchestrator.executor.preview_ms` but no success/failure counts).
- Orchestrator ExecutionRequest Shim (Phase 4): ExecutionRequest built conditionally (`feature_action_validation`) with PlanStep derivation for check/attack/condition actions. Tests: test_orchestrator_phase3.py, test_orchestrator_attack.py, test_action_validation_executor_phase4.py validate presence and tool chain round trip.
- Executor Interop Adapter: Conversion helpers `execution_request_from_tool_chain` and `tool_chain_from_execution_request` implemented and tested (test_action_validation_schemas.py, test_action_validation_executor_phase4.py). Adapter used in orchestrator when previewing with executor flag.
- ActivityLog (Phase 6 dependency): Orchestrator writes ActivityLog entries when `features_activity_log` and `features_action_validation` enabled (see lines ~664–713 in orchestrator.py). Counters for failures exist. Full ActivityLog epic cross-links not reviewed here but integration hook is present.
- MCP Adapters (Phase 7 future): No MCP modules yet. Only flag `features_mcp` exists; search shows no adapter scaffolding → STORY-AVA-001H tasks outstanding.
- Tiered Planning (Phase 8/9 future): Only single-step logic; no tier selection scaffolding or guards population logic yet → STORY-AVA-001I tasks outstanding.
- Operational Hardening: Planner timeout (`planner_timeout_seconds`) present. No explicit payload size bounding or executor-specific timeout/payload controls yet → parts of `TASK-AVA-TIMEOUT-29` pending. Rollout runbook & extended metrics not visible in repo → `TASK-AVA-RUNBOOK-31` pending; expanded metrics taxonomy (`TASK-AVA-METRIC-30`) partially incomplete (missing feasibility & executor apply counters).
- Observability Gaps: 
  - Missing dedicated counter names promised in architecture: `planner.feasible`, `executor.preview` (exists as timing metric), `executor.apply` (not present), predicate failure reasons covered, activity log success metric missing.
  - Plan feasibility currently inferred indirectly; consider increment `planner.feasible` vs `planner.infeasible`.
- Guards & Repairs: Plan model includes `repairs`, `guards`, `alternatives`, but planner integration does not populate them (repairs/alternatives come only via transformation if future path). Tests for serialization stability absent.
- AskReport / IntentFrame: Present but not yet produced by an ImprobabilityDrive stage (no `/ask` command producing AskReport). So Phase 1 (Intent framing) partially scaffolded only at data model level.

**Summary of Implemented vs Pending**
- Implemented: Core schemas, planner Plan integration, predicate gate, execution request adapter, orchestration shim, metrics basics, ActivityLog hook.
- Pending: MCP adapter scaffold, tiered planning scaffolding & guards, richer metrics (feasible/preview/apply), AskReport production logic, runbook & ops metrics expansion, repairs/alternatives population, payload bounds & per-phase timeouts, guards population tests, MCP parity tests.

**Fresh Clone Validation Guide**

1. Prerequisites
- OS: macOS (per environment)
- Dependencies: Docker (for Postgres if needed), Python 3.10+, Make, optionally Ollama or OpenAI key (LLM features can stay disabled for non-LLM smoke).
- Environment variables if enabling LLM or Discord:
  - `DISCORD_APP_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_BOT_TOKEN` (for real Discord)
  - `LLM_API_PROVIDER` (`ollama` or `openai`), `LLM_API_URL` (if ollama), `LLM_API_KEY` (if openai)
- Recommended: Create a Python virtual environment (Makefile handles .venv).

2. Clone & Bootstrap
```
git clone https://github.com/crashtestbrandt/Adventorator.git
cd Adventororator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
(Or rely on Make targets which will also install dev deps if specified; minimal dependencies currently empty but tests may pull extras—if missing, install via `pip install -r requirements.txt`.)

3. Configuration (config.toml)
Adjust feature flags for progressive validation. Minimal safe baseline (all AVA off):
```
[features]
llm = false
action_validation = false
predicate_gate = false
executor = false
activity_log = false
```
Full AVA phase-6 style smoke (no MCP yet):
```
[features]
llm = true
action_validation = true
predicate_gate = true
executor = true         # if you want executor preview paths
activity_log = true     # requires DB
combat = true           # to allow attack steps
rules = true            # if rules-based previews needed
```
Optional retrieval (Phase 6):
```
[features.retrieval]
enabled = false
provider = "none"
top_k = 4
```
Planner timeout override:
```
[planner]
timeout_seconds = 12
```
Logging (JSON lines):
```
[logging]
enabled = true
level = "INFO"
console = true
to_file = true
file_path = "logs/adventorator.jsonl"
```

4. Database Setup (if using ActivityLog or character predicates)
```
make db-up          # Starts Postgres (docker-compose)
make alembic-up     # Applies migrations
```
If you skip Postgres, SQLite fallback is used; some character existence predicates still function if using sqlite file (default connection string).

5. Quality Gates (baseline)
```
make format
make lint
make type
make test
```
Expect green tests; key AVA tests:
- test_action_validation_schemas.py
- test_orchestrator_phase3.py
- test_action_validation_executor_phase4.py
- test_action_validation_predicate_gate_phase5.py
- test_predicate_gate_metrics.py

6. Run the Service (Web application + interaction endpoint)
```
make run
```
This starts FastAPI/uvicorn (port default 18000). Metrics endpoint may be disabled unless you set `[ops] metrics_endpoint_enabled = true`.

7. Web CLI Smoke Tests (web_cli.py)
Purpose: Emulate Discord interactions locally (signed requests).

a. Enable LLM & planner (if you want actual plan decisions):
Set in config.toml: `llm = true`, provide LLM settings (for `ollama`, ensure `ollama serve` is running and `llm_api_url` points to it; for openai supply key).

b. Start server (if not already):
```
make run
```

c. In a second shell (virtualenv activated):
Basic help (ensures command registry loads):
```
PYTHONPATH=./src python scripts/web_cli.py help
```
Plan command without AVA (flag off):
```
# Ensure action_validation=false
PYTHONPATH=./src python scripts/web_cli.py plan "roll a d20"
```
Observe plaintext response mapping to /roll or planned command execution.

Enable AVA + Predicate Gate:
- Set `action_validation=true`, `predicate_gate=true` in config.toml.
- Restart server if config changed.
Then:
```
PYTHONPATH=./src python scripts/web_cli.py plan "roll a d20"
```
Validate:
- Logs show `planner.initiated`, `predicate_gate.initiated/completed`.
- Metrics counters (if you instrument a quick inspection; otherwise verify log lines).
Predicate failure path:
```
PYTHONPATH=./src python scripts/web_cli.py plan "check XYZ with dc 900"
```
Expect ephemeral failure message citing ability/DC issues; verify `predicate.gate.error` counters (can inspect by temporarily adding a debug endpoint or reading in-memory metrics if exposed—currently internal).

Orchestrator `/do` path producing ExecutionRequest (ensure `features_action_validation=true`):
```
PYTHONPATH=./src python scripts/web_cli.py do "Make a DEX check with dc 12"
```
Expect:
- Response includes mechanics preview.
- When `features_executor=true`, preview uses executor pipeline; otherwise fallback text.
Attack example (if combat enabled):
```
PYTHONPATH=./src python scripts/web_cli.py do "Attack the goblin with a dagger"
```
Check logs for `orchestrator.execution_request.built` and steps with op `attack`.

ActivityLog Integration:
Ensure `activity_log=true` & DB migrations applied:
```
PYTHONPATH=./src python scripts/web_cli.py do "Make a DEX check with dc 10"
```
Then query DB (psql or sqlite) to confirm an `activity_log` entry referencing `plan_id` (table name assumed per repo—verify actual model/table if needed).

8. Discord Smoke Tests
(Only if you have real credentials; otherwise skip.)

a. Create/Configure Discord Application:
- Obtain `DISCORD_APP_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_BOT_TOKEN`.
- In .env (or environment):
```
DISCORD_APP_ID=...
DISCORD_PUBLIC_KEY=...
DISCORD_BOT_TOKEN=...
```

b. Register Slash Commands:
With server stopped or running (does an HTTP call):
```
PYTHONPATH=./src python scripts/register_commands.py
```
This should upsert slash commands (plan, do, roll, check, etc.).

c. Run Server With Tunnel (optional for Discord to reach local):
```
make tunnel   # cloudflared; exposes local 18000
make run
```
Set the interaction endpoint in Discord dev portal to the tunnel URL root (pointing to FastAPI path expected by the app). If an override is used, ensure `discord_webhook_url_override` is NOT set (that's for web CLI local test path).

d. In Discord test guild:
- `/plan roll a d20` with AVA flags OFF to confirm legacy path.
- Toggle `action_validation=true` and restart server, then re-run `/plan roll a d20`; verify no regression in visible output (should still show roll result).
- Failure scenario: `/plan check LCK dc 900` expecting error response (predicate gate rejection).
- `/do make a dex check with dc 12` expecting preview plus narration; with executor enabled you should see structured mechanics (e.g., roll components).
- `/do attack goblin with dagger` (if combat flag enabled) verifying `attack` ExecutionRequest step.

e. Confirm Idempotent Cache:
Send the exact `/plan roll a d20` twice quickly; second invocation should log a planner cache hit (`planner.cache.hit` or `planner.cache_lookup` result=hit/miss pair) without re-invoking LLM.

f. ActivityLog Verification:
If enabled, after `/do ...` commands, query DB or add a temporary endpoint/log inspection to ensure an `activity_log_id` is returned in server logs.

9. Feature Flag Matrix Quick Checks
(Flip one flag at a time; restart server after config changes.)
- `action_validation=true`, `predicate_gate=false`: Plan objects produced, no predicate gate log lines, feasibility always True.
- `action_validation=true`, `predicate_gate=true`: Failures surfaced for invalid abilities/DC.
- `executor=true` adds executor preview path; disable to test fallback messaging.
- `activity_log=true` adds ActivityLog writes (look for `activity_log.write_failed` warnings if misconfigured).

10. Troubleshooting
- Planner timeouts: If LLM unresponsive, planner falls back to `/roll 1d20` path (see timeout handler in `plan_cmd`).
- Predicate gate DB lookups require characters to exist; create characters via existing `/sheet create` (if present) or direct DB seeding for test.
- If commands not found in Discord: Re-run `register_commands.py` and ensure the application commands have propagated (may take a minute).

11. Suggested Next Implementation Steps (Gaps)
- Implement MCP adapter scaffold modules (interface + in-process shim) behind `features_mcp`.
- Add tier selection scaffolding: config-driven level; populate (even placeholder) `guards` list for each PlanStep.
- Introduce feasibility counters: `planner.feasible` / `planner.infeasible`.
- Executor metrics: `executor.preview.ok/error` plus `executor.apply.ok/error` once apply path integrated.
- Populate `repairs` and `alternatives` when predicate gate fails (e.g., suggest valid abilities).
- Add payload bounding (max args size, max steps length) and explicit orchestrator timeout config.
- Serialization stability tests with golden JSON for `Plan` including empty vs populated guards.
- AskReport generation step (ImprobabilityDrive) or mark deferred with ADR/Story.
- Runbook documentation file (`docs/dev/action-validation-runbook.md`) with rollout phases & rollback toggles.

12. Minimal Quick Validation Script (Optional)
To rapidly test planner + predicate gate after clone:
```
source .venv/bin/activate
python - <<'PY'
from Adventorator.config import load_settings
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters
import asyncio

class DummyLLM:
    async def generate_response(self, messages): return '{"command":"check","args":{"ability":"DEX","dc":12}}'

async def main():
    load_all_commands()
    cmd = find_command("plan", None)
    inv = Invocation(
        name="plan", subcommand=None,
        options={"message":"check dex dc 12"},
        user_id="1", channel_id="10", guild_id="100",
        responder=type("R",(),{"send":lambda self,msg,ephemeral=False: print("RESP:",msg)})(),
        settings=type("S",(),{
            "features_llm":True,
            "features_action_validation":True,
            "features_predicate_gate":True,
            "feature_planner_enabled":True,
        })(),
        llm_client=DummyLLM()
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)
    print("predicate.gate.ok =", get_counter("predicate.gate.ok"))
asyncio.run(main())
PY
```

**Next Actions (If You Want Help)**
- Draft MCP adapter skeleton + tests.
- Add feasibility & executor metrics counters.
- Prepare a runbook doc stub.