# app.py

import asyncio
import json
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request

from Adventorator import repos
from Adventorator.config import load_settings
from Adventorator.crypto import verify_ed25519
from Adventorator.db import session_scope
from Adventorator.discord_schemas import Interaction
from Adventorator.llm import LLMClient
from Adventorator.logging import setup_logging
from Adventorator.orchestrator import run_orchestrator
from Adventorator.responder import followup_message, respond_deferred, respond_pong
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG
from Adventorator.schemas import CharacterSheet

rng = DiceRNG()  # TODO: Seed per-scene later

log = structlog.get_logger()
settings = load_settings()
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special for now
    try:
        yield
    finally:
        if llm_client:
            await llm_client.close()


app = FastAPI(title="Adventorator", lifespan=lifespan)

llm_client = None
if settings.features_llm:
    llm_client = LLMClient(settings)


DISCORD_SIG_HEADER = "X-Signature-Ed25519"
DISCORD_TS_HEADER = "X-Signature-Timestamp"


@app.post("/interactions")
async def interactions(request: Request):
    raw = await request.body()
    sig = request.headers.get(DISCORD_SIG_HEADER)
    ts = request.headers.get(DISCORD_TS_HEADER)
    if not sig or not ts:
        log.error("Missing signature headers", sig=sig, ts=ts)
        raise HTTPException(status_code=401, detail="missing signature headers")

    if not verify_ed25519(settings.discord_public_key, ts, raw, sig):
        log.error("Invalid signature", sig=sig, ts=ts)
        raise HTTPException(status_code=401, detail="bad signature")

    inter = Interaction.model_validate_json(raw)
    log.info("Interaction received", inter=inter)

    async with session_scope() as s:
        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
        campaign = await repos.get_or_create_campaign(s, guild_id)
        await repos.ensure_scene(s, campaign.id, channel_id)
        # Content can be reconstructed from command name/options; store a compact form:
        # msg = f"/{inter.data.name}" if inter.data and inter.data.name else "<interaction>"
        # await repos.write_transcript(
        #     s,
        #     campaign.id,
        #     scene.id,
        #     channel_id,
        #     "player",
        #     msg,
        #     str(user_id),
        #     meta=inter.model_dump(),
        # )

    # Ping = 1
    if inter.type == 1:
        return respond_pong()

    # Anything else: immediately DEFER (type 5) to satisfy the 3s budget.

    if inter.type == 2 and inter.data is not None and inter.data.name:
        asyncio.create_task(_dispatch_command(inter))
    return respond_deferred()


async def _dispatch_command(inter: Interaction):
    # Guard against data None (mypy)
    if inter.data is None:
        return
    name = inter.data.name

    if name == "sheet":
        sub = _subcommand(inter)
        if sub == "create":
            raw = _option(inter, "json")
            if raw is None or len(raw) > 16_000:
                await followup_message(
                    inter.application_id,
                    inter.token,
                    "❌ JSON missing or too large (16KB max).",
                    ephemeral=True,
                )
                return
            try:
                payload = json.loads(raw)
                sheet = CharacterSheet.model_validate(payload)
            except Exception as e:
                await followup_message(
                    inter.application_id,
                    inter.token,
                    f"❌ Invalid JSON or schema: {e}",
                    ephemeral=True,
                )
                return

            # Resolve context (guild/channel/user)
            guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
                player = await repos.get_or_create_player(s, user_id, username)
                await repos.ensure_scene(s, campaign.id, channel_id)

                await repos.upsert_character(s, campaign.id, player.id, sheet)
                await repos.write_transcript(
                    s,
                    campaign.id,
                    None,
                    channel_id,
                    "system",
                    "sheet.create",
                    str(user_id),
                    meta={"name": sheet.name},
                )

            await followup_message(
                inter.application_id, inter.token, f"✅ Sheet saved for **{sheet.name}**"
            )
            return

        elif sub == "show":
            who = _option(inter, "name")
            guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                found_char = await repos.get_character(s, campaign.id, who)
                if not found_char:
                    await followup_message(
                        inter.application_id,
                        inter.token,
                        f"❌ No character named **{who}**",
                        ephemeral=True,
                    )
                    return
                await repos.write_transcript(
                    s,
                    campaign.id,
                    None,
                    channel_id,
                    "system",
                    "sheet.show",
                    str(user_id),
                    meta={"name": who},
                )

            # present a compact summary
            assert found_char is not None
            sheet_dict = found_char.sheet  # stored as dict in DB
            summary = (
                f"**{sheet_dict['name']}** — {sheet_dict['class']} {sheet_dict['level']}\n"
                f"AC {sheet_dict['ac']} | "
                f"HP {sheet_dict['hp']['current']}/{sheet_dict['hp']['max']} | "
                f"STR {sheet_dict['abilities']['STR']} DEX {sheet_dict['abilities']['DEX']} "
                f"CON {sheet_dict['abilities']['CON']} INT {sheet_dict['abilities']['INT']} "
                f"WIS {sheet_dict['abilities']['WIS']} CHA {sheet_dict['abilities']['CHA']}"
            )
            await followup_message(inter.application_id, inter.token, summary, ephemeral=True)
            return

    if name == "roll":
        # expect option "expr"
        expr = _option(inter, "expr", default="1d20")
        adv = bool(_option(inter, "advantage", default=False))
        dis = bool(_option(inter, "disadvantage", default=False))
        roll_res = rng.roll(expr, advantage=adv, disadvantage=dis)
        text = (
            f"🎲 `{expr}` → rolls {roll_res.rolls} "
            f"{'(adv)' if adv else '(dis)' if dis else ''} = **{roll_res.total}**"
        )
        await followup_message(inter.application_id, inter.token, text)
        return
    elif name == "check":
        # options: ability, score, proficient, expertise, prof_bonus, dc, advantage, disadvantage
        ability = _option(inter, "ability", default="DEX").upper()
        score = int(_option(inter, "score", default=10))
        prof = bool(_option(inter, "proficient", default=False))
        exp = bool(_option(inter, "expertise", default=False))
        pb = int(_option(inter, "prof_bonus", default=2))
        dc = int(_option(inter, "dc", default=15))
        adv = bool(_option(inter, "advantage", default=False))
        dis = bool(_option(inter, "disadvantage", default=False))

        # d20 (1 or 2 rolls depending on adv/dis)
        res_roll = rng.roll("1d20", advantage=adv, disadvantage=dis)
        ci = CheckInput(
            ability=ability,
            score=score,
            proficient=prof,
            expertise=exp,
            proficiency_bonus=pb,
            dc=dc,
            advantage=adv,
            disadvantage=dis,
        )
        out = compute_check(
            ci, res_roll.rolls[:2] if len(res_roll.rolls) >= 2 else [res_roll.rolls[0]]
        )
        verdict = "✅ success" if out.success else "❌ fail"
        text = (
            f"🧪 **{ability}** check vs DC {dc}\n"
            f"• d20: {out.d20} → pick {out.pick}\n"
            f"• mod: {out.mod:+}\n"
            f"= **{out.total}** → {verdict}"
        )
        await followup_message(inter.application_id, inter.token, text)
    elif name == "ooc":
        # Shadow-mode orchestrator path; visibility gated by features_llm_visible
        if not settings.features_llm or not llm_client:
            await followup_message(
                inter.application_id,
                inter.token,
                "❌ The LLM narrator is currently disabled.",
                ephemeral=True,
            )
            return

        message = _option(inter, "message")
        if not message:
            await followup_message(
                inter.application_id,
                inter.token,
                "❌ You need to provide a message.",
                ephemeral=True,
            )
            return

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)

        # Persist player's input first so it's part of the context facts builder
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(
                s, campaign.id, scene.id, channel_id, "player", message, str(user_id)
            )
            scene_id = scene.id

        # Run the orchestrator (neutral sheet for now; extend to character sheets later)
        orc_res = await run_orchestrator(
            scene_id=scene_id, player_msg=message, llm_client=llm_client
        )

        if orc_res.rejected:
            # Polite ephemeral fallback in degraded mode
            await followup_message(
                inter.application_id,
                inter.token,
                "The narrator is silent for now. (LLM unavailable)",
                ephemeral=True,
            )
            return

        # Format mechanics + narration
        formatted = f"🧪 Mechanics\n{orc_res.mechanics}\n\n📖 Narration\n{orc_res.narration}"

        if settings.features_llm_visible:
            await followup_message(inter.application_id, inter.token, formatted)
        else:
            # Shadow mode: inform user minimally and avoid posting full content
            await followup_message(
                inter.application_id,
                inter.token,
                "(Narrator running in shadow mode)",
                ephemeral=True,
            )

        # Log bot narration to transcript (non-blocking context open)
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(
                s,
                campaign.id,
                scene.id,
                channel_id,
                "bot",
                orc_res.narration,
                str(user_id),
                meta={"mechanics": orc_res.mechanics},
            )
    elif name == "narrate":
        # Shadow-mode narrator using orchestrator (LLM JSON + rules). Behind llm feature flag.
        if not settings.features_llm or not llm_client:
            await followup_message(
                inter.application_id,
                inter.token,
                "❌ The LLM narrator is currently disabled.",
                ephemeral=True,
            )
            return

        message = _option(inter, "message")
        if not message:
            await followup_message(
                inter.application_id,
                inter.token,
                "❌ You need to provide a message.",
                ephemeral=True,
            )
            return

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)

        # Persist player's input first so it's part of the context facts builder
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(
                s, campaign.id, scene.id, channel_id, "player", message, str(user_id)
            )
            scene_id = scene.id

        # Run the orchestrator (neutral sheet for now; extend to character sheets later)
        orc_res = await run_orchestrator(
            scene_id=scene_id, player_msg=message, llm_client=llm_client
        )

        if orc_res.rejected:
            text = f"🛑 Proposal rejected: {orc_res.reason or 'invalid'}"
            await followup_message(inter.application_id, inter.token, text, ephemeral=True)
            return

        # Format mechanics + narration for Discord
        formatted = f"🧪 Mechanics\n{orc_res.mechanics}\n\n📖 Narration\n{orc_res.narration}"
        await followup_message(inter.application_id, inter.token, formatted)

        # Log bot narration to transcript (non-blocking context open)
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            await repos.write_transcript(
                s,
                campaign.id,
                scene.id,
                channel_id,
                "bot",
                orc_res.narration,
                str(user_id),
                meta={"mechanics": orc_res.mechanics},
            )
    else:
        await followup_message(
            inter.application_id, inter.token, f"Unknown command: {name}", ephemeral=True
        )


def _subcommand(inter: Interaction) -> str | None:
    # options[0].name for SUB_COMMAND
    if inter.data is not None and inter.data.options:
        first = inter.data.options[0]
        if first.get("type") == 1:
            return first.get("name")
    return None


def _option(inter: Interaction, name: str, default=None):
    # If you’re inside a SUB_COMMAND, options are nested one level deeper
    if inter.data is None:
        return default
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
    # For slash commands: guild_id & channel_id are in "guild_id"/"channel" fields
    # (add to schemas if needed).
    # For simplicity here, we assume you extended Interaction to include guild_id/channel.id/user.id
    # If not, adapt based on your actual payload.

    # TODO: parse from raw JSON fields in your Interaction model if missing.

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
        player = await repos.get_or_create_player(s, user_id, username)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(
            s, campaign.id, scene.id, channel_id, "player", "<user message>", str(user_id)
        )
        return campaign, player, scene
