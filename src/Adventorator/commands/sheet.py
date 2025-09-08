# src/Adventorator/commands/sheet.py
import json

from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.schemas import CharacterSheet


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
        ch = await repos.get_character(s, campaign.id, who)
        if not ch:
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

    sheet_dict = ch.sheet  # type: ignore[attr-defined]
    summary = (
        f"**{sheet_dict['name']}** — {sheet_dict['class']} {sheet_dict['level']}\n"
        f"AC {sheet_dict['ac']} | HP {sheet_dict['hp']['current']}/{sheet_dict['hp']['max']} | "
        f"STR {sheet_dict['abilities']['STR']} DEX {sheet_dict['abilities']['DEX']} "
        f"CON {sheet_dict['abilities']['CON']} INT {sheet_dict['abilities']['INT']} "
        f"WIS {sheet_dict['abilities']['WIS']} CHA {sheet_dict['abilities']['CHA']}"
    )
    await inv.responder.send(summary, ephemeral=True)
