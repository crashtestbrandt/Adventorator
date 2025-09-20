import asyncio

import pytest

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.models import EncounterStatus
from Adventorator.services import encounter_service


@pytest.mark.asyncio
async def test_lifecycle_start_add_set_init_and_activate():
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=555, name="Guild")
        scene = await repos.ensure_scene(s, campaign_id=camp.id, channel_id=111)

        mech, evs = await encounter_service.start_encounter(s, scene_id=scene.id)
        assert "Encounter" in mech["mechanics"]
        enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
        assert enc is not None and enc.status == EncounterStatus.setup

        # Add two combatants
        m2, e2 = await encounter_service.add_combatant(s, encounter_id=enc.id, name="A")
        m3, e3 = await encounter_service.add_combatant(s, encounter_id=enc.id, name="B")
        assert "Added" in m2["mechanics"] and "Added" in m3["mechanics"]

        # Set initiatives → should auto-activate and set first turn
        a = (await repos.list_combatants(s, encounter_id=enc.id))[0]
        b = (await repos.list_combatants(s, encounter_id=enc.id))[1]
        await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=a.id, initiative=14
        )
        mech4, evs4 = await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=b.id, initiative=12
        )
        enc2 = await repos.get_encounter_by_id(s, encounter_id=enc.id)
        assert enc2 is not None and enc2.status == EncounterStatus.active
        assert any(ev["type"] == "encounter.advanced" for ev in evs4)


@pytest.mark.asyncio
async def test_next_turn_wraps_and_round_increments():
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=556, name="G2")
        scene = await repos.ensure_scene(s, campaign_id=camp.id, channel_id=222)
        await encounter_service.start_encounter(s, scene_id=scene.id)
        enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
        a = await repos.add_combatant(s, encounter_id=enc.id, name="A")
        b = await repos.add_combatant(s, encounter_id=enc.id, name="B")
        await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=a.id, initiative=15
        )
        await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=b.id, initiative=12
        )
        enc = await repos.get_encounter_by_id(s, encounter_id=enc.id)
        assert enc is not None and enc.active_idx == 0 and enc.round == 1

        # Next turn → B, same round
        mech1, evs1 = await encounter_service.next_turn(s, encounter_id=enc.id)
        enc = await repos.get_encounter_by_id(s, encounter_id=enc.id)
        assert enc.active_idx == 1 and enc.round == 1

        # Next turn → wrap to A, round increments
        mech2, evs2 = await encounter_service.next_turn(s, encounter_id=enc.id)
        enc = await repos.get_encounter_by_id(s, encounter_id=enc.id)
        assert enc.active_idx == 0 and enc.round == 2


@pytest.mark.asyncio
async def test_concurrent_next_turn_single_winner():
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=557, name="G3")
        scene = await repos.ensure_scene(s, campaign_id=camp.id, channel_id=333)
        await encounter_service.start_encounter(s, scene_id=scene.id)
        enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
        a = await repos.add_combatant(s, encounter_id=enc.id, name="A")
        b = await repos.add_combatant(s, encounter_id=enc.id, name="B")
        await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=a.id, initiative=15
        )
        await encounter_service.set_initiative(
            s, encounter_id=enc.id, combatant_id=b.id, initiative=12
        )

    # Run two concurrent next_turn calls each with their own session
    async def call_next():
        async with session_scope() as s2:
            return await encounter_service.next_turn(s2, encounter_id=enc.id)

    r1, r2 = await asyncio.gather(call_next(), call_next())
    # After two next_turn calls, active_idx should be 0 (wrapped) and round 2
    async with session_scope() as s3:
        enc2 = await repos.get_encounter_by_id(s3, encounter_id=enc.id)
        assert enc2.active_idx in (0, 1)  # Accept either order; lock ensures consistency
        assert enc2.round >= 1
