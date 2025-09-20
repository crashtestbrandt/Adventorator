# src/Adventorator/commands/check.py
import structlog
from pydantic import Field

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.config import load_settings
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter
from Adventorator.rules.checks import CheckInput
from Adventorator.services.character_service import CharacterService

log = structlog.get_logger()


class CheckOpts(Option):
    ability: str = Field(default="DEX", description="Ability (e.g., STR, DEX)")
    score: int = Field(default=10, description="Ability score (e.g., 10)")
    proficient: bool = Field(default=False, description="Proficient in this check")
    expertise: bool = Field(default=False, description="Expertise applies (double prof)")
    prof_bonus: int = Field(default=2, description="Proficiency bonus")
    dc: int = Field(default=15, description="Difficulty Class")
    advantage: bool = Field(default=False, description="Roll with advantage")
    disadvantage: bool = Field(default=False, description="Roll with disadvantage")


@slash_command(
    name="check",
    description="Make an ability check with options.",
    option_model=CheckOpts,
)
async def check_command(inv: Invocation, opts: CheckOpts):
    ability = (opts.ability or "DEX").upper()
    score = opts.score
    prof_bonus = opts.prof_bonus
    proficient = opts.proficient
    expertise = opts.expertise

    # If score/proficiency flags or prof bonus not provided explicitly,
    # try to default from the active character
    need_sheet = (score in (None, 0, 10) and not opts.proficient and not opts.expertise) or (
        prof_bonus in (None, 0, 2)
    )
    if need_sheet:
        async with session_scope() as s:
            cs = CharacterService()
            sheet = await cs.get_active_sheet_info(
                s,
                user_id=int(inv.user_id or 0),
                guild_id=int(inv.guild_id or 0) if inv.guild_id else 0,
                channel_id=int(inv.channel_id or 0) if inv.channel_id else 0,
            )
        if sheet is not None:
            # Override score and prof bonus from sheet
            score = int(sheet.abilities.get(ability, score))
            prof_bonus = int(sheet.proficiency_bonus or prof_bonus)
            # If a commonly mapped skill implies proficiency/expertise, respect it.
            # Try to infer skill name from ability if possible (no direct mapping here),
            # so leave flags unless the user set them explicitly. If both flags are false,
            # keep them as False; detailed skill flags are handled in /do via narrator flow.

    ci = CheckInput(
        ability=ability,
        score=int(score),
        proficient=bool(proficient),
        expertise=bool(expertise),
        proficiency_bonus=int(prof_bonus),
        dc=int(opts.dc),
        advantage=bool(opts.advantage),
        disadvantage=bool(opts.disadvantage),
    )
    if inv.ruleset is None:
        from Adventorator.rules.engine import Dnd5eRuleset

        rs = Dnd5eRuleset()
    else:
        rs = inv.ruleset
    out = rs.perform_check(ci)
    verdict = "✅ success" if out.success else "❌ fail"
    text = (
        f"🧪 **{ability}** check vs DC {opts.dc}\n"
        f"• d20: {out.d20} → pick {out.pick}\n"
        f"• mod: {out.mod:+}\n"
        f"= **{out.total}** → {verdict}"
    )
    settings = inv.settings or load_settings()
    await inv.responder.send(text)

    # Phase 9: append event when enabled
    if getattr(settings, "features_events", False):
        try:
            guild_id = int(inv.guild_id or 0)
            channel_id = int(inv.channel_id or 0)
            user_id = str(inv.user_id)
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                scene = await repos.ensure_scene(s, campaign.id, channel_id)
                payload = {
                    "ability": ability,
                    "score": int(score),
                    "proficient": bool(proficient),
                    "expertise": bool(expertise),
                    "proficiency_bonus": int(prof_bonus),
                    "dc": int(opts.dc),
                    "d20": list(out.d20),
                    "pick": int(out.pick),
                    "mod": int(out.mod),
                    "total": int(out.total),
                    "success": bool(out.success),
                    "text": text,
                }
                await repos.append_event(
                    s,
                    scene_id=scene.id,
                    actor_id=user_id,
                    type="check.performed",
                    payload=payload,
                    request_id=None,
                )
        except Exception:
            # Keep non-fatal during rollout
            pass

    if getattr(settings, "features_activity_log", False):
        try:
            try:
                guild_id = int(inv.guild_id or 0)
            except (TypeError, ValueError):
                inc_counter("activity_log.failed")
                log.warning(
                    "activity_log.write_failed",
                    command="check",
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
                    command="check",
                    reason="invalid_channel_id",
                    channel_id=inv.channel_id,
                )
                return
            async with session_scope() as s:
                campaign = await repos.get_or_create_campaign(s, guild_id)
                scene = await repos.ensure_scene(s, campaign.id, channel_id)
                payload = {
                    "ability": ability,
                    "score": int(score),
                    "proficient": bool(proficient),
                    "expertise": bool(expertise),
                    "proficiency_bonus": int(prof_bonus),
                    "dc": int(opts.dc),
                    "advantage": bool(opts.advantage),
                    "disadvantage": bool(opts.disadvantage),
                    "d20": list(out.d20),
                    "pick": int(out.pick),
                    "mod": int(out.mod),
                    "total": int(out.total),
                    "success": bool(out.success),
                    "text": text,
                }
                await repos.create_activity_log(
                    s,
                    campaign_id=campaign.id,
                    scene_id=scene.id,
                    actor_ref=str(inv.user_id) if inv.user_id is not None else None,
                    event_type="mechanics.check",
                    summary=f"{ability} check vs DC {opts.dc}",
                    payload=payload,
                    correlation_id=None,
                    request_id=None,
                )
        except Exception:
            inc_counter("activity_log.failed")
            log.warning("activity_log.write_failed", command="check", exc_info=True)
