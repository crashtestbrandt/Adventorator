"""Minimal CharacterService: resolve active character and provide sheet info.

This is a light abstraction to keep handlers/orchestrator decoupled from repos.
We aim to return only what mechanics need: ability scores, proficiency bonus,
and a couple of identity fields for LLM summaries.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from Adventorator import models


@dataclass(frozen=True)
class SheetInfo:
    name: str
    class_name: str | None
    level: int | None
    # Simple mechanics slice
    abilities: dict[str, int]  # raw ability scores (STR/DEX/CON/INT/WIS/CHA)
    proficiency_bonus: int
    # Normalized skill proficiency map: key -> {proficient: bool, expertise: bool, ability: str}
    skills: dict[str, dict[str, Any]]


class CharacterService:
    """Resolve a user's active character in a guild/channel and expose sheet info."""

    # very small in-process TTL cache: key -> (expires_at, SheetInfo)
    _cache: dict[tuple[int, int], tuple[float, SheetInfo]] = {}
    # name lookup cache: (campaign_id, lower_name) -> (expires_at, SheetInfo)
    _name_cache: dict[tuple[int, str], tuple[float, SheetInfo]] = {}
    _ttl_seconds: int = 30

    @classmethod
    def configure_cache_ttl(cls, seconds: int) -> None:
        cls._ttl_seconds = max(0, int(seconds))

    async def get_active_sheet_info(
        self,
        session,
        *,
        user_id: int | str,
        guild_id: int | str | None,
        channel_id: int | str | None,
    ) -> SheetInfo | None:
        # Convert to canonical types
        uid = int(user_id) if user_id is not None else 0
        # guild and channel are reserved for future scoping

        # Strategy: pick a character by heuristic since there is no explicit API yet.
        # 1) Try to resolve the Player by discord_user_id and pick any character in the campaign.
        # Cache check (keyed by user and a shared namespace 0 for now)
        cache_key = (uid, 0)
        now = time.time()
        if cache_key in self._cache:
            exp, cached = self._cache[cache_key]
            if now <= exp:
                return cached
            else:
                # expired
                try:
                    del self._cache[cache_key]
                except KeyError:
                    pass

        try:
            q = await session.execute(
                select(models.Player).where(models.Player.discord_user_id == uid)
            )
            player = q.scalar_one_or_none()
            char = None
            if player is not None:
                # Pick the most recently updated character for this player.
                stmt = select(models.Character).where(
                    models.Character.player_id == player.id
                ).order_by(models.Character.updated_at.desc())
                cq = await session.execute(stmt)
                char = cq.scalars().first()
            if char is None:
                return None
        except Exception:
            return None

        # Character model may store the sheet as JSON (schema aligned with Pydantic v2 aliasing)
        # Build a compact view with sensible defaults.
        sheet: dict[str, Any] = char.sheet or {}
        abilities = {}
        for key in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            # Support lowercase keys in sheet as well
            src = sheet.get("abilities", {})
            abilities[key] = int(src.get(key, src.get(key.lower(), 10)))

        # Proficiency bonus: derive from sheet if present, else default to 2
        prof = sheet.get("proficiency_bonus")
        try:
            prof_bonus = int(prof) if prof is not None else 2
        except Exception:
            prof_bonus = 2

        name = char.name or "Unnamed"
        class_name = (
            sheet.get("class_name")
            or sheet.get("class")
            or (sheet.get("identity", {}) or {}).get("class_name")
        )
        level = sheet.get("level") or (sheet.get("identity", {}) or {}).get("level")
        try:
            lvl = int(level) if level is not None else None
        except Exception:
            lvl = None

        # Normalize skills from various potential shapes in the sheet
        skills: dict[str, dict[str, Any]] = {}
        raw_skills = sheet.get("skills") or {}
        # Common mapping skill -> canonical key and default governing ability
        skill_to_ability = {
            "acrobatics": "DEX",
            "animal handling": "WIS",
            "animal_handling": "WIS",
            "arcana": "INT",
            "athletics": "STR",
            "deception": "CHA",
            "history": "INT",
            "insight": "WIS",
            "intimidation": "CHA",
            "investigation": "INT",
            "medicine": "WIS",
            "nature": "INT",
            "perception": "WIS",
            "performance": "CHA",
            "persuasion": "CHA",
            "religion": "INT",
            "sleight of hand": "DEX",
            "sleight_of_hand": "DEX",
            "stealth": "DEX",
            "survival": "WIS",
        }

        def _canon_skill_key(k: str) -> str:
            k = (k or "").strip().lower().replace("-", " ")
            # unify spaces/underscores
            k = k.replace("_", " ")
            return k

        if isinstance(raw_skills, dict):
            for k, v in raw_skills.items():
                ck = _canon_skill_key(str(k))
                base = {
                    "proficient": False,
                    "expertise": False,
                    "ability": skill_to_ability.get(ck, "DEX"),
                }
                try:
                    if isinstance(v, dict):
                        prof = bool(v.get("proficient", v.get("prof", v.get("p", False))))
                        exp = bool(v.get("expertise", v.get("x", False)))
                    else:
                        # If value is boolean, treat as proficient only
                        prof = bool(v)
                        exp = False
                except Exception:
                    prof = False
                    exp = False
                base["proficient"] = prof
                base["expertise"] = exp
                skills[ck] = base

        sheet_info = SheetInfo(
            name=name,
            class_name=class_name if isinstance(class_name, str) else None,
            level=lvl,
            abilities=abilities,
            proficiency_bonus=prof_bonus,
            skills=skills,
        )

        # populate cache
        try:
            self._cache[cache_key] = (now + self._ttl_seconds, sheet_info)
        except Exception:
            pass

        return sheet_info

    async def get_sheet_by_name(
        self, session, *, campaign_id: int, name: str
    ) -> SheetInfo | None:
        """Lookup a character by name in a campaign and return SheetInfo (cached)."""
        try:
            cache_key = (int(campaign_id), (name or "").strip().lower())
            now = time.time()
            if cache_key in self._name_cache:
                exp, cached = self._name_cache[cache_key]
                if now <= exp:
                    return cached
                else:
                    try:
                        del self._name_cache[cache_key]
                    except Exception:
                        pass
            stmt = select(models.Character).where(
                models.Character.campaign_id == int(campaign_id),
                models.Character.name == name,
            )
            q = await session.execute(stmt)
            char = q.scalars().first()
            if not char:
                return None
            sheet = char.sheet or {}
            abilities = {}
            for abbr in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
                src = sheet.get("abilities", {})
                abilities[abbr] = int(src.get(abbr, src.get(abbr.lower(), 10)))
            prof_bonus = int(sheet.get("proficiency_bonus", 2) or 2)
            class_name = sheet.get("class_name") or sheet.get("class")
            level = sheet.get("level")
            skills = {}
            raw_skills = sheet.get("skills") or {}
            if isinstance(raw_skills, dict):
                for k, v in raw_skills.items():
                    ck = str(k).strip().lower().replace("_", " ")
                    try:
                        prof = bool(v.get("proficient", False)) if isinstance(v, dict) else bool(v)
                        exp = bool(v.get("expertise", False)) if isinstance(v, dict) else False
                    except Exception:
                        prof = False
                        exp = False
                    skills[ck] = {"proficient": prof, "expertise": exp}
            info = SheetInfo(
                name=char.name or name,
                class_name=class_name if isinstance(class_name, str) else None,
                level=int(level) if isinstance(level, int) else None,
                abilities=abilities,
                proficiency_bonus=prof_bonus,
                skills=skills,
            )
            try:
                self._name_cache[cache_key] = (now + self._ttl_seconds, info)
            except Exception:
                pass
            return info
        except Exception:
            return None
