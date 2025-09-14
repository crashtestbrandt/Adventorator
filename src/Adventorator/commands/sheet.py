# src/Adventorator/commands/sheet.py
import json

from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.schemas import CharacterSheet
from Adventorator.services.character_service import CharacterService


class SheetCreateOpts(Option):
    # Use alias 'json' to avoid shadowing BaseModel.json while keeping CLI/API stable
    payload: str = Field(alias="json", description="Character sheet JSON payload (<=16KB)")


class SheetShowOpts(Option):
    name: str = Field(description="Character name to display")


@slash_command(
    name="sheet",
    subcommand="create",
    description="Create or update a character sheet.",
    option_model=SheetCreateOpts,
)
async def sheet_create(inv: Invocation, opts: SheetCreateOpts):
    raw = opts.payload
    if raw is None or len(raw) > 16_000:
        await inv.responder.send("❌ JSON missing or too large (16KB max).", ephemeral=True)
        return
    try:
        payload = json.loads(raw)
        sheet = CharacterSheet.model_validate(payload)
    except Exception as e:
        await inv.responder.send(f"❌ Invalid JSON or schema: {e}", ephemeral=True)
        return

    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
        player = await repos.get_or_create_player(s, user_id, f"user-{user_id}")
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

    await inv.responder.send(f"✅ Sheet saved for **{sheet.name}**")


@slash_command(
    name="sheet",
    subcommand="show",
    description="Show a character sheet summary.",
    option_model=SheetShowOpts,
)
async def sheet_show(inv: Invocation, opts: SheetShowOpts):
    who = (opts.name or "").strip()
    if not who:
        await inv.responder.send("❌ You must provide a character name.", ephemeral=True)
        return

    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        cs = CharacterService()
        sheet = await cs.get_sheet_by_name(s, campaign_id=campaign.id, name=who)
        if not sheet:
            await inv.responder.send(f"❌ No character named **{who}**", ephemeral=True)
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

    # Preserve existing summary format; fill minimal fields from SheetInfo
    # Note: AC/HP aren't in SheetInfo; keep placeholders if not available in DB sheet structure.
    name = sheet.name
    cls = sheet.class_name or "?"
    lvl = sheet.level or "?"
    # Attempt to pull AC/HP if present via repos.get_character would have used raw JSON.
    # For now, display abilities-centric summary consistently.
    summary = (
        f"**{name}** — {cls} {lvl}\n"
        f"STR {sheet.abilities.get('STR', 10)} DEX {sheet.abilities.get('DEX', 10)} "
        f"CON {sheet.abilities.get('CON', 10)} INT {sheet.abilities.get('INT', 10)} "
        f"WIS {sheet.abilities.get('WIS', 10)} CHA {sheet.abilities.get('CHA', 10)}"
    )
    await inv.responder.send(summary, ephemeral=True)
