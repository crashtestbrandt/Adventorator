import logging

from pydantic import Field, ValidationError
from sqlalchemy import select

from Adventorator import models, repos
from Adventorator.action_validation import (
    ExecutionRequest,
    tool_chain_from_execution_request,
)
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter


logger = logging.getLogger(__name__)


class ConfirmOpts(Option):
    id: int | None = Field(default=None, description="Pending action id (optional)")


@slash_command(
    name="confirm",
    description="Confirm your most recent pending action.",
    option_model=ConfirmOpts,
)
async def confirm(inv: Invocation, opts: ConfirmOpts):
    settings = inv.settings
    if (
        not settings
        or not getattr(settings, "features_executor", False)
        or not getattr(settings, "features_executor_confirm", True)
    ):
        await inv.responder.send("Pending actions are disabled.", ephemeral=True)
        return

    user_id = str(inv.user_id or "0")
    channel_id = int(inv.channel_id or 0)
    guild_id = int(inv.guild_id or 0)

    # Resolve latest pending in this scene for the user
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        pa = None
        if opts.id is not None:
            # Fetch specific id if provided
            q = await s.execute(
                select(models.PendingAction).where(models.PendingAction.id == opts.id)
            )
            pa = q.scalar_one_or_none()
        if pa is None:
            pa = await repos.get_latest_pending_for_user(s, scene_id=scene.id, user_id=user_id)
            if pa is None or pa.status != "pending":
                await inv.responder.send("No pending action to confirm.", ephemeral=True)
                inc_counter("pending.confirm.none")
                return
        # Apply chain via executor
        try:
            from Adventorator.executor import Executor, ToolCallChain, ToolStep

            chain_payload = pa.chain or {}
            chain: ToolCallChain | None = None

            if (
                settings
                and getattr(settings, "features_action_validation", False)
                and isinstance(chain_payload, dict)
            ):
                req_payload = chain_payload.get("execution_request")
                if isinstance(req_payload, dict):
                    try:
                        req = ExecutionRequest.model_validate(req_payload)
                    except ValidationError:
                        inc_counter("pending.confirm.execution_request.invalid")
                        logger.warning(
                            "Invalid execution_request payload on pending action id=%s", pa.id
                        )
                    else:
                        chain = tool_chain_from_execution_request(req)

            if chain is None:
                steps = []
                for st in (chain_payload.get("steps") or []):
                    steps.append(
                        ToolStep(
                            tool=st.get("tool"),
                            args=st.get("args", {}),
                            requires_confirmation=bool(
                                st.get("requires_confirmation", False)
                            ),
                            visibility=str(st.get("visibility", "ephemeral")),
                        )
                    )
                chain = ToolCallChain(
                    request_id=chain_payload.get("request_id", pa.request_id),
                    scene_id=int(chain_payload.get("scene_id", pa.scene_id)),
                    steps=steps,
                    actor_id=chain_payload.get("actor_id") or user_id,
                )
            elif not chain.actor_id:
                chain = ToolCallChain(
                    request_id=chain.request_id,
                    scene_id=chain.scene_id,
                    steps=chain.steps,
                    actor_id=chain_payload.get("actor_id") or user_id,
                )

            ex = Executor()
            await ex.apply_chain(chain)
            # Write bot transcript and mark complete
            await repos.write_transcript(
                s,
                campaign.id,
                scene.id,
                channel_id,
                "bot",
                pa.narration,
                user_id,
                meta={"mechanics": pa.mechanics},
                status="complete",
            )
            if pa.player_tx_id:
                await repos.update_transcript_status(s, pa.player_tx_id, "complete")
            await repos.mark_pending_action_status(s, pa.id, "confirmed")
            await inv.responder.send(
                f"✅ Confirmed.\n🧪 Mechanics\n{pa.mechanics}\n\n📖 Narration\n{pa.narration}"
            )
            inc_counter("pending.confirm.ok")
        except Exception:
            await repos.mark_pending_action_status(s, pa.id, "error")
            await inv.responder.send("❌ Failed to apply action.", ephemeral=True)
            inc_counter("pending.confirm.error")
