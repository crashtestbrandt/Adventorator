
## High-level architecture and code quality
- Command system: Clean separation with `Adventorator.commanding.slash_command` and dynamic loading fits the repo’s conventions. The `/plan` command in `Adventorator.commands.plan.plan_cmd` correctly validates options and defers I/O to repos and services.
- Planner vs Orchestrator: Good split. The planner outputs strict JSON via `Adventorator.planner.plan` using `Adventorator.planner_schemas.PlannerOutput`; the orchestrator performs guarded narration in `Adventorator.commands.do._handle_do_like`. Safety choices (allowlist, argument validation, “shadow mode,” transcripts) are sound.
- Data access: Proper use of `Adventorator.db.session_scope` and repos helpers like `Adventorator.repos.get_or_create_campaign`, `Adventorator.repos.ensure_scene`, and `Adventorator.repos.write_transcript` is consistent.
- Tests: Integration tests for `/plan` routing cover roll, check, OOC, unknown tool, and invalid JSON (tests/test_plan_integration.py, test_plan_more_integration.py, test_act_integration.py, tests/test_act_more_integration.py). These mirror the fake LLM pattern described in docs and assert metrics like `Adventorator.metrics.get_counter`.

## Gaps and concrete fixes
- Logging on failures: Your logging-improvement plan calls for structured logs with exc_info. In `_handle_do_like`, errors are caught but not logged. Add a structured error with request context.
- Planner feature flag naming: `Adventorator.commands.plan.plan_cmd` checks settings.feature_planner_enabled, while config exposes [features].planner. Normalize to support both names to avoid surprises in env overrides.
- Safer default visibility: The repo-wide tests and rollout guidance prefer “shadow mode” (LLM content not public). Your config defaults to `llm_visible = true`. Consider defaulting to false to reduce accidental public posting.
- DB error logging: Your logging plan (Phase 4) asks for logging exceptions in `session_scope`. Ensure errors are logged before rollback.
- Metrics parity: Tests assert accepted decisions. Make sure rejections (unknown tool or validation errors) increment a “rejected” counter so dashboards stay balanced.

Suggested patches
1) Add structured error logging to orchestrator delivery failures.

````python
# ...existing code...
import structlog
log = structlog.get_logger()
# ...existing code...

async def _handle_do_like(inv: Invocation, opts: DoOpts):
    # ...existing code...
    except Exception:
        # Log the failure with context and full traceback
        log.error(
            "orchestrator.delivery_failed",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            player_tx_id=player_tx_id,
            bot_tx_id=bot_tx_id,
            exc_info=True,
        )
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
            if bot_tx_id is not None:
                await repos.update_transcript_status(s, bot_tx_id, "error")
        await inv.responder.send("⚠️ Failed to deliver narration.", ephemeral=True)
# ...existing code...
````

2) Make `/plan` respect both planner flags to avoid config drift.

````python
# ...existing code...
@slash_command(name="plan", description="Let the DM figure out what to do.", option_model=PlanOpts)
async def plan_cmd(inv: Invocation, opts: PlanOpts):
    # Preconditions: require LLM available
    settings = inv.settings
    if not (settings and getattr(settings, "features_llm", False) and inv.llm_client):
        await inv.responder.send("❌ The planner/LLM is currently disabled.", ephemeral=True)
        return
    # Hard feature flag to disable planner instantly
    # Support either "feature_planner_enabled" (old) or "features_planner" (new) with a safe default
    planner_enabled = getattr(settings, "feature_planner_enabled", getattr(settings, "features_planner", True))
    if not planner_enabled:
        await inv.responder.send("❌ Planner is disabled by configuration.", ephemeral=True)
        return
    # ...existing code...
````

3) Log DB exceptions in `session_scope` (Phase 4 Task 4.2).

````python
# ...existing code...
import structlog
log = structlog.get_logger()

@asynccontextmanager
async def session_scope():
    # ...existing code...
    try:
        yield session
        await session.commit()
    except Exception:
        # New: structured error before rollback
        log.error("db.session_scope_error", exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()
# ...existing code...
````

4) Default visibility to shadow mode (safer-by-default; tests commonly set visible=False).

````toml
# ...existing code...
[features]
llm = true
planner = true
rules = true
combat = false
llm_visible = false  # safer default; set true explicitly when ready
# ...existing code...
````

## Progress vs your plan (README)
- Phase 0–4: Largely implemented per README.md. Verified interactions, rules engine, persistence, planner smart routing with allowlist and JSON validation, plus rate limiting and a 30s cache in `Adventorator.commands.plan.plan_cmd` and `Adventorator.planner.plan`.
- Logging improvement plan: Docs are thorough; patches above advance Phase 2 and Phase 4. Still to do: LLM client pre/post call logs in `Adventorator/llm.py` with duration and status, and planner decision logs carrying request_id.
- Tests: Routing and safety are covered (tests/test_plan_integration.py, tests/test_plan_more_integration.py). Consider adding rate-limit and cache-hit tests, and explicit “rejected” metric assertions to complement accepted decisions from `Adventorator.metrics.inc_counter`.

## Are spaCy or MCP warranted?
- spaCy: Not necessary for your planner. You’re using LLM JSON tool selection with strict schema validation; deterministic rules are handled in your rules engine. Adding classical NLP adds complexity without clear benefit given the strict, schema-first approach.
- MCP (Model Context Protocol): Useful if you plan to expose multiple tools/services across processes/providers and want a standard tool-calling bus. Today, your tool surface is internal and validated; MCP would be premature. Revisit if you externalize tools or need multi-agent/tool orchestration.

## On the path to full DnD 5e SRD mechanics?
- Yes, if you continue the “deterministic rules, data-driven tables, AI for narration only” approach. Focus next on:
  - Expand the rules engine (attack rolls, damage types, conditions, advantage/disadvantage propagation, proficiency, skills).
  - Initiative/turn system with a queue and locks (your roadmap mentions Redis; start with in-memory, then abstract).
  - Strict schemas for character sheets and effects; keep narration separate from mutations.
  - License hygiene: Model mechanics as code/data; don’t embed non-SRD content. Use SRD 5.1 (CC BY 4.0) data only.

## Best-practice checks
- Validation and allowlisting: Good. Keep the planner’s allowlist tight and surface “rejected” metrics explicitly.
- Logging: Move to consistent structured logs with `request_id` and `exc_info` across boundaries (Discord, LLM, DB). The patches above cover orchestrator/DB; add LLM pre/post logs next.
- Safety defaults: Prefer shadow mode by default; promote public visibility explicitly per environment.
- Errors: Avoid bare excepts without logs (fixed above). Preserve tracebacks.
- Config flags: Keep names consistent across config, settings, and handlers to avoid silent misconfig.
- Rate-limit and cache: Continue to prune timestamps in `_rl`; consider background cleanup if user cardinality grows.

## Notable symbols and files referenced
- Commands: `Adventorator.commands.plan.plan_cmd`, `Adventorator.commands.do._handle_do_like`
- Core: `Adventorator.commanding.slash_command`, `Adventorator.commanding.find_command`
- Planner: `Adventorator.planner.plan`, `Adventorator.planner_schemas.PlannerOutput`
- Data: `Adventorator.db.session_scope`, `Adventorator.repos.get_or_create_campaign`, `Adventorator.repos.ensure_scene`, `Adventorator.repos.write_transcript`, `Adventorator.repos.update_transcript_status`
- Metrics: `Adventorator.metrics.inc_counter`, `Adventorator.metrics.get_counter`
- Tests: test_plan_integration.py, test_plan_more_integration.py, test_act_integration.py, test_act_more_integration.py
- Config: config.toml