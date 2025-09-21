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
- MCP Adapters (Phase 7): In-process adapters live under `src/Adventorator/mcp/` with contracts in `contracts/mcp/`. `Executor` routes checks, attacks, and damage through the MCP client when `features_mcp` is enabled; parity tests cover legacy vs MCP paths (`tests/test_mcp_executor_parity.py`).
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

**Environment Modes (Host vs Docker) & Env Files**
- Host Local Mode: Invoked via `make run` / `make dev`. Reads configuration from `config.toml` plus optional `.env.local` (highest precedence) for secrets (`DISCORD_*`, `LLM_*`, overrides). Falls back to legacy `.env` only if `.env.local` absent (kept for backward compatibility; do not reintroduce new values there).
- Docker Dev Mode: Invoked via `make compose-dev` (or related compose targets). Containers load variables from `.env.docker` (purpose‑built for container context: e.g. `DATABASE__HOST=db`). Host-only secrets that should not be baked into images stay in `.env.local` and are NOT auto-copied—mount or pass through if required.
- Separation Rationale: Prevent accidental leakage of host credentials into containers and eliminate manual file swapping. Enables concurrent workflows (host web CLI vs containerized service) without editing env files.
- Practical Guidelines:
  - Put Discord credentials, generated signing/dev keys, and LLM provider keys in `.env.local`.
  - Put container networking / service hostnames (`POSTGRES_HOST=db`, any port remaps) in `.env.docker`.
  - Never commit filled `.env.local` / `.env.docker`; provide examples (`.env.docker.example`).
  - Scripts (`register_commands.py`, `generate_keys.py`) now prefer `.env.local`; they warn only if both missing.
- Port Management: `make dev` / `make run` will auto free (or fail fast about) port 18000; compose variant performs its own mapping and can use auto‑selection helpers if added later.

**Dev Webhook Override & Follow-Up Gating**
- Purpose: Provide deterministic, local visibility of follow-up (secondary) interaction messages without sending them to real Discord webhooks.
- Activation: Set `DISCORD_WEBHOOK_URL_OVERRIDE` to the app's internal dev sink URL (e.g. `http://127.0.0.1:18000/dev-webhook/webhooks/{APP_ID}/{TOKEN}`). The web CLI detects this pattern and switches to polling mode instead of spawning the legacy sink.
- Security / Safety Gating: Override is applied ONLY for dev-signed (web_cli) interactions. Real Discord interaction requests (validated via signature + application id / token that are not the dev key) bypass the override so production / guild messages continue to flow to actual Discord webhooks.
- Endpoints:
  - POST `/dev-webhook/webhooks/{application_id}/{token}`: Receives and logs follow-up payload (mirrors Discord's semantics for testing).
  - GET `/dev-webhook/latest/{token}`: Returns last received payload for polling (used by `web_cli` to print follow-up content after initial ACK).
- Plan Command Guarantee: `/plan` now always emits a follow-up (even cache hits) so the CLI never “hangs” waiting; this was a regression fix.
- Regression Prevention: Attachment and rich content follow-ups are also gated—only dev interactions can be rerouted ensuring no accidental leakage to dev sink from real users.

**Local Plan Preview Quick Setup (TL;DR)**
1. Ensure app is running (host or compose) on port 18000.
2. In `.env.local` (host) and/or `.env.docker` (container) set:
  ```
  DISCORD_WEBHOOK_URL_OVERRIDE=http://127.0.0.1:18000/dev-webhook
  ```
  (No trailing `/webhooks/...` — the application appends `/webhooks/{app_id}/{token}` internally.)
3. Restart the app so settings reload.
4. Run:
  ```bash
  .venv/bin/python scripts/web_cli.py plan "Scout the hallway quietly"
  ```
5. Expect an immediate ACK plus a polled preview block beginning with `🧭 Plan Preview:`.

**Troubleshooting Preview Not Showing**
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| CLI prints `(No follow-up content...)` and warning about setting override | Server not started with `DISCORD_WEBHOOK_URL_OVERRIDE` | Add variable, restart app |
| 404 on POST `/webhooks/{app_id}/{token}` in logs | CLI injected header without `/dev-webhook` prefix (older CLI) | Update CLI (current version skips header when override missing) or set override env |
| 401 `Invalid Webhook Token` in logs | Server attempted real Discord call with fake token (no override) | Set `DISCORD_WEBHOOK_URL_OVERRIDE` locally |
| Preview truncated or empty | Planner produced zero steps (edge case) | Verify planner logs; ensure prompt not empty |
| Multiple rapid polls (spam) | Normal polling loop (0.5s) while waiting for planner LLM | Ignore; preview prints when available |

**Design Notes**
- We intentionally use a base URL without the `/webhooks/{APP_ID}/{TOKEN}` suffix so the responder can construct standard Discord-style URLs uniformly.
- The CLI now emits a warning when it assumed an override (based on host config) but the server still returns no dev payload—guiding developers to set the missing env var.
- Using a true Discord token in local dev is discouraged; rely on the override + fake token path for deterministic testing without external dependencies.

**Metrics Gap Matrix (Implemented vs Target)**
| Category | Implemented Metrics (examples) | Missing / Planned Metrics | Notes |
|----------|--------------------------------|---------------------------|-------|
| Planner | `planner.cache.lookup` (hit/miss labels), timing logs (request ms), implicit feasibility via downstream success | `planner.feasible`, `planner.infeasible` | Add explicit feasibility counters for ops visibility |
| Predicate Gate | `predicate.gate.ok`, `predicate.gate.error`, `predicate.gate.fail_reason.<code>` | (Possibly) `predicate.gate.bypass` when disabled | Fail reasons granular; bypass would aid rollout analysis |
| Executor Preview | `orchestrator.executor.preview_ms` (timing) | `executor.preview.ok`, `executor.preview.error` | Need success/failure counts (timing alone insufficient) |
| Executor Apply (future) | None (apply path not integrated) | `executor.apply.ok`, `executor.apply.error`, `executor.apply_ms` | Add with real apply integration |
| Activity Log | `activity_log.write_failed` (error counter) | `activity_log.write.ok` | Success counter needed for ratios / SLO |
| Guards / Repairs | None | `plan.guards.populated`, `plan.repairs.suggested` | Emitted when planner or gate populates remediation data |
| Feasibility Repair | None | `planner.repair.generated` | After introducing repair suggestions |
| Payload / Size | None | `planner.request.truncated`, `plan.steps.capped` | For bounding / safety instrumentation |

**Guards, Repairs & Roadmap Clarification**
- Current State: `Plan` model fields `guards`, `repairs`, `alternatives` exist but remain empty lists throughout planner + gate path; no serialization tests validate non-empty cases.
- Near-Term Steps:
  1. Introduce simple static guard population (e.g., ability existence check becomes a guard object with condition + remediation hint).
  2. On predicate failure, synthesize `repairs` (e.g., suggest valid abilities or lower DC range) and return them in follow-up payload for future UI surfacing.
  3. Add golden serialization tests capturing: empty fields, single guard, multiple guards + repairs.
  4. Emit metrics counters (`plan.guards.populated`, `plan.repairs.suggested`).
  5. Extend planner to optionally request tiered alternative steps; store in `alternatives` with ranking metadata.
- Validation Goal: Ensure downstream (executor, potential MCP adapter) can safely ignore unknown guard types until fully supported (forward compatibility).

**Outcome Summary (Updated)**
- Local Dev UX: Dual env file pattern implemented; documentation now explicit about precedence and separation, reducing onboarding ambiguity.
- Reliability: Follow-up override gating verified; prevents accidental hijack of real Discord interactions while preserving deterministic local visibility.
- Observability: Predicate gate metrics comprehensive; clear, enumerated gaps now captured in matrix to drive next instrumentation sprint.
- Remaining Gaps: Metrics (feasibility, executor success/failure, activity_log.write.ok), guards/repairs population, AskReport production, payload/time bounding, golden serialization tests.
- Recommended Immediate Next Actions: (1) Implement feasibility + executor preview counters, (2) add `activity_log.write.ok`, (3) scaffold minimal guard objects with serialization test, (4) introduce repair suggestion for common predicate failures.

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
- Under `[features]` set `action_validation = true` and `predicate_gate = true` in `config.toml`, then restart the server.
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
- In `.env.local` (host) or `.env.docker` (compose) or exported environment:
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