"""Minimal CharacterService: resolve active character and provide sheet info.

This is a light abstraction to keep handlers/orchestrator decoupled from repos.
We aim to return only what mechanics need: ability scores, proficiency bonus,
and a couple of identity fields for LLM summaries.
"""
from __future__ import annotations

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


class CharacterService:
    """Resolve a user's active character in a guild/channel and expose sheet info."""

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
        level = (
            sheet.get("level")
            or (sheet.get("identity", {}) or {}).get("level")
        )
        try:
            lvl = int(level) if level is not None else None
        except Exception:
            lvl = None

        return SheetInfo(
            name=name,
            class_name=class_name if isinstance(class_name, str) else None,
            level=lvl,
            abilities=abilities,
            proficiency_bonus=prof_bonus,
        )
