# src/Adventorator/commands/ooc_do.py
from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.orchestrator import run_orchestrator


class DoOpts(Option):
    message: str = Field(description="Your action or narration message")


async def _handle_do_like(inv: Invocation, opts: DoOpts):
    settings = inv.settings
    llm = inv.llm_client if (settings and getattr(settings, "features_llm", False)) else None
    if not llm:
        await inv.responder.send(
            "❌ The LLM narrator is currently disabled.", ephemeral=True
        )
        return

    message = (opts.message or "").strip()
    if not message:
        await inv.responder.send("❌ You need to provide a message.", ephemeral=True)
        return

    # Resolve scene context and persist player's input
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(
            s, campaign.id, scene.id, channel_id, "player", message, str(user_id)
        )
        scene_id = scene.id

    # Orchestrate
    res = await run_orchestrator(
        scene_id=scene_id,
        player_msg=message,
        llm_client=llm,
        prompt_token_cap=getattr(settings, "llm_max_prompt_tokens", None) if settings else None,
    )

    if res.rejected:
        await inv.responder.send(
            f"🛑 Proposal rejected: {res.reason or 'invalid'}", ephemeral=True
        )
        return

    if settings and getattr(settings, "features_llm_visible", False):
        formatted = f"🧪 Mechanics\n{res.mechanics}\n\n📖 Narration\n{res.narration}"
        await inv.responder.send(formatted)
    else:
        await inv.responder.send(
            "Narrator ran in shadow mode (log-only). Ask a GM to enable visibility.",
            ephemeral=True,
        )

    # Log bot narration
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "bot",
            res.narration,
            str(user_id),
            meta={"mechanics": res.mechanics},
        )


@slash_command(name="do", description="Take an in-world action.", option_model=DoOpts)
async def do_command(inv: Invocation, opts: DoOpts):
    await _handle_do_like(inv, opts)


@slash_command(name="ooc", description="Out-of-character narrator.", option_model=DoOpts)
async def ooc_command(inv: Invocation, opts: DoOpts):
    await _handle_do_like(inv, opts)
