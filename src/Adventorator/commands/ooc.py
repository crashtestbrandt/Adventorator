from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import (
    Invocation,
    Option,
    slash_command,
)
from Adventorator.db import session_scope
from Adventorator.llm_prompts import (
    build_clerk_messages,
    build_ooc_narration_messages,
)


class OocOpts(Option):
    message: str = Field(description="Your out-of-character message")


@slash_command(
    name="ooc",
    description="Out-of-character narration (no dice).",
    option_model=OocOpts,
)
async def ooc_command(inv: Invocation, opts: OocOpts):
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

    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    player_tx_id = None
    bot_tx_id = None
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
        player_tx_id = player_tx.id

        # Build facts from recent transcripts for context
        txs = await repos.get_recent_transcripts(s, scene_id=scene.id, limit=15)
        clerk_msgs = build_clerk_messages(
            txs,
            player_msg=message,
            max_tokens=(
                getattr(settings, "llm_max_prompt_tokens", None) if settings else None
            ),
        )

    # Convert clerk messages to facts (exclude system, keep content)
    facts: list[str] = []
    for m in clerk_msgs:
        if m.get("role") == "system":
            continue
        facts.append(str(m.get("content", "")).strip())
    facts = [f for f in facts if f]

    # Build OOC narration-only prompt and call LLM for plain text
    ooc_msgs = build_ooc_narration_messages(
        facts,
        player_msg=message,
        max_tokens=(
            getattr(settings, "llm_max_prompt_tokens", None) if settings else None
        ),
    )
    narration = await llm.generate_response(ooc_msgs)
    if narration is None:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
        await inv.responder.send("❌ Failed to generate narration.", ephemeral=True)
        return

    # Persist bot transcript and send narration only (no dice)
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        bot_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "bot",
            narration,
            str(user_id),
            status="pending",
        )
        bot_tx_id = bot_tx.id

    try:
        if settings and getattr(settings, "features_llm_visible", False):
            await inv.responder.send(f"📖 Narration\n{narration}")
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

