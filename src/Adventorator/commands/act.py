from __future__ import annotations

from typing import Any
import asyncio
import structlog

from pydantic import Field

from Adventorator.commanding import Invocation, Option, find_command, slash_command
from Adventorator.db import session_scope
from Adventorator import repos
from Adventorator.metrics import inc_counter
from Adventorator.planner import plan, _cache_get, _cache_put, _is_allowed
from Adventorator.planner_schemas import PlannerOutput

log = structlog.get_logger()


class ActOpts(Option):
    message: str = Field(description="Freeform action/request")


@slash_command(name="act", description="Let the DM figure out what to do.", option_model=ActOpts)
async def act(inv: Invocation, opts: ActOpts):
    # Preconditions: require LLM available
    if not (inv.settings and getattr(inv.settings, "features_llm", False) and inv.llm_client):
        await inv.responder.send("❌ The planner/LLM is currently disabled.", ephemeral=True)
        return

    user_msg = (opts.message or "").strip()
    if not user_msg:
        await inv.responder.send("❌ You need to provide a message.", ephemeral=True)
        return

    inc_counter("planner.request")

    # Ensure scene + persist player's input (like /ooc)
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "player",
            user_msg,
            str(user_id),
        )
        scene_id = scene.id

    # Cache check
    cached = _cache_get(scene_id, user_msg)
    if cached is not None:
        try:
            out = PlannerOutput.model_validate(cached)  # type: ignore[name-defined]
        except Exception:
            out = None
        else:
            inc_counter("planner.cache.hit")
    else:
        # Plan using LLM with a soft timeout; fallback to roll 1d20 on timeout
        try:
            out = await asyncio.wait_for(plan(inv.llm_client, user_msg), timeout=6.0)  # type: ignore[arg-type]
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

    if not out:
        inc_counter("planner.parse_failed")
        await inv.responder.send("⚠️ I couldn't figure out a valid command.", ephemeral=True)
        return

    # Save to cache
    try:
        _cache_put(scene_id, user_msg, out.model_dump())  # type: ignore[arg-type]
    except Exception:
        pass

    target_name = out.command.replace(":", ".")
    target_top, _, target_sub = target_name.partition(".")

    cmd_name_flat = target_top + (f".{target_sub}" if target_sub else "")
    if not _is_allowed(cmd_name_flat):
        inc_counter("planner.decision.rejected")
        log.info("planner.decision", cmd=cmd_name_flat, accepted=False)
        await inv.responder.send("⚠️ That action isn't supported yet.", ephemeral=True)
        return

    cmd = find_command(target_top, target_sub or None)
    if not cmd:
        await inv.responder.send("⚠️ Planned command was not found.", ephemeral=True)
        return

    # Validate args against the command's option model
    try:
        option_obj = cmd.option_model.model_validate(out.args)  # type: ignore[attr-defined]
    except Exception as e:
        inc_counter("planner.decision.rejected")
        log.info("planner.decision", cmd=cmd_name_flat, accepted=False, error=str(e))
        await inv.responder.send("⚠️ Planned arguments were invalid.", ephemeral=True)
        return

    inc_counter("planner.decision.accepted")
    log.info("planner.decision", cmd=cmd_name_flat, accepted=True)

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
    )
    await cmd.handler(new_inv, option_obj)
