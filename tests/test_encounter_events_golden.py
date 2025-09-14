import pytest

from Adventorator import repos
from Adventorator.config import Settings
from Adventorator.db import session_scope
from Adventorator.executor import Executor, ToolCallChain, ToolStep


@pytest.mark.asyncio
async def test_encounter_events_golden(db, monkeypatch):
    """End-to-end executor apply emits deterministic events in correct order."""
    # Enable events + combat
    settings = Settings(features_events=True, features_combat=True)
    monkeypatch.setattr("Adventorator.executor.load_settings", lambda: settings, raising=True)

    # Prep a scene id
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id=123)
        scene = await repos.ensure_scene(s, campaign.id, channel_id=456)
        scene_id = scene.id

    ex = Executor()

    # Start encounter
    chain = ToolCallChain(
        request_id="r1",
        scene_id=scene_id,
        steps=[
            ToolStep(tool="start_encounter", args={"scene_id": scene_id}),
        ],
    )
    await ex.apply_chain(chain)

    # Add two combatants A, B
    # Lookup encounter id for adds
    async with session_scope() as s:
        enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene_id)
        assert enc is not None
        encounter_id = enc.id

    chain2 = ToolCallChain(
        request_id="r2",
        scene_id=scene_id,
        steps=[
            ToolStep(
                tool="add_combatant",
                args={"encounter_id": encounter_id, "name": "A", "hp": 0},
            ),
            ToolStep(
                tool="add_combatant",
                args={"encounter_id": encounter_id, "name": "B", "hp": 0},
            ),
        ],
    )
    await ex.apply_chain(chain2)

    # Set initiatives A=15, B=12 -> encounter becomes active and advances to first
    # Need combatant ids
    async with session_scope() as s:
        cbs = await repos.list_combatants(s, encounter_id=encounter_id)
        # order_idx preserves insertion; match names
        by_name = {c.name: c for c in cbs}
        a_id = by_name["A"].id
        b_id = by_name["B"].id

    chain3 = ToolCallChain(
        request_id="r3",
        scene_id=scene_id,
        steps=[
            ToolStep(
                tool="set_initiative",
                args={
                    "encounter_id": encounter_id,
                    "combatant_id": a_id,
                    "initiative": 15,
                },
            ),
            ToolStep(
                tool="set_initiative",
                args={
                    "encounter_id": encounter_id,
                    "combatant_id": b_id,
                    "initiative": 12,
                },
            ),
        ],
    )
    await ex.apply_chain(chain3)

    # Next turn once
    chain4 = ToolCallChain(
        request_id="r4",
        scene_id=scene_id,
        steps=[ToolStep(tool="next_turn", args={"encounter_id": encounter_id})],
    )
    await ex.apply_chain(chain4)

    # Collect recent events and assert golden sequence by type
    async with session_scope() as s:
        evs = await repos.list_events(s, scene_id=scene_id, limit=20)
        types = [e.type for e in evs]

    # We expect at least in order:
    #  encounter.started
    #  combatant.added (A)
    #  combatant.added (B)
    #  combatant.initiative_set (A)
    #  combatant.initiative_set (B)
    #  encounter.advanced (first turn)
    #  encounter.advanced (next turn)
    expected = [
        "encounter.started",
        "combatant.added",
        "combatant.added",
        "combatant.initiative_set",
        "combatant.initiative_set",
        "encounter.advanced",
        "encounter.advanced",
    ]

    # types contains other executor events as well; check subsequence ordering
    pos = 0
    for t in types:
        if pos < len(expected) and t == expected[pos]:
            pos += 1
    assert pos == len(expected), f"Missing sequence; got: {types}"
