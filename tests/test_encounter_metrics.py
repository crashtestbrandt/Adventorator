import pytest

from Adventorator import repos
from Adventorator.metrics import get_counter, get_counters, reset_counters
from Adventorator.models import EncounterStatus


@pytest.mark.asyncio
async def test_next_turn_metrics_ok(db):
    reset_counters()
    # Setup: encounter with two combatants, initiatives set, active
    # Satisfy FKs by creating campaign and scene first
    camp = await repos.get_or_create_campaign(db, guild_id=901, name="M1")
    scene = await repos.ensure_scene(db, campaign_id=camp.id, channel_id=902)
    enc = await repos.create_encounter(db, scene_id=scene.id)
    await repos.add_combatant(db, encounter_id=enc.id, name="A")
    await repos.add_combatant(db, encounter_id=enc.id, name="B")
    cbs = await repos.list_combatants(db, encounter_id=enc.id)
    await repos.set_combatant_initiative(db, combatant_id=cbs[0].id, initiative=15)
    await repos.set_combatant_initiative(db, combatant_id=cbs[1].id, initiative=10)
    # Transition to active
    await repos.update_encounter_state(
        db, encounter_id=enc.id, status=EncounterStatus.active.value, round=1, active_idx=0
    )

    # Exercise next_turn
    from Adventorator.services import encounter_service

    mech, evs = await encounter_service.next_turn(db, encounter_id=enc.id)
    assert "Round" in mech["mechanics"]
    assert any(ev.get("type") == "encounter.advanced" for ev in evs)

    # Metrics
    assert get_counter("encounter.next_turn.ok") == 1
    counters = get_counters()
    assert counters.get("histo.encounter.next_turn.ms.count") == 1


@pytest.mark.asyncio
async def test_add_and_set_initiative_metrics(db):
    reset_counters()
    camp = await repos.get_or_create_campaign(db, guild_id=903, name="M2")
    scene = await repos.ensure_scene(db, campaign_id=camp.id, channel_id=904)
    enc = await repos.create_encounter(db, scene_id=scene.id)
    from Adventorator.services import encounter_service
    mech, evs = await encounter_service.add_combatant(db, encounter_id=enc.id, name="Rogue")
    assert get_counter("encounter.add.ok") == 1

    cbs = await repos.list_combatants(db, encounter_id=enc.id)
    mech, evs = await encounter_service.set_initiative(
        db, encounter_id=enc.id, combatant_id=cbs[0].id, initiative=12
    )
    assert get_counter("encounter.initiative_set.ok") == 1
