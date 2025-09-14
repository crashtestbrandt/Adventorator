import pytest

from Adventorator import repos


@pytest.mark.asyncio
async def test_append_and_list_events(db):
    # Setup a campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Test")
    scene = await repos.ensure_scene(db, camp.id, 100)

    # Append a couple events
    e1 = await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="c1",
        type="apply_damage",
        payload={"target": "c2", "amount": 3},
        request_id="r1",
    )
    e2 = await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="c1",
        type="heal",
        payload={"target": "c2", "amount": 1},
        request_id="r2",
    )

    assert e1.id < e2.id

    events = await repos.list_events(db, scene_id=scene.id)
    assert [e.id for e in events] == [e1.id, e2.id]


def test_fold_hp_view():
    class E:
        def __init__(self, type, payload):
            self.type = type
            self.payload = payload

    events = [
        E("apply_damage", {"target": "c2", "amount": 3}),
        E("heal", {"target": "c2", "amount": 1}),
        E("apply_damage", {"target": "c3", "amount": 2}),
    ]
    hp = repos.fold_hp_view(events)
    assert hp == {"c2": -2, "c3": -2}
