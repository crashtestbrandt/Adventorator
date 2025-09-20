# Manual Smoke Tests

This doc outlines a quick manual smoke suite using both the Web CLI (`scripts/web_cli.py`) and the actual Discord client. Skip `scripts/cli.py` for now; focus on the same network path Discord uses.

Prereqs
- .env configured (Discord app ID, public key, bot token, webhook override for dev optional)
- App running locally (`make run`) or via docker compose (`docker compose up -d --build db app`)
- Enable feature flags in `config.toml` before starting the app:
  - `features.action_validation = true`
  - `features.predicate_gate = true`
  - `features.executor = true` (for mechanics previews) and `features.activity_log = true` (to persist ExecutionRequests)
- Reset local state if needed: `rm adventorator.sqlite3` (optional) and `PYTHONPATH=./src python scripts/expire_pending.py`
- Tunnel running (`make tunnel`) if testing from Discord
- Tail logs for observability during the run: `tail -f logs/adventorator.jsonl`; if you have the metrics endpoint exposed via config, poll `http://localhost:18000/metrics` between steps to watch counter deltas.

## Part A — Web CLI (local HTTP to /interactions)

Why: Exercise FastAPI `/interactions`, the `/plan` → predicate gate → orchestrator pipeline, and follow-up webhooks without Discord.

### 0) Connectivity & health
- Run: `PYTHONPATH=./src python scripts/web_cli.py ping`
- Expect: Deferred ACK followed by a follow-up "pong" (or success log) to the webhook sink. Confirms keys, headers, and webhook routing work before touching planner flows.

### 1) End-to-end planner happy path
- Run: `PYTHONPATH=./src python scripts/web_cli.py plan --text "make a dexterity check vs DC 12"`
- Expect: Deferred ACK followed by a `/check` resolution containing mechanics. Logs should include `planner.plan_built`, `predicate_gate.completed ok=true`, and `orchestrator.execution_request.built` with a non-empty `plan_id`.

### 2) Predicate gate rejection
- Run: `PYTHONPATH=./src python scripts/web_cli.py plan --text "Aria attempts a stealth check vs DC 25"`
- Before running, ensure no character named "Aria" exists in the campaign (fresh DB or rename accordingly).
- Expect: Follow-up with `🛑 Actor 'Aria' was not found...`. Logs emit `predicate_gate.rejected` with `exists(actor)` failure and `predicate.gate.fail_reason.exists(actor)` counter increments.

### 3) Planner cache reuse
- Run the command from step 1 again immediately.
- Expect: Webhook response identical to step 1. Logs show `planner.cache.hit` and the follow-up arrives without triggering a second LLM request.

### 4) Legacy mechanics sanity checks
- Run: `PYTHONPATH=./src python scripts/web_cli.py roll --expr 2d6+3`
- Run: `PYTHONPATH=./src python scripts/web_cli.py check --ability DEX --dc 15`
- Expect: Dice rolls and ability checks still succeed, proving feature flags didn't regress baseline commands.

### 5) Orchestrator preview + executor parity
- Run: `PYTHONPATH=./src python scripts/web_cli.py do --text "I swing at the skeleton with my longsword"`
- Expect: Mechanics preview sourced from the executor dry run (look for `orchestrator.executor.preview_ms` metric). The follow-up payload includes combat narration; logs capture `execution_request` with `attack` PlanStep args clamped to policy bounds.

### 6) Activity log persistence
- After step 5 completes, query the DB: `sqlite3 adventorator.sqlite3 "select id, event_type, summary from activity_logs order by id desc limit 1;"`
- Expect: A new row with `event_type` like `attack.preview` and a summary derived from the execution request. The payload should contain `plan_id`, mechanics preview, and narration (inspect via `sqlite3 ... select payload ...`).

### 7) Pending confirm flow (if enabled)
- Run: `PYTHONPATH=./src python scripts/web_cli.py do --text "I try to pick the lock"`
- Expect: Preview with an action ID. Confirm/cancel via:
  - `PYTHONPATH=./src python scripts/web_cli.py confirm --id <pending_id>`
  - `PYTHONPATH=./src python scripts/web_cli.py cancel --id <pending_id>`
- Expect: Confirm posts the mechanics follow-up and, with `features.activity_log=true`, another ActivityLog row. Cancel should emit a confirmation message without additional ActivityLog writes.

Notes
- For dev, you can route follow-ups to a local sink by setting the `X-Adventorator-Webhook-Base` header; see `config.toml` and `responder.py` override behavior.
- If you only want to capture webhook payloads, run the CLI with `--sink-only` to start the sink without sending an interaction.

## Part B — Discord client (end-to-end)

Why: Verify real user experience, intents, and permissions with signed requests.

Setup
- Run `python scripts/register_commands.py` to register slash commands in your dev guild.
- Start the tunnel and set the tunnel URL as your interaction endpoint in the Discord Developer Portal.

Smoke steps
1) `/plan "help the rogue pick a DC 13 lock"`
   - Expect `/check` mechanics preview plus narration. Verify Discord message embed includes the same `plan_id` logged in `planner.plan_built`.
2) `/plan "Aria pleads with the guard"`
   - With no `Aria` in the roster, expect an ephemeral rejection mirroring the predicate gate failure message from Part A.
3) `/plan "strike the cultist"`
   - Follow the response with `/do` confirm/cancel flows if executor preview asks for confirmation. Ensure confirmation posts a mechanics follow-up and (with `features.activity_log=true`) that the Activity Log table receives a new row.
4) `/ooc "Where does the corridor lead?"`
   - Expect LLM narration (visible if `features.llm_visible=true`). Check that transcript rows are still created.
5) `/roll 1d20` and `/check ability:DEX dc:15`
   - Sanity check that legacy commands stay unaffected while flags are on.
6) `/sheet show` (if a sheet exists)
   - Confirm sheet summaries still return and that predicate gate failures do not impact sheet-related commands.

Troubleshooting
- If no follow-up arrives, check logs for webhook errors; ensure `DISCORD_BOT_TOKEN` is set and not using an override URL accidentally.
- If signature verification fails, confirm Public Key and the tunnel path are correct and the trusted dev headers are only used in dev.
- For predicate gate debugging, temporarily disable `features.predicate_gate` in `config.toml` to confirm the issue isolates to deterministic validation rather than planner intent framing.
