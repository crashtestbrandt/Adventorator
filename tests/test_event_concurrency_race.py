import asyncio

import pytest

from Adventorator import repos


@pytest.mark.asyncio
async def test_concurrent_event_appends_dense_ordinals(db):
    camp = await repos.get_or_create_campaign(db, 42, name="Race")
    scene = await repos.ensure_scene(db, camp.id, 4200)

    async def worker(i: int):
        return await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id=f"c{i}",
            type="race",
            payload={"i": i},
            request_id=f"req-{i}",
        )

    # Launch a burst of concurrent appends
    tasks = [asyncio.create_task(worker(i)) for i in range(15)]
    results = await asyncio.gather(*tasks)

    # Fetch ordered events and verify dense replay ordinals 0..n-1
    evs = await repos.list_events(db, scene_id=scene.id)
    ordinals = [e.replay_ordinal for e in evs]
    assert ordinals == list(range(len(evs))), ordinals
    # Ensure we actually stored exactly the number requested
    assert len(evs) == len(results)
    # Uniqueness of idempotency keys across burst
    idempo_keys = {bytes(e.idempotency_key) for e in evs}
    assert len(idempo_keys) == len(evs)
