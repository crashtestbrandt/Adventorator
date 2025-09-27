from __future__ import annotations

from typing import Any, cast

from pydantic import Field
from sqlalchemy.exc import IntegrityError

from Adventorator import repos
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter
from Adventorator.orchestrator import run_orchestrator
from Adventorator.services.character_service import CharacterService


class DoOpts(Option):
    message: str = Field(description="Your action or narration message")


async def _handle_do_like(inv: Invocation, opts: DoOpts):
    settings = inv.settings
    llm = inv.llm_client if (settings and getattr(settings, "features_llm", False)) else None
    if not llm:
        await inv.responder.send(
            "❌ The narrator is disabled. Ask a GM to enable LLM features.",
            ephemeral=True,
        )
        return

    message = (opts.message or "").strip()
    if not message:
        await inv.responder.send("❌ You need to provide a message.", ephemeral=True)
        return
    if len(message) < 3 or message.lower() in {"y", "n", "yes", "no", "ok", "k"}:
        await inv.responder.send(
            "⚠️ Please provide a bit more detail so I can narrate.", ephemeral=True
        )
        return

    # Resolve scene context and persist player's input
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)

    player_tx_id = None
    bot_tx_id = None
    scene_id = None
    allowed: list[str] = []
    sheet_provider = None
    char_summary_provider = None
    # Resolve scene and write the player transcript within the same session
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        player_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "player",
            message,
            str(user_id),
            status="pending",
        )
        player_tx_id = getattr(player_tx, "id", None)
        scene_id = scene.id
        # Derive allowed actors from characters in this campaign
        # Allowed actors: include full names and their capitalized word tokens
        names = await repos.list_character_names(s, campaign.id)
        allowed = list(names)
        extra_tokens: set[str] = set()
        for nm in names:
            for part in str(nm).split():
                part = part.strip()
                if part and part[0].isalpha() and part[0].isupper():
                    extra_tokens.add(part)
        if extra_tokens:
            allowed.extend(sorted(extra_tokens))
        # Build a sheet provider from CharacterService for this user
        cs = CharacterService()
        sheet = await cs.get_active_sheet_info(
            s,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )
        if sheet is not None:
            # Map to the orchestrator's per-ability callable
            def _provider(ability: str):
                a = (ability or "").upper()
                score = int(sheet.abilities.get(a, 10))
                # Infer proficiency/expertise from skills if message hints at a skill
                txt = message.lower()
                # Map simple keywords -> canonical skill keys used by
                # CharacterService
                keyword_to_skill = {
                    "lockpick": "sleight of hand",
                    "pick lock": "sleight of hand",
                    "sneak": "stealth",
                    "hide": "stealth",
                    "move quietly": "stealth",
                    "climb": "athletics",
                    "jump": "athletics",
                    "convince": "persuasion",
                    "persuade": "persuasion",
                    "lie": "deception",
                    "deceive": "deception",
                    "recall lore": "history",
                    "recall": "history",
                    "notice": "perception",
                    "spot": "perception",
                    "search": "investigation",
                    "investigate": "investigation",
                }
                skill_key = None
                for k, skill_name in keyword_to_skill.items():
                    if k in txt:
                        skill_key = skill_name
                        break
                prof = False
                exp = False
                if skill_key and hasattr(sheet, "skills") and sheet.skills:
                    s_info = sheet.skills.get(skill_key)
                    if s_info:
                        prof = bool(s_info.get("proficient", False))
                        exp = bool(s_info.get("expertise", False))
                        # If the skill's governing ability differs and matches the
                        # requested, keep; otherwise just use the ability score
                        # above.
                return {
                    "score": score,
                    "proficient": prof,
                    "expertise": exp,
                    "prof_bonus": int(sheet.proficiency_bonus),
                }

            sheet_provider = _provider

            # Build a compact character summary for prompts
            def _summary() -> str:
                parts = [sheet.name]
                if sheet.class_name:
                    parts.append(str(sheet.class_name))
                if sheet.level:
                    parts.append(f"Lv {sheet.level}")
                # Include two key stats for brevity
                dex = sheet.abilities.get("DEX", 10)
                str_ = sheet.abilities.get("STR", 10)
                parts.append(f"STR {str_}, DEX {dex}, PB {sheet.proficiency_bonus}")
                return " ".join(str(p) for p in parts if p)

            char_summary_provider = _summary

    # Orchestrate
    try:
        # Prefer character identity for actor_id if available
        actor_id = str(user_id)
        try:
            if sheet is not None and getattr(sheet, "name", None):
                actor_id = str(sheet.name)
        except Exception:
            actor_id = str(user_id)
        res = await run_orchestrator(
            scene_id=scene_id or 0,
            player_msg=message,
            sheet_info_provider=sheet_provider,
            character_summary_provider=char_summary_provider,
            llm_client=llm,
            prompt_token_cap=getattr(settings, "llm_max_prompt_tokens", None) if settings else None,
            allowed_actors=allowed,
            settings=settings,
            actor_id=actor_id,
        )
    except Exception:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
        await inv.responder.send(
            "❌ Unexpected error while processing your action. Please try again.",
            ephemeral=True,
        )
        return

    if res.rejected:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
                # If an activity log was created during rejection (unlikely), link it
                if getattr(res, "activity_log_id", None):
                    try:
                        await repos.link_transcript_activity_log(
                            s,
                            transcript_id=player_tx_id,
                            activity_log_id=getattr(res, "activity_log_id", None),
                        )
                    except IntegrityError:
                        # Safe to ignore: activity log row not persisted yet; linkage is optional.
                        pass
        # Friendlier surface for known rejection reasons
        reason_key = (res.reason or "").lower()
        # Special-case unknown_actor:<names>
        if reason_key.startswith("unknown_actor"):
            names = (res.reason.split(":", 1)[1] if ":" in (res.reason or "") else "").strip()
            detail = f" ({names})" if names else ""
            readable = (
                "🛑 Narration referenced unknown characters" + detail + ". "
                "Use only your character or known NPCs in this scene."
            )
        else:
            readable = {
            "llm_invalid_or_empty": (
                "🛑 The narrator couldn't produce a structured preview. "
                "Try a simpler action or rephrase."
            ),
            "unsafe_verb": (
                "🛑 Action rejected for unsafe content. "
                "Describe what you attempt, not direct state changes."
            ),
            "unsupported action": "🛑 That action type isn't supported yet.",
            "unknown ability": "🛑 Unknown ability; use STR/DEX/CON/INT/WIS/CHA.",
            "dc out of acceptable range": "🛑 DC must be between 5 and 30.",
            "attacker/target required": "🛑 Attack needs both attacker and target.",
            "attack_bonus/target_ac required": "🛑 Provide attack_bonus and target_ac.",
            "attack_bonus out of range": "🛑 attack_bonus must be between -5 and 15.",
            "target_ac out of range": "🛑 target_ac must be between 5 and 30.",
            "damage spec required": "🛑 Missing damage dice (e.g., 1d6+2).",
            "damage.mod out of range": "🛑 Damage modifier must be between -5 and +10.",
            "damage.mod invalid": "🛑 Damage modifier must be a number.",
            "duration out of range": "🛑 Duration must be between 0 and 100.",
            "duration invalid": "🛑 Duration must be a number.",
            }.get(reason_key, f"🛑 Proposal rejected: {res.reason or 'invalid'}")
        await inv.responder.send(readable, ephemeral=True)
        inc_counter("pending.rejected")
        return

    # Pending actions flow: if enabled and a chain is present, persist PendingAction and
    # present confirmation instructions; leave transcripts in pending status.
    pending_enabled = bool(getattr(settings, "features_executor", False)) and bool(
        getattr(settings, "features_executor_confirm", True)
    )
    if pending_enabled and getattr(res, "chain_json", None):
        # Check if any step requires confirmation; else fall back to immediate output
        steps = list((res.chain_json or {}).get("steps", []))
        any_requires = any(bool(st.get("requires_confirmation")) for st in steps)
        if not any_requires:
            pending_enabled = False
    if pending_enabled and getattr(res, "chain_json", None):
        async with session_scope() as s:
            campaign = await repos.get_or_create_campaign(s, guild_id)
            scene = await repos.ensure_scene(s, campaign.id, channel_id)
            # Do not create bot transcript yet; we'll confirm it upon /confirm
            chain_json = cast(dict[str, Any], res.chain_json)
            pa = await repos.create_pending_action(
                s,
                campaign_id=campaign.id,
                scene_id=scene.id,
                channel_id=channel_id,
                user_id=str(user_id),
                request_id=chain_json.get("request_id", f"orc-{scene_id}"),
                chain=chain_json,
                mechanics=res.mechanics,
                narration=res.narration,
                player_tx_id=player_tx_id,
                bot_tx_id=None,
                activity_log_id=res.activity_log_id,
            )
            if player_tx_id is not None and getattr(res, "activity_log_id", None):
                try:
                    await repos.link_transcript_activity_log(
                        s,
                        transcript_id=player_tx_id,
                        activity_log_id=getattr(res, "activity_log_id", None),
                    )
                except IntegrityError:
                    pass
            await inv.responder.send(
                (
                    "🧪 Mechanics\n"
                    + res.mechanics
                    + "\n\n📖 Narration (pending)\n"
                    + res.narration
                    + f"\n\nConfirm with /confirm, or cancel with /cancel. [id {pa.id}]"
                ),
                ephemeral=not bool(getattr(settings, "features_llm_visible", False)),
            )
            inc_counter("pending.presented")
            return

    # Otherwise: legacy immediate output path
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        bot_tx = await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "bot",
            res.narration,
            str(user_id),
            meta={"mechanics": res.mechanics},
            status="pending",
            activity_log_id=res.activity_log_id,
        )
        bot_tx_id = getattr(bot_tx, "id", None)
        if player_tx_id is not None and getattr(res, "activity_log_id", None):
            await repos.link_transcript_activity_log(
                s,
                transcript_id=player_tx_id,
                activity_log_id=getattr(res, "activity_log_id", None),
            )

    # Attempt to send and mark statuses
    try:
        if settings and getattr(settings, "features_llm_visible", False):
            formatted = f"🧪 Mechanics\n{res.mechanics}\n\n📖 Narration\n{res.narration}"
            await inv.responder.send(formatted)
        else:
            await inv.responder.send(
                "Narrator ran in shadow mode (log-only). Ask a GM to enable visibility.",
                ephemeral=True,
            )
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "complete")
            if bot_tx_id is not None:
                await repos.update_transcript_status(s, bot_tx_id, "complete")
    except Exception:
        async with session_scope() as s:
            if player_tx_id is not None:
                await repos.update_transcript_status(s, player_tx_id, "error")
            if bot_tx_id is not None:
                await repos.update_transcript_status(s, bot_tx_id, "error")
        await inv.responder.send(
            "⚠️ Failed to deliver narration to the channel. Please try again.",
            ephemeral=True,
        )


@slash_command(name="do", description="Take an in-world action.", option_model=DoOpts)
async def do_command(inv: Invocation, opts: DoOpts):
    await _handle_do_like(inv, opts)
