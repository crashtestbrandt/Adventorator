from __future__ import annotations

from datetime import datetime, timezone

from Adventorator import repos
from Adventorator.commanding import Invocation, slash_command
from Adventorator.db import session_scope


def _fmt_pending(pa) -> str:
    created = (
        pa.created_at.replace(tzinfo=timezone.utc)
        if pa.created_at.tzinfo is None
        else pa.created_at
    )
    now = datetime.now(timezone.utc)
    age_s = int((now - created).total_seconds())
    ttl = None
    if pa.expires_at is not None:
        ttl = int((pa.expires_at - now).total_seconds())
    ttl_str = f" ttl {ttl}s" if ttl is not None else ""
    mech = (pa.mechanics or "").splitlines()[0] if pa.mechanics else ""
    nar = (pa.narration or "").splitlines()[0] if pa.narration else ""
    return f"[{pa.id}] age {age_s}s{ttl_str} | {mech} | {nar}"


@slash_command(name="pending", description="List your pending actions in this scene.")
async def pending(inv: Invocation):
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = str(inv.user_id or "")

    if not user_id or not channel_id or not guild_id:
        await inv.responder.send("❌ Missing context.", ephemeral=True)
        return

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        # For now, just get the latest pending; can be expanded to list many
        pa = await repos.get_latest_pending_for_user(s, scene_id=scene.id, user_id=user_id)

    if not pa:
        await inv.responder.send("No pending action found.", ephemeral=True)
        return

    await inv.responder.send(_fmt_pending(pa), ephemeral=True)
