from __future__ import annotations

from typing import Any

from pydantic import Field

from Adventorator.commanding import Invocation, Option, find_command, slash_command
from Adventorator.planner import plan


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

    # Plan using LLM
    out = await plan(inv.llm_client, user_msg)  # type: ignore[arg-type]
    if not out:
        await inv.responder.send("⚠️ I couldn't figure out a valid command.", ephemeral=True)
        return

    # For Milestone 0, allow only mapping to /do
    target_name = out.command
    target_sub = out.subcommand
    if target_name not in {"do"}:
        await inv.responder.send("⚠️ That action isn't supported yet.", ephemeral=True)
        return

    cmd = find_command(target_name, target_sub)
    if not cmd:
        await inv.responder.send("⚠️ Planned command was not found.", ephemeral=True)
        return

    # Validate args against the command's option model
    try:
        option_obj = cmd.option_model.model_validate(out.args)  # type: ignore[attr-defined]
    except Exception:
        await inv.responder.send("⚠️ Planned arguments were invalid.", ephemeral=True)
        return

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
