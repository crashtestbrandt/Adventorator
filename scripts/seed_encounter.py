#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.db import session_scope
from Adventorator import repos
from Adventorator.models import EncounterStatus

GUILD_ID = 1
CHANNEL_ID = 1

async def main() -> None:
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, GUILD_ID)
        scene = await repos.ensure_scene(s, campaign.id, CHANNEL_ID)
        enc = await repos.create_encounter(s, scene_id=scene.id)
        # Add a few combatants
        a = await repos.add_combatant(s, encounter_id=enc.id, name="Ari", character_id=None, hp=10)
        b = await repos.add_combatant(s, encounter_id=enc.id, name="Goblin", character_id=None, hp=7)
        c = await repos.add_combatant(s, encounter_id=enc.id, name="Orc", character_id=None, hp=15)
        # Set initiatives
        await repos.set_combatant_initiative(s, combatant_id=a.id, initiative=15)
        await repos.set_combatant_initiative(s, combatant_id=b.id, initiative=12)
        await repos.set_combatant_initiative(s, combatant_id=c.id, initiative=8)
        # Activate encounter
        await repos.update_encounter_state(s, encounter_id=enc.id, status=EncounterStatus.active.value, round=1, active_idx=0)
        print(f"Seeded encounter {enc.id} with 3 combatants in scene {scene.id}.")

if __name__ == "__main__":
    asyncio.run(main())
