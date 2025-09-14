import pytest

from Adventorator import repos
from Adventorator.db import session_scope


@pytest.mark.asyncio
async def test_hp_fold_damage_and_heal(db):
    guild_id = 2001
    channel_id = 2002
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        # Append events directly
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="apply_damage",
            payload={"target": "char-a", "amount": 8},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="heal",
            payload={"target": "char-a", "amount": 3},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="apply_damage",
            payload={"target": "char-b", "amount": 5},
        )
        evs = await repos.list_events(s, scene_id=scene.id)
        hp = repos.fold_hp_view(evs)
        assert hp == {"char-a": -5, "char-b": -5}


@pytest.mark.asyncio
async def test_conditions_fold_apply_and_remove(db):
    guild_id = 2011
    channel_id = 2012
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="condition.applied",
            payload={"target": "char-a", "condition": "poisoned", "duration": 10},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="condition.applied",
            payload={"target": "char-a", "condition": "poisoned"},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="condition.removed",
            payload={"target": "char-a", "condition": "poisoned"},
        )
        evs = await repos.list_events(s, scene_id=scene.id)
        conds = repos.fold_conditions_view(evs)
        assert "char-a" in conds
        assert "poisoned" in conds["char-a"]
        slot = conds["char-a"]["poisoned"]
        assert slot["stacks"] == 1
        assert slot["duration"] == 10


@pytest.mark.asyncio
async def test_conditions_fold_clear(db):
    guild_id = 2031
    channel_id = 2032
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="condition.applied",
            payload={"target": "char-a", "condition": "blinded", "duration": 5},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="condition.cleared",
            payload={"target": "char-a", "condition": "blinded"},
        )
        evs = await repos.list_events(s, scene_id=scene.id)
        conds = repos.fold_conditions_view(evs)
        slot = conds["char-a"]["blinded"]
        assert slot["stacks"] == 0
        assert slot["duration"] is None


@pytest.mark.asyncio
async def test_initiative_fold_replay(db):
    guild_id = 2021
    channel_id = 2022
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="initiative.set",
            payload={"order": [{"id": "char-a", "init": 12}, {"id": "char-b", "init": 15}]},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="initiative.update",
            payload={"id": "char-a", "init": 18},
        )
        await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id="gm",
            type="initiative.remove",
            payload={"id": "char-b"},
        )
        evs = await repos.list_events(s, scene_id=scene.id)
        order = repos.fold_initiative_view(evs)
        assert order == [("char-a", 18)]
