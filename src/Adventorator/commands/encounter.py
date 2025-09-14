# src/Adventorator/commands/encounter.py
from __future__ import annotations

from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.config import load_settings
from Adventorator.db import session_scope


class EncounterStatusOpts(Option):
    # Reserved for future filters (e.g., include_ended). Currently no options.
    verbose: bool = Field(default=False, description="Show extra debug fields")


def _format_status(
    *,
    status: str,
    round_num: int,
    active_idx: int | None,
    combatants: list[tuple[int | None, str, int | None]],
    verbose: bool = False,
) -> str:
    # Header
    hdr = f"📊 Encounter status: {status}"
    if round_num:
        hdr += f" — round {round_num}"
    lines: list[str] = [hdr]

    # Initiative table
    if combatants:
        lines.append("\nInitiative order:")
        for i, (cid, name, initv) in enumerate(combatants):
            mark = "➡️" if (active_idx is not None and i == active_idx) else "  "
            iv = "-" if initv is None else str(initv)
            extra = f" (id={cid})" if verbose else ""
            lines.append(f"{mark} {iv:>2} — {name}{extra}")
    else:
        lines.append("\n(no combatants)")

    return "\n".join(lines)


@slash_command(
    name="encounter",
    subcommand="status",
    description="Show the current encounter status and initiative order.",
    option_model=EncounterStatusOpts,
)
async def encounter_status(inv: Invocation, opts: EncounterStatusOpts):
    settings = inv.settings or load_settings()
    if not getattr(settings, "features_combat", False):
        await inv.responder.send(
            "⚠️ Combat features disabled (features.combat=false)", ephemeral=True
        )
        return

    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)

    async with session_scope() as s:
        # Resolve scene for this channel
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)

        enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
        if not enc:
            await inv.responder.send("No encounter in this scene.")
            return

        # Gather and sort combatants deterministically
        cbs = await repos.list_combatants(s, encounter_id=enc.id)
        ordered = repos.sort_initiative_order(cbs)
        rows: list[tuple[int | None, str, int | None]] = [
            (getattr(cb, "id", None), getattr(cb, "name", "?"), getattr(cb, "initiative", None))
            for cb in ordered
        ]

        text = _format_status(
            status=str(getattr(enc, "status", "?")),
            round_num=int(getattr(enc, "round", 0) or 0),
            active_idx=getattr(enc, "active_idx", None),
            combatants=rows,
            verbose=bool(opts.verbose),
        )

    await inv.responder.send(text)
