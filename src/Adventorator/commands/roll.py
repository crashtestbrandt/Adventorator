# src/Adventorator/commands/roll.py
import structlog
from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.config import load_settings
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter

log = structlog.get_logger()


class RollOpts(Option):
    expr: str = Field(default="1d20", description="Dice expression")
    advantage: bool = Field(default=False, description="Roll with advantage")
    disadvantage: bool = Field(default=False, description="Roll with disadvantage")


@slash_command(
    name="roll",
    description="Roll dice (e.g., 2d6+3).",
    option_model=RollOpts,
    # you could include Discord-only metadata here too
)
async def roll(inv: Invocation, opts: RollOpts):
    # Prefer injected ruleset; fallback to default if not provided (tests/CLI)
    if inv.ruleset is None:
        from Adventorator.rules.engine import Dnd5eRuleset

        rs = Dnd5eRuleset()
    else:
        rs = inv.ruleset
    res = rs.roll_dice(
        opts.expr or "1d20",
        advantage=opts.advantage,
        disadvantage=opts.disadvantage,
    )
    suffix = "(adv)" if opts.advantage else "(dis)" if opts.disadvantage else ""
    text = f"🎲 `{opts.expr}` → rolls {res.rolls} {suffix} = **{res.total}**"
    settings = inv.settings or load_settings()
    await inv.responder.send(text)

    # Phase 9: append an audit event for the roll when enabled
    if getattr(settings, "features_events", False):
        try:
            guild_id = int(inv.guild_id or 0)
            channel_id = int(inv.channel_id or 0)
            user_id = str(inv.user_id)
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                scene = await repos.ensure_scene(s, campaign.id, channel_id)
                payload = {
                    "expr": opts.expr or "1d20",
                    "rolls": list(res.rolls),
                    "total": int(res.total),
                    "advantage": bool(opts.advantage),
                    "disadvantage": bool(opts.disadvantage),
                    "text": text,
                }
                await repos.append_event(
                    s,
                    scene_id=scene.id,
                    actor_id=user_id,
                    type="roll.performed",
                    payload=payload,
                    request_id=None,
                )
        except Exception:
            # Never fail the command on ledger errors in Phase 9 rollout
            pass

    if getattr(settings, "features_activity_log", False):
        try:
            try:
                guild_id = int(inv.guild_id or 0)
            except (TypeError, ValueError):
                inc_counter("activity_log.failed")
                log.warning(
                    "activity_log.write_failed",
                    command="roll",
                    reason="invalid_guild_id",
                    guild_id=inv.guild_id,
                )
                return
            try:
                channel_id = int(inv.channel_id or 0)
            except (TypeError, ValueError):
                inc_counter("activity_log.failed")
                log.warning(
                    "activity_log.write_failed",
                    command="roll",
                    reason="invalid_channel_id",
                    channel_id=inv.channel_id,
                )
                return
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                scene = await repos.ensure_scene(s, campaign.id, channel_id)
                payload = {
                    "expression": opts.expr or "1d20",
                    "rolls": list(res.rolls),
                    "total": int(res.total),
                    "advantage": bool(opts.advantage),
                    "disadvantage": bool(opts.disadvantage),
                    "text": text,
                }
                await repos.create_activity_log(
                    s,
                    campaign_id=campaign.id,
                    scene_id=scene.id,
                    actor_ref=str(inv.user_id) if inv.user_id is not None else None,
                    event_type="mechanics.roll",
                    summary=f"Roll {opts.expr or '1d20'}",
                    payload=payload,
                    correlation_id=None,
                    request_id=None,
                )
        except Exception:
            inc_counter("activity_log.failed")
            log.warning("activity_log.write_failed", command="roll", exc_info=True)
