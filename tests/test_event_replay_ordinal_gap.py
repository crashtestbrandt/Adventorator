import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from Adventorator import models, repos
from Adventorator.events import envelope as event_envelope


@pytest.mark.asyncio
async def test_replay_ordinal_gap_rejected(db):
    """Ensure trigger rejects non-dense replay_ordinal (gap)."""
    camp = await repos.get_or_create_campaign(db, 555, name="Gap")
    scene = await repos.ensure_scene(db, camp.id, 5550)
    # Insert genesis via helper
    genesis = event_envelope.GenesisEvent(campaign_id=camp.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.flush()

    # Attempt to insert event skipping ordinal 1 -> using 2 directly
    payload = {"gap": True}
    ev = models.Event(
        campaign_id=camp.id,
        scene_id=scene.id,
        replay_ordinal=2,  # should be 1
        type="gap.test",
        event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
        world_time=2,
        prev_event_hash=genesis.payload_hash,
        payload_hash=event_envelope.compute_payload_hash(payload),
        idempotency_key=event_envelope.compute_idempotency_key(
            campaign_id=camp.id,
            event_type="gap.test",
            execution_request_id="req-gap",
            plan_id=None,
            payload=payload,
            replay_ordinal=2,
        ),
        actor_id=None,
        plan_id=None,
        execution_request_id="req-gap",
        approved_by=None,
        payload=payload,
        migrator_applied_from=None,
    )
    db.add(ev)
    with pytest.raises((IntegrityError, OperationalError)):
        await db.flush()
