from pydantic import Field
from sqlalchemy import select

from Adventorator import models, repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter


class CancelOpts(Option):
    id: int | None = Field(default=None, description="Pending action id (optional)")


@slash_command(
    name="cancel",
    description="Cancel your most recent pending action.",
    option_model=CancelOpts,
)
async def cancel(inv: Invocation, opts: CancelOpts):
    settings = inv.settings
    if not settings or not getattr(settings, "features_executor", False):
        await inv.responder.send("Pending actions are disabled.", ephemeral=True)
        return

    user_id = str(inv.user_id or "0")
    channel_id = int(inv.channel_id or 0)
    guild_id = int(inv.guild_id or 0)

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        pa = None
        if opts.id is not None:
            q = await s.execute(
                select(models.PendingAction).where(models.PendingAction.id == opts.id)
            )
            pa = q.scalar_one_or_none()
        if pa is None:
            pa = await repos.get_latest_pending_for_user(s, scene_id=scene.id, user_id=user_id)
        if pa is None or pa.status != "pending":
            await inv.responder.send("No pending action to cancel.", ephemeral=True)
            inc_counter("pending.cancel.none")
            return
        await repos.mark_pending_action_status(s, pa.id, "canceled")
        # Mark the player's pending transcript as error to close it out
        if pa.player_tx_id:
            await repos.update_transcript_status(s, pa.player_tx_id, "error")
        await inv.responder.send("🛑 Canceled your pending action.")
        inc_counter("pending.cancel.ok")
