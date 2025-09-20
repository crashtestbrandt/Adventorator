from __future__ import annotations

import asyncio
import time

import structlog
from pydantic import Field

from Adventorator import repos
from Adventorator.action_validation import (
    Plan,
    PredicateContext,
    evaluate_predicates,
    plan_from_planner_output,
    plan_registry,
    planner_output_from_plan,
    record_plan_steps,
    record_predicate_gate_outcome,
)
from Adventorator.action_validation.logging_utils import log_event, log_rejection
from Adventorator.commanding import Invocation, Option, find_command, slash_command
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter
from Adventorator.planner import _cache_get, _cache_put, _is_allowed, plan
from Adventorator.planner_schemas import PlannerOutput

log = structlog.get_logger()

_PLAN_TIMEOUT = 12.0  # seconds (default; overridden by settings if provided)

# Simple in-memory per-user rate limiter: max N requests per window
_RL_MAX = 5
_RL_WINDOW = 60.0
_rl: dict[str, list[float]] = {}


def _rate_limited(user_id: str) -> bool:
    now = time.time()
    wins = _rl.setdefault(user_id, [])
    # Drop entries outside the window
    cutoff = now - _RL_WINDOW
    while wins and wins[0] < cutoff:
        wins.pop(0)
    if len(wins) >= _RL_MAX:
        return True
    wins.append(now)
    return False


class PlanOpts(Option):
    message: str = Field(description="Freeform action/request")


@slash_command(name="plan", description="Let the DM figure out what to do.", option_model=PlanOpts)
async def plan_cmd(inv: Invocation, opts: PlanOpts):
    # Preconditions: require LLM available
    settings = inv.settings
    if not (settings and getattr(settings, "features_llm", False) and inv.llm_client):
        await inv.responder.send("❌ The planner/LLM is currently disabled.", ephemeral=True)
        return
    # Hard feature flag to disable planner instantly
    if not getattr(settings, "feature_planner_enabled", True):
        await inv.responder.send("❌ Planner is disabled by configuration.", ephemeral=True)
        return

    user_msg = (opts.message or "").strip()
    if not user_msg:
        await inv.responder.send("❌ You need to provide a message.", ephemeral=True)
        return

    # Per-user simple rate limiting
    if inv.user_id and _rate_limited(str(inv.user_id)):
        await inv.responder.send(
            "⏳ You're doing that a bit too quickly. Please wait a moment.",
            ephemeral=True,
        )
        return

    inc_counter("planner.request")
    # We don't yet know scene id; will log again post scene lookup.
    log_event("planner", "initiated", user_id=str(inv.user_id or ""))

    # Ensure scene + persist player's input (like /ooc)
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)
    use_action_validation = bool(getattr(settings, "features_action_validation", False))
    use_predicate_gate = bool(getattr(settings, "features_predicate_gate", False))

    allowed_actor_names: list[str] = []
    campaign_id = 0
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        player_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "player",
            user_msg,
            str(user_id),
        )
        player_tx_id = getattr(player_tx, "id", None)
        scene_id = scene.id
        log_event(
            "planner",
            "context_ready",
            scene_id=scene_id,
            campaign_id=campaign.id,
            user_id=user_id,
            action_validation=use_action_validation,
            predicate_gate=use_predicate_gate,
        )
        campaign_id = campaign.id
        if use_action_validation and use_predicate_gate:
            try:
                allowed_actor_names = await repos.list_character_names(s, campaign.id)
            except Exception:
                allowed_actor_names = []

    # Planner timeout (allow override via settings)
    try:
        timeout_s = float(getattr(settings, "planner_timeout_seconds", _PLAN_TIMEOUT))
    except Exception:
        timeout_s = _PLAN_TIMEOUT

    # Cache check
    plan_obj: Plan | None = None
    out: PlannerOutput | None = None

    cached = _cache_get(guild_id, channel_id, user_msg)
    if cached is None:
        log_event(
            "planner",
            "cache_lookup",
            result="miss",
            guild_id=guild_id,
            channel_id=channel_id,
            msg_hash=hash(user_msg),
        )
    if cached is not None:
        # Defensive: ensure cache hit metric present even if later parsing fails.
        # Do not manually increment planner.cache.hit here; rely on _cache_get.
        cached_payload, schema = cached
        cache_hit = True
        try:
            if schema == "plan":
                plan_obj = Plan.model_validate(cached_payload)
                out = planner_output_from_plan(plan_obj)
            else:
                out = PlannerOutput.model_validate(cached_payload)  # type: ignore[name-defined]
                if use_action_validation and out is not None:
                    plan_obj = plan_from_planner_output(out)
            # If action validation disabled, no further transformation needed; ensure hit metric remains.
            # Non-action-validation path: rely solely on _cache_get metric.
        except Exception:
            # Treat as cache miss by clearing outputs
            plan_obj = None
            out = None
            cache_hit = False
        if cache_hit and out is not None:
            # _cache_get already emitted planner.cache.hit metric; just log.
            log_event(
                "planner",
                "cache_hit",
                schema=schema,
                scene_id=scene_id,
                guild_id=guild_id,
                channel_id=channel_id,
            )
    else:
        # Plan using LLM with a soft timeout; fallback to roll 1d20 on timeout
        try:
            result = await asyncio.wait_for(
                plan(inv.llm_client, user_msg, return_plan=use_action_validation),  # type: ignore[arg-type]
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            # Friendly fallback
            fallback_text = "I couldn't decide in time; rolling a d20."
            cmd = find_command("roll", None)
            if cmd is None:
                await inv.responder.send("⚠️ Timeout while planning.", ephemeral=True)
                return
            opt_obj = cmd.option_model.model_validate({"expr": "1d20"})  # type: ignore[attr-defined]
            await inv.responder.send(fallback_text, ephemeral=True)
            await cmd.handler(inv, opt_obj)
            return

        else:
            if isinstance(result, Plan):
                plan_obj = result
                out = planner_output_from_plan(result)
            else:
                out = result
                if use_action_validation and out is not None:
                    plan_obj = plan_from_planner_output(out)

    # Early cache write (before allowlist / predicate gate) so that even if
    # later validation rejects, subsequent identical requests avoid a second
    # LLM call. (Acceptable because cache is an optimization of pure planner
    # decision shape, independent of later gating.)
    try:
        if out is not None:
            if plan_obj is not None:
                _cache_put(guild_id, channel_id, user_msg, plan_obj.model_dump(), schema="plan")
            else:
                _cache_put(
                    guild_id,
                    channel_id,
                    user_msg,
                    out.model_dump(),  # type: ignore[arg-type]
                    schema="planner_output",
                )
    except Exception:
        pass

    if not out:
        inc_counter("planner.parse_failed")
        await inv.responder.send("⚠️ I couldn't figure out a valid command.", ephemeral=True)
        return

    target_name = out.command.replace(":", ".")
    target_top, _, target_sub = target_name.partition(".")

    cmd_name_flat = target_top + (f".{target_sub}" if target_sub else "")
    if not _is_allowed(cmd_name_flat):
        inc_counter("planner.decision.rejected")
        inc_counter("planner.allowlist.rejected")
        log_rejection(
            "planner",
            reason="allowlist",
            cmd=cmd_name_flat,
            confidence=getattr(out, "confidence", None),
            rationale=(getattr(out, "rationale", None) or "")[:120],
        )
        await inv.responder.send("⚠️ That action isn't supported yet.", ephemeral=True)
        return

    cmd = find_command(target_top, target_sub or None)
    if not cmd:
        await inv.responder.send("⚠️ Planned command was not found.", ephemeral=True)
        return

    if use_action_validation and use_predicate_gate:
        try:
            ctx = PredicateContext(
                campaign_id=int(campaign_id),
                scene_id=int(scene_id),
                user_id=int(user_id) if user_id else None,
                allowed_actors=tuple(allowed_actor_names),
            )
        except Exception:
            ctx = PredicateContext(
                campaign_id=int(campaign_id),
                scene_id=int(scene_id),
                user_id=None,
                allowed_actors=tuple(allowed_actor_names),
            )
        log_event("predicate_gate", "initiated", cmd=cmd_name_flat, scene_id=scene_id)
        gate_result = await evaluate_predicates(out, context=ctx)
        record_predicate_gate_outcome(ok=gate_result.ok)
        if not gate_result.ok:
            plan_obj = plan_from_planner_output(out)
            plan_obj = plan_obj.model_copy(
                update={
                    "feasible": False,
                    "steps": [],
                    "failed_predicates": [failure.as_dict() for failure in gate_result.failed],
                }
            )
            plan_registry.register_plan(plan_obj)
            log_rejection(
                "predicate_gate",
                reason="failed",
                cmd=cmd_name_flat,
                failures=[failure.as_dict() for failure in gate_result.failed],
            )
            # Emit per-failure counters for observability (predicate.gate.fail_reason.<code>)
            try:
                for failure in gate_result.failed:
                    code = failure.code.replace(" ", "_").replace("/", "_")
                    inc_counter(f"predicate.gate.fail_reason.{code}")
            except Exception:
                pass
            # Record steps metric (zero steps -> no increment) and completed lifecycle.
            try:
                record_plan_steps(plan_obj)
            except Exception:
                pass
            log_event(
                "predicate_gate",
                "completed",
                cmd=cmd_name_flat,
                ok=False,
                failure_count=len(gate_result.failed),
            )
            inc_counter("planner.decision.rejected")
            reason = gate_result.failed[0].message if gate_result.failed else "Action not feasible."
            await inv.responder.send(f"🛑 {reason}", ephemeral=True)
            return
        else:
            log_event("predicate_gate", "completed", cmd=cmd_name_flat, ok=True, failure_count=0)
    # Validate args against the command's option model
    try:
        option_obj = cmd.option_model.model_validate(out.args)  # type: ignore[attr-defined]
    except Exception as e:
        inc_counter("planner.decision.rejected")
        log_rejection("planner", reason="arg_validation", cmd=cmd_name_flat, error=str(e))
        guidance: str | None = None
        if cmd_name_flat in {"sheet.create"}:
            guidance = (
                "To create a character, use /sheet create and provide the json option with "
                'your character sheet JSON. Example: {"name": "Aria", '
                '"class": "Fighter", "level": 1, ...}'
            )
        elif cmd_name_flat in {"sheet.show"}:
            guidance = (
                "To show a character, use /sheet show with the name option. Example: name: Aria"
            )
        elif cmd_name_flat == "check":
            guidance = (
                "Use /check with at least ability (STR/DEX/...). Optionally include dc. "
                "Example: ability: DEX dc: 12"
            )
        elif cmd_name_flat == "roll":
            guidance = 'Use /roll with an expr like 1d20 or 2d6+3. Example: expr: "1d20"'
        elif cmd_name_flat == "do":
            guidance = (
                "Use /do with a short action description. Example: message: "
                '"I sneak along the wall"'
            )

        msg = guidance or "⚠️ Planned arguments were invalid."
        await inv.responder.send(msg, ephemeral=True)
        return

    inc_counter("planner.decision.accepted")
    log_event(
        "planner",
        "decision",
        cmd=cmd_name_flat,
        accepted=True,
        confidence=getattr(out, "confidence", None),
        rationale=(getattr(out, "rationale", None) or "")[:120],
    )

    if use_action_validation:
        if plan_obj is None:
            plan_obj = plan_from_planner_output(out)
        plan_registry.register_plan(plan_obj)
        record_plan_steps(plan_obj)
        log_event("planner", "plan_built", plan_id=plan_obj.plan_id, feasible=plan_obj.feasible)
        log_event(
            "planner",
            "completed",
            cmd=cmd_name_flat,
            feasible=plan_obj.feasible,
            accepted=True,
        )
    else:
        log_event(
            "planner",
            "completed",
            cmd=cmd_name_flat,
            feasible=None,
            accepted=True,
        )

    # Re-dispatch to the planned command handler with the SAME invocation context
    new_inv = Invocation(
        name=cmd.name,
        subcommand=cmd.subcommand,
        options=out.args,
        user_id=inv.user_id,
        channel_id=inv.channel_id,
        guild_id=inv.guild_id,
        responder=inv.responder,
        settings=inv.settings,
        llm_client=inv.llm_client,
        ruleset=inv.ruleset,
    )
    await cmd.handler(new_inv, option_obj)
    # Fallback: Some legacy planned commands may be no-ops (e.g., roll routed internally
    # without emitting a follow-up). To avoid silent CLI experience, send a minimal
    # confirmation if nothing has been sent yet. We approximate by emitting only for
    # simple roll/check actions where plan produced no multi-step execution.
    try:
        if cmd_name_flat in {"roll", "check"}:
            # Provide a lightweight hint to user; actual mechanics will be in logs or downstream
            await inv.responder.send("✅ Planned action processed.", ephemeral=True)
    except Exception:
        pass
