import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from Adventorator import models, repos
from Adventorator.events import envelope as event_envelope


@pytest.mark.asyncio
async def test_genesis_event_matches_expected_hashes(db):
    campaign = await repos.get_or_create_campaign(db, 99, name="Story Campaign")
    genesis = event_envelope.GenesisEvent(campaign_id=campaign.id).instantiate()
    db.add(genesis)
    await db.flush()

    assert genesis.replay_ordinal == 0
    assert genesis.prev_event_hash == event_envelope.GENESIS_PREV_EVENT_HASH
    assert genesis.payload_hash == event_envelope.GENESIS_PAYLOAD_HASH
    assert genesis.payload == {}
    assert genesis.idempotency_key == event_envelope.GENESIS_IDEMPOTENCY_KEY

    row = await db.get(models.Event, genesis.id)
    assert row is not None
    assert row.prev_event_hash == event_envelope.GENESIS_PREV_EVENT_HASH
    assert row.payload_hash == event_envelope.GENESIS_PAYLOAD_HASH


@pytest.mark.asyncio
async def test_replay_ordinal_trigger_enforces_dense_sequence(db):
    campaign = await repos.get_or_create_campaign(db, 101, name="Trigger Test")
    scene = await repos.ensure_scene(db, campaign.id, 4242)

    genesis = event_envelope.GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.flush()

    payload = {"kind": "demo"}
    genesis_envelope_hash = event_envelope.compute_envelope_hash(
        campaign_id=genesis.campaign_id,
        scene_id=genesis.scene_id,
        replay_ordinal=genesis.replay_ordinal,
        event_type=genesis.type,
        event_schema_version=genesis.event_schema_version,
        world_time=genesis.world_time,
        wall_time_utc=genesis.wall_time_utc,
        prev_event_hash=genesis.prev_event_hash,
        payload_hash=genesis.payload_hash,
        idempotency_key=genesis.idempotency_key,
    )
    gap_event = models.Event(
        campaign_id=campaign.id,
        scene_id=scene.id,
        replay_ordinal=genesis.replay_ordinal + 2,
        type="test.event",
        event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
        world_time=genesis.replay_ordinal + 2,
        prev_event_hash=genesis_envelope_hash,
        payload_hash=event_envelope.compute_payload_hash(payload),
        idempotency_key=event_envelope.compute_idempotency_key(
            campaign_id=campaign.id,
            event_type="test.event",
            execution_request_id="req-1",
            plan_id=None,
            payload=payload,
            replay_ordinal=genesis.replay_ordinal + 2,
        ),
        actor_id=None,
        plan_id=None,
        execution_request_id="req-1",
        approved_by=None,
        payload=payload,
        migrator_applied_from=None,
    )
    db.add(gap_event)
    with pytest.raises((IntegrityError, OperationalError)):
        await db.flush()
