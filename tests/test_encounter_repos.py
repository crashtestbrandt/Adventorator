import pytest

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.models import EncounterStatus


@pytest.mark.asyncio
async def test_encounter_repos_ordering_and_initiative():
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=12345, name="TestGuild")
        scene = await repos.ensure_scene(s, campaign_id=camp.id, channel_id=999)
        enc = await repos.create_encounter(s, scene_id=scene.id)

        # Add combatants in insertion order; no initiatives yet
        a = await repos.add_combatant(s, encounter_id=enc.id, name="Alice")
        b = await repos.add_combatant(s, encounter_id=enc.id, name="Bob")
        c = await repos.add_combatant(s, encounter_id=enc.id, name="Cora")

        assert [
            x.order_idx for x in await repos.list_combatants(s, encounter_id=enc.id)
        ] == [0, 1, 2]

        # Set initiatives with a tie between Bob and Cora, ensuring stable tiebreak by order_idx
        await repos.set_combatant_initiative(s, combatant_id=a.id, initiative=15)
        await repos.set_combatant_initiative(s, combatant_id=b.id, initiative=12)
        await repos.set_combatant_initiative(s, combatant_id=c.id, initiative=12)

        ordered = repos.sort_initiative_order(await repos.list_combatants(s, encounter_id=enc.id))
        # Expect Alice (15) first, then Bob (12, order_idx 1), then Cora (12, order_idx 2)
        assert [x.name for x in ordered] == ["Alice", "Bob", "Cora"]


@pytest.mark.asyncio
async def test_encounter_repos_state_updates():
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=12346, name="TG2")
        scene = await repos.ensure_scene(s, campaign_id=camp.id, channel_id=1000)
        enc = await repos.create_encounter(s, scene_id=scene.id)
        assert enc.status == EncounterStatus.setup
        await repos.update_encounter_state(
            s,
            encounter_id=enc.id,
            status=EncounterStatus.active.value,
            round=2,
            active_idx=1,
        )
        enc2 = await repos.get_encounter_by_id(s, encounter_id=enc.id)
        assert enc2 is not None
        assert enc2.status == EncounterStatus.active
        assert enc2.round == 2
        assert enc2.active_idx == 1
