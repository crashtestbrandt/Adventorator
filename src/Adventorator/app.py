# app.py

from fastapi import FastAPI, Request, HTTPException
from Adventorator.logging import setup_logging
from Adventorator.config import load_settings
from Adventorator.crypto import verify_ed25519
from Adventorator.discord_schemas import Interaction
from Adventorator.responder import respond_pong, respond_deferred, followup_message
from Adventorator.rules.dice import DiceRNG
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.db import session_scope
from Adventorator.schemas import CharacterSheet
from Adventorator import repos
import structlog
import asyncio
import json
from Adventorator.llm import LLMClient
from Adventorator.orchestrator import run_orchestrator

rng = DiceRNG()  # TODO: Seed per-scene later

log = structlog.get_logger()
settings = load_settings()
setup_logging()
app = FastAPI(title="Adventorator")

llm_client = None
if settings.features_llm:
    llm_client = LLMClient(settings)


@app.on_event("shutdown")
async def shutdown_event():
    if llm_client:
        await llm_client.close()

DISCORD_SIG_HEADER = "X-Signature-Ed25519"
DISCORD_TS_HEADER = "X-Signature-Timestamp"

@app.post("/interactions")
async def interactions(request: Request):
    raw = await request.body()
    sig = request.headers.get(DISCORD_SIG_HEADER)
    ts  = request.headers.get(DISCORD_TS_HEADER)
    if not sig or not ts:
        raise HTTPException(status_code=401, detail="missing signature headers")

    if not verify_ed25519(settings.discord_public_key, ts, raw, sig):
        raise HTTPException(status_code=401, detail="bad signature")

    inter = Interaction.model_validate_json(raw)

    async with session_scope() as s:
        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        # Content can be reconstructed from command name/options; store a compact form:
        # msg = f"/{inter.data.name}" if inter.data and inter.data.name else "<interaction>"
        # await repos.write_transcript(s, campaign.id, scene.id, channel_id, "player", msg, str(user_id), meta=inter.model_dump())

    # Ping = 1
    if inter.type == 1:
        return respond_pong()

    # Anything else: immediately DEFER (type 5) to satisfy the 3s budget.

    if inter.type == 2 and inter.data and inter.data.name:
        asyncio.create_task(_dispatch_command(inter))
    return respond_deferred()

async def _dispatch_command(inter: Interaction):
    name = inter.data.name

    if name == "sheet":
        sub = _subcommand(inter)
        if sub == "create":
            raw = _option(inter, "json")
            if raw is None or len(raw) > 16_000:
                await followup_message(inter.application_id, inter.token, "❌ JSON missing or too large (16KB max).", ephemeral=True)
                return
            try:
                payload = json.loads(raw)
                sheet = CharacterSheet.model_validate(payload)
            except Exception as e:
                await followup_message(inter.application_id, inter.token, f"❌ Invalid JSON or schema: {e}", ephemeral=True)
                return

            # Resolve context (guild/channel/user)
            guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)  # implement this helper
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
                player = await repos.get_or_create_player(s, user_id, username)
                await repos.ensure_scene(s, campaign.id, channel_id)

                ch = await repos.upsert_character(s, campaign.id, player.id, sheet)
                await repos.write_transcript(s, campaign.id, None, channel_id, "system", "sheet.create", str(user_id), meta={"name": sheet.name})

            await followup_message(inter.application_id, inter.token, f"✅ Sheet saved for **{sheet.name}**")
            return

        elif sub == "show":
            who = _option(inter, "name")
            guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                ch = await repos.get_character(s, campaign.id, who)
                if not ch:
                    await followup_message(inter.application_id, inter.token, f"❌ No character named **{who}**", ephemeral=True)
                    return
                await repos.write_transcript(s, campaign.id, None, channel_id, "system", "sheet.show", str(user_id), meta={"name": who})

            # present a compact summary
            sheet = ch.sheet
            summary = (
                f"**{sheet['name']}** — {sheet['class']} {sheet['level']}\n"
                f"AC {sheet['ac']} | HP {sheet['hp']['current']}/{sheet['hp']['max']} | "
                f"STR {sheet['abilities']['STR']} DEX {sheet['abilities']['DEX']} CON {sheet['abilities']['CON']} "
                f"INT {sheet['abilities']['INT']} WIS {sheet['abilities']['WIS']} CHA {sheet['abilities']['CHA']}"
            )
            await followup_message(inter.application_id, inter.token, summary, ephemeral=True)
            return

    if name == "roll":
        # expect option "expr"
        expr = _option(inter, "expr", default="1d20")
        adv = bool(_option(inter, "advantage", default=False))
        dis = bool(_option(inter, "disadvantage", default=False))
        res = rng.roll(expr, advantage=adv, disadvantage=dis)
        text = f"🎲 `{expr}` → rolls {res.rolls} {'(adv)' if adv else '(dis)' if dis else ''} = **{res.total}**"
        await followup_message(inter.application_id, inter.token, text)
    elif name == "check":
        # options: ability, score, proficient, expertise, prof_bonus, dc, advantage, disadvantage
        ability = _option(inter, "ability", default="DEX").upper()
        score = int(_option(inter, "score", default=10))
        prof = bool(_option(inter, "proficient", default=False))
        exp  = bool(_option(inter, "expertise", default=False))
        pb   = int(_option(inter, "prof_bonus", default=2))
        dc   = int(_option(inter, "dc", default=15))
        adv  = bool(_option(inter, "advantage", default=False))
        dis  = bool(_option(inter, "disadvantage", default=False))

        # d20 (1 or 2 rolls depending on adv/dis)
        res_roll = rng.roll("1d20", advantage=adv, disadvantage=dis)
        ci = CheckInput(ability=ability, score=score, proficient=prof, expertise=exp,
                        proficiency_bonus=pb, dc=dc, advantage=adv, disadvantage=dis)
        out = compute_check(ci, res_roll.rolls[:2] if len(res_roll.rolls) >= 2 else [res_roll.rolls[0]])
        verdict = "✅ success" if out.success else "❌ fail"
        text = (
            f"🧪 **{ability}** check vs DC {dc}\n"
            f"• d20: {out.d20} → pick {out.pick}\n"
            f"• mod: {out.mod:+}\n"
            f"= **{out.total}** → {verdict}"
        )
        await followup_message(inter.application_id, inter.token, text)
    elif name == "ooc":
        if not settings.features_llm or not llm_client:
            await followup_message(inter.application_id, inter.token, "❌ The LLM narrator is currently disabled.", ephemeral=True)
            return
        
        message = _option(inter, "message")
        if not message:
            await followup_message(inter.application_id, inter.token, "❌ You need to provide a message.", ephemeral=True)
            return

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)

        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)

            # 1. Write the player's message to the transcript immediately
            await repos.write_transcript(s, campaign.id, scene.id, channel_id, "player", message, str(user_id))

            # 2. Fetch recent history for context, only from this user
            history = await repos.get_recent_transcripts(s, scene.id, limit=15, user_id=str(user_id))
            
            # 3. Format history for the LLM prompt
            prompt_messages = []
            for entry in history:
                # Map our author types to LLM roles
                role = "user" if entry.author == "player" else "assistant" if entry.author == "bot" else None
                if role:
                    prompt_messages.append({"role": role, "content": entry.content})
            
            # 4. Call the LLM to get a narrative response
            log.info("Generating LLM response", scene_id=scene.id, history_len=len(prompt_messages))
            llm_response = await llm_client.generate_response(prompt_messages)

            if not llm_response:
                # The LLM client already logs errors, just inform the user.
                await followup_message(inter.application_id, inter.token, "The narrator is silent. (No response from LLM)", ephemeral=True)
                return
            
            # 5. Send the LLM's response to the Discord channel
            formatted_response = f"**{username}:** {message}\n**Response:** {llm_response}"
            await followup_message(inter.application_id, inter.token, formatted_response)

            # 6. Write the LLM's response to the transcript to complete the loop
            await repos.write_transcript(s, campaign.id, scene.id, channel_id, "bot", llm_response, str(user_id))
    elif name == "narrate":
        # Shadow-mode narrator using orchestrator (LLM JSON + rules). Behind llm feature flag.
        if not settings.features_llm or not llm_client:
            await followup_message(inter.application_id, inter.token, "❌ The LLM narrator is currently disabled.", ephemeral=True)
            return

        message = _option(inter, "message")
        if not message:
            await followup_message(inter.application_id, inter.token, "❌ You need to provide a message.", ephemeral=True)
            return

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)

        # Persist player's input first so it's part of the context facts builder
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(s, campaign.id, scene.id, channel_id, "player", message, str(user_id))
            scene_id = scene.id

        # Run the orchestrator (neutral sheet for now; extend to character sheets later)
        res = await run_orchestrator(scene_id=scene_id, player_msg=message, llm_client=llm_client)

        if res.rejected:
            text = f"🛑 Proposal rejected: {res.reason or 'invalid'}"
            await followup_message(inter.application_id, inter.token, text, ephemeral=True)
            return

        # Format mechanics + narration for Discord
        formatted = (
            f"🧪 Mechanics\n{res.mechanics}\n\n"
            f"📖 Narration\n{res.narration}"
        )
        await followup_message(inter.application_id, inter.token, formatted)

        # Log bot narration to transcript (non-blocking context open)
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(s, campaign.id, scene.id, channel_id, "bot", res.narration, str(user_id), meta={"mechanics": res.mechanics})
    else:
        await followup_message(inter.application_id, inter.token, f"Unknown command: {name}", ephemeral=True)

def _subcommand(inter: Interaction) -> str | None:
    # options[0].name for SUB_COMMAND
    if inter.data and inter.data.options:
        first = inter.data.options[0]
        if first.get("type") == 1:
            return first.get("name")
    return None

def _option(inter: Interaction, name: str, default=None):
    # If you’re inside a SUB_COMMAND, options are nested one level deeper
    opts = inter.data.options or []
    if opts and isinstance(opts[0], dict) and opts[0].get("type") == 1:
        opts = opts[0].get("options", [])
    for opt in opts or []:
        if opt.get("name") == name:
            return opt.get("value", default)
    return default

def _infer_ids_from_interaction(inter):
    guild_id = int(inter.guild.id) if inter.guild else 0
    channel_id = int(inter.channel.id) if inter.channel else 0
    user = inter.member.user if inter.member and inter.member.user else None
    user_id = int(user.id) if user else 0
    username = user.username if user else "Unknown"
    return guild_id, channel_id, user_id, username

async def _resolve_context(inter: Interaction):
    guild_id = int(inter.guild.id) if inter.guild else 0
    channel_id = int(inter.channel.id) if inter.channel else 0
    user = inter.member.user if inter.member and inter.member.user else None
    user_id = int(user.id) if user else 0
    username = user.username if user else "Unknown"

    # Discord Interaction payloads carry these in different places depending on type.
    # For slash commands: guild_id & channel_id are in "guild_id"/"channel" fields (add to schemas if needed).
    # For simplicity here, we assume you extended Interaction to include guild_id/channel.id/user.id
    # If not, adapt based on your actual payload.

    # TODO: parse from raw JSON fields in your Interaction model if missing.

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
        player = await repos.get_or_create_player(s, user_id, username)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(s, campaign.id, scene.id, channel_id, "player", "<user message>", str(user_id))
        return campaign, player, scene
