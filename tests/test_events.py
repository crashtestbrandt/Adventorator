from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from Adventorator import models, repos
from Adventorator.events import (
    GENESIS_PAYLOAD_HASH,
    GENESIS_PREVIOUS_HASH,
    compute_idempotency_key,
    compute_payload_hash,
    ensure_genesis_event,
)


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
    assert e1.replay_ordinal == 1
    assert e2.replay_ordinal == 2
    assert e2.prev_event_hash == e1.payload_hash

    events = await repos.list_events(db, scene_id=scene.id)
    assert [e.id for e in events] == [e1.id, e2.id]


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected(db):
    camp = await repos.get_or_create_campaign(db, 1, name="Dup Test")
    scene = await repos.ensure_scene(db, camp.id, 200)

    await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="actor",
        type="test",
        payload={"foo": "bar"},
        request_id="same",
    )

    with pytest.raises(IntegrityError):
        await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id="actor",
            type="test",
            payload={"foo": "bar"},
            request_id="same",
        )
    await db.rollback()


@pytest.mark.asyncio
async def test_replay_ordinal_trigger_enforces_dense(db):
    camp = await repos.get_or_create_campaign(db, 1, name="Trigger")
    scene = await repos.ensure_scene(db, camp.id, 300)
    genesis = await ensure_genesis_event(db, campaign_id=camp.id)

    rogue = models.Event(
        campaign_id=camp.id,
        scene_id=scene.id,
        replay_ordinal=2,
        event_type="test",
        event_schema_version=1,
        world_time=2,
        wall_time_utc=datetime.now(timezone.utc),
        prev_event_hash=bytes(genesis.payload_hash),
        payload_hash=compute_payload_hash({"foo": 1}),
        idempotency_key=compute_idempotency_key(
            campaign_id=camp.id,
            event_type="test",
            payload={"foo": 1},
            execution_request_id="rogue",
        ),
        actor_id=None,
        plan_id=None,
        execution_request_id="rogue",
        approved_by=None,
        payload={"foo": 1},
        migrator_applied_from=None,
    )
    db.add(rogue)
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_genesis_event_has_expected_hash(db):
    camp = await repos.get_or_create_campaign(db, 1, name="Genesis")

    genesis = await ensure_genesis_event(db, campaign_id=camp.id)
    assert genesis.replay_ordinal == 0
    assert genesis.prev_event_hash == GENESIS_PREVIOUS_HASH
    assert genesis.payload_hash == GENESIS_PAYLOAD_HASH

    again = await ensure_genesis_event(db, campaign_id=camp.id)
    assert genesis.event_id == again.event_id


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
