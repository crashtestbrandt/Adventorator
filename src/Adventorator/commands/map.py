from __future__ import annotations

from pydantic import Field

from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.config import load_settings
from Adventorator.responder import followup_message_with_attachment
from Adventorator.services.renderer import RenderInput, render_map
from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.models import EncounterStatus


class MapShowOpts(Option):
    verbose: bool = Field(default=False, description="Include debug info about cache/encounter")
    demo: bool = Field(
        default=False, description="Render a demo map without requiring an encounter"
    )


@slash_command(
    name="map",
    subcommand="show",
    description="Render and show the current encounter map (FF-gated)",
    option_model=MapShowOpts,
)
async def map_show(inv: Invocation, opts: MapShowOpts):
    settings = inv.settings or load_settings()
    if not getattr(settings, "features_map", False):
        await inv.responder.send(
            "🗺️ Map rendering is disabled (features.map=false).",
            ephemeral=True,
        )
        return

    # Demo mode: render a sample grid/tokens without DB state
    if getattr(opts, "demo", False):
        from Adventorator.services.renderer import Token

        tokens = [
            Token(name="Ari", x=1, y=1, color=(64, 128, 255), active=True),
            Token(name="Bor", x=3, y=2, color=(80, 200, 120), active=False),
            Token(name="Cat", x=2, y=4, color=(220, 120, 120), active=False),
        ]
        rinp = RenderInput(
            encounter_id=-1, last_event_id=None, width=512, height=384, tokens=tokens
        )
    else:
        # Real encounter rendering
        guild_id = int(inv.guild_id or 0)
        channel_id = int(inv.channel_id or 0)
        # Defaults before DB
        rinp: RenderInput | None = None
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
            # Require an active encounter for non-demo rendering
            if not enc or getattr(enc, "status", None) != EncounterStatus.active:
                await inv.responder.send(
                    "⚠️ No active encounter for this scene. Try /map show demo:true or start combat.",
                    ephemeral=True,
                )
                return
            # List and order combatants; derive simple grid positions
            cbs = await repos.list_combatants(s, encounter_id=enc.id)
            ordered = repos.sort_initiative_order(cbs)
            # Build tokens: PCs (character_id set) get blue-ish; others red-ish
            from Adventorator.services.renderer import Token

            def _clamp(v: int, lo: int, hi: int) -> int:
                return max(lo, min(hi, v))

            grid_size = 10
            tokens: list[Token] = []
            active_idx = int(getattr(enc, "active_idx", 0) or 0)
            for i, cb in enumerate(ordered):
                gx = i % grid_size
                gy = i // grid_size
                color = (64, 128, 255) if getattr(cb, "character_id", None) else (220, 120, 120)
                is_active = i == active_idx
                tokens.append(
                    Token(
                        name=str(getattr(cb, "name", f"C{i + 1}")),
                        x=_clamp(gx, 0, grid_size - 1),
                        y=_clamp(gy, 0, grid_size - 1),
                        color=color,
                        active=is_active,
                    )
                )
            last_event_id = await repos.get_latest_event_id_for_scene(s, scene_id=scene.id)
            rinp = RenderInput(
                encounter_id=int(getattr(enc, "id", 0) or 0),
                last_event_id=last_event_id,
                width=512,
                height=384,
                tokens=tokens,
            )
    # Safety: type checker guard
    assert rinp is not None
    png = render_map(rinp)

    # If running under real Discord responder, it provides application_id/token
    app_id = getattr(inv.responder, "application_id", None)
    token = getattr(inv.responder, "token", None)
    webhook_base = getattr(inv.responder, "webhook_base_url", None)
    sent_as = "fallback-text"
    if app_id and token:
        await followup_message_with_attachment(
            application_id=app_id,
            token=token,
            content="Encounter Map (image attached)",
            filename="map.png",
            file_bytes=png,
            ephemeral=False,
            settings=settings,
            webhook_base_url=webhook_base,
            # Only allow settings-based webhook override (dev sink) for dev CLI requests
            allow_settings_override=getattr(inv.responder, "dev_request", False),
        )
        sent_as = "attachment"
    else:
        # In tests or non-discord responders, fall back to a simple text reply
        await inv.responder.send("Encounter Map (attachment unsupported in this environment)")
        sent_as = "text"

    if getattr(opts, "verbose", False):
        size = len(png or b"")
        fallback = "yes" if size <= 100 else "no"
        await inv.responder.send(
            f"debug: sent_as={sent_as} png_bytes={size} tiny_fallback={fallback}",
            ephemeral=True,
        )
