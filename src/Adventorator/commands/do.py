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
    if len(message) < 3 or message.lower() in {"y", "n", "yes", "no", "ok", "k"}:
        await inv.responder.send(
            "⚠️ Please provide a bit more detail so I can narrate.", ephemeral=True
        )
        return

    # Resolve scene context and persist player's input
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    player_tx_id = None
    bot_tx_id = None
    scene_id = None
    allowed: list[str] = []
    # Resolve scene and write the player transcript within the same session
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        player_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "player",
            message,
            str(user_id),
            status="pending",
        )
        player_tx_id = getattr(player_tx, "id", None)
        scene_id = scene.id
        # Derive allowed actors from characters in this campaign
        allowed = await repos.list_character_names(s, campaign.id)

    # Orchestrate
    try:
        res = await run_orchestrator(
            scene_id=scene_id or 0,
            player_msg=message,
            llm_client=llm,
            prompt_token_cap=getattr(settings, "llm_max_prompt_tokens", None) if settings else None,
            allowed_actors=allowed,
        )
    except Exception:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
        await inv.responder.send("❌ Failed to process your request.", ephemeral=True)
        return

    if res.rejected:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
        await inv.responder.send(
            f"🛑 Proposal rejected: {res.reason or 'invalid'}", ephemeral=True
        )
        return

    # Prepare bot transcript (pending)
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        bot_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "bot",
            res.narration,
            str(user_id),
            meta={"mechanics": res.mechanics},
            status="pending",
        )
        bot_tx_id = getattr(bot_tx, "id", None)

    # Attempt to send and mark statuses
    try:
        if settings and getattr(settings, "features_llm_visible", False):
            formatted = f"🧪 Mechanics\n{res.mechanics}\n\n📖 Narration\n{res.narration}"
            await inv.responder.send(formatted)
        else:
            await inv.responder.send(
                "Narrator ran in shadow mode (log-only). Ask a GM to enable visibility.",
                ephemeral=True,
            )
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "complete")
            if bot_tx_id is not None:
                await repos.update_transcript_status(s, bot_tx_id, "complete")
    except Exception:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
            if bot_tx_id is not None:
                await repos.update_transcript_status(s, bot_tx_id, "error")
        await inv.responder.send("⚠️ Failed to deliver narration.", ephemeral=True)


@slash_command(name="do", description="Take an in-world action.", option_model=DoOpts)
async def do_command(inv: Invocation, opts: DoOpts):
    await _handle_do_like(inv, opts)
