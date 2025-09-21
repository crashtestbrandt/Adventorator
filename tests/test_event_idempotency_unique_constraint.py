import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from Adventorator import models, repos
from Adventorator.events import envelope as event_envelope


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected(db):
    """HR-001: Ensure (campaign_id, idempotency_key) uniqueness constraint enforced.

    We create two events with identical idempotency key material for the same campaign
    but different ordinals to provoke a UNIQUE violation. The second flush should fail.
    """
    campaign = await repos.get_or_create_campaign(db, 1234, name="Idem Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 9001)

    genesis = event_envelope.GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.flush()

    # Build a payload & deterministic idempotency key we will intentionally reuse.
    payload = {"kind": "dup-test"}
    common_key = event_envelope.compute_idempotency_key(
        campaign_id=campaign.id,
        event_type="test.event",
        execution_request_id="req-dup",
        plan_id=None,
        payload=payload,
        replay_ordinal=genesis.replay_ordinal + 1,
    )

    first = models.Event(
        campaign_id=campaign.id,
        scene_id=scene.id,
        replay_ordinal=genesis.replay_ordinal + 1,
        type="test.event",
        event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
        world_time=genesis.replay_ordinal + 1,
        prev_event_hash=genesis.payload_hash,
        payload_hash=event_envelope.compute_payload_hash(payload),
        idempotency_key=common_key,
        actor_id=None,
        plan_id=None,
        execution_request_id="req-dup",
        approved_by=None,
        payload=payload,
        migrator_applied_from=None,
    )
    db.add(first)
    await db.flush()

    # Second event intentionally tries to reuse idempotency_key (violation expected)
    second = models.Event(
        campaign_id=campaign.id,
        scene_id=scene.id,
        replay_ordinal=genesis.replay_ordinal + 2,
        type="test.event",
        event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
        world_time=genesis.replay_ordinal + 2,
        prev_event_hash=first.payload_hash,
        payload_hash=event_envelope.compute_payload_hash(payload),
        idempotency_key=common_key,  # REUSE
        actor_id=None,
        plan_id=None,
        execution_request_id="req-dup",
        approved_by=None,
        payload=payload,
        migrator_applied_from=None,
    )
    db.add(second)
    with pytest.raises((IntegrityError, OperationalError)):
        await db.flush()
