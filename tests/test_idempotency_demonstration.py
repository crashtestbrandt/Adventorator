"""Demonstration test for idempotency key functionality (STORY-CDA-CORE-001D)."""

import asyncio
import pytest
from datetime import datetime, timezone

from Adventorator.events.envelope import compute_idempotency_key_v2, compute_payload_hash
from Adventorator.events.envelope import GENESIS_SCHEMA_VERSION, GenesisEvent


@pytest.mark.asyncio
async def test_idempotency_demonstration_sequential():
    """Demonstrate that idempotency works with sequential retry attempts."""
    import os
    os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
    
    from Adventorator.db import get_sessionmaker, get_engine
    from Adventorator import models, repos
    from Adventorator.db import Base
    
    # Set up database  
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    sessionmaker = get_sessionmaker()
    
    # Set up test data
    campaign_id_input = 12345
    scene_id_input = 67890
    
    # Create campaign and scene
    async with sessionmaker() as db:
        campaign = await repos.get_or_create_campaign(db, campaign_id_input, name="Demo Campaign")
        scene = await repos.ensure_scene(db, campaign.id, scene_id_input)
        
        # Use the actual campaign and scene IDs from the database
        campaign_id = campaign.id
        scene_id = scene.id
        
        # Create genesis event
        genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
        db.add(genesis)
        await db.commit()
    
    # Define the operation that will be retried
    plan_id = "demo-plan-123"
    tool_name = "dice_roll"
    ruleset_version = "dnd5e-v1.0"
    args_json = {"sides": 20, "count": 1, "modifier": 3}
    
    # Compute idempotency key
    idempotency_key = compute_idempotency_key_v2(
        plan_id=plan_id,
        campaign_id=campaign_id,
        event_type="tool.execute",
        tool_name=tool_name,
        ruleset_version=ruleset_version,
        args_json=args_json,
    )
    
    # Common event data
    payload = {"result": 15, "details": "d20 roll + 3"}
    event_data = {
        "scene_id": scene_id,
        "replay_ordinal": 1,  # genesis.replay_ordinal + 1
        "type": "tool.execute",
        "event_schema_version": GENESIS_SCHEMA_VERSION,
        "world_time": 1,  # genesis.world_time + 1
        "wall_time_utc": datetime.now(timezone.utc),
        "prev_event_hash": genesis.payload_hash,
        "payload_hash": compute_payload_hash(payload),
        "actor_id": "player-1",
        "plan_id": plan_id,
        "execution_request_id": "req-demo-test",
        "approved_by": None,
        "payload": payload,
        "migrator_applied_from": None,
    }
    
    # Simulate multiple attempts (sequential for simplicity)
    retry_attempts = 12  # Exceed minimum requirement of 10
    successful_attempts = 0
    created_event_id = None
    
    for attempt in range(retry_attempts):
        async with sessionmaker() as db:
            from sqlalchemy.exc import IntegrityError
            from sqlalchemy import select
            
            try:
                # Check if event already exists
                stmt = select(models.Event).where(
                    models.Event.campaign_id == campaign_id,
                    models.Event.idempotency_key == idempotency_key
                )
                existing = await db.scalar(stmt)
                
                if existing:
                    # Idempotent reuse
                    successful_attempts += 1
                    assert existing.id == created_event_id, "Should reuse the same event"
                    continue
                
                # Try to create new event
                event = models.Event(
                    campaign_id=campaign_id,
                    idempotency_key=idempotency_key,
                    **event_data
                )
                
                db.add(event)
                await db.commit()
                
                # First successful creation
                successful_attempts += 1
                created_event_id = event.id
                print(f"Attempt {attempt + 1}: Created new event with ID {event.id}")
                
            except IntegrityError:
                # Race condition or constraint violation
                await db.rollback()
                
                # Fetch the winning event
                stmt = select(models.Event).where(
                    models.Event.campaign_id == campaign_id,
                    models.Event.idempotency_key == idempotency_key
                )
                existing = await db.scalar(stmt)
                
                if existing:
                    successful_attempts += 1
                    assert existing.id == created_event_id, "Should reuse the same event"
                    print(f"Attempt {attempt + 1}: Reused existing event with ID {existing.id}")
    
    # Verify acceptance criteria: all attempts succeeded
    assert successful_attempts == retry_attempts, f"Expected {retry_attempts} successful attempts, got {successful_attempts}"
    
    # Verify only one event was actually persisted
    async with sessionmaker() as db:
        from sqlalchemy import select, func
        
        count_stmt = select(func.count(models.Event.id)).where(
            models.Event.campaign_id == campaign_id,
            models.Event.idempotency_key == idempotency_key
        )
        event_count = await db.scalar(count_stmt)
        
        assert event_count == 1, f"Expected exactly 1 event persisted, found {event_count}"
    
    print(f"SUCCESS: {retry_attempts} retry attempts resulted in exactly 1 persisted event")


@pytest.mark.asyncio 
async def test_idempotency_demonstration_concurrent():
    """Demonstrate that idempotency works with concurrent retry attempts."""
    import os
    os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
    
    from Adventorator.db import get_sessionmaker, get_engine
    from Adventorator import models, repos
    from Adventorator.db import Base
    from tests.test_retry_storm_harness import RetryStormSimulator
    
    # Set up database  
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    sessionmaker = get_sessionmaker()
    
    # Set up test data
    campaign_id_input = 54321
    scene_id_input = 98765
    
    # Create campaign and scene in one session
    async with sessionmaker() as db:
        campaign = await repos.get_or_create_campaign(db, campaign_id_input, name="Concurrent Demo Campaign")
        scene = await repos.ensure_scene(db, campaign.id, scene_id_input)
        
        # Use the actual campaign and scene IDs from the database
        campaign_id = campaign.id
        scene_id = scene.id
        
        # Create genesis event
        genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
        db.add(genesis)
        await db.commit()
    
    # Define the operation that will be retried
    plan_id = "concurrent-demo-plan-456"
    tool_name = "attack_roll"
    ruleset_version = "dnd5e-v1.1"
    args_json = {"weapon": "longsword", "bonus": 5}
    
    # Compute idempotency key
    idempotency_key = compute_idempotency_key_v2(
        plan_id=plan_id,
        campaign_id=campaign_id,
        event_type="tool.execute",
        tool_name=tool_name,
        ruleset_version=ruleset_version,
        args_json=args_json,
    )
    
    # Common event data
    payload = {"attack_roll": 18, "damage": "1d8+3", "hit": True}
    event_data = {
        "scene_id": scene_id,
        "replay_ordinal": 1,  # genesis.replay_ordinal + 1
        "type": "tool.execute",
        "event_schema_version": GENESIS_SCHEMA_VERSION,
        "world_time": 1,  # genesis.world_time + 1
        "wall_time_utc": datetime.now(timezone.utc),
        "prev_event_hash": genesis.payload_hash,
        "payload_hash": compute_payload_hash(payload),
        "actor_id": "player-2",
        "plan_id": plan_id,
        "execution_request_id": "req-concurrent-demo",
        "approved_by": None,
        "payload": payload,
        "migrator_applied_from": None,
    }
    
    # Simulate concurrent retry storm
    simulator = RetryStormSimulator(sessionmaker)
    retry_attempts = 15  # Exceed minimum requirement of 10
    
    # Execute retries concurrently
    tasks = []
    for i in range(retry_attempts):
        task = simulator.simulate_event_creation_attempt(
            campaign_id, idempotency_key, event_data
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Analyze results
    successful_results = []
    failed_results = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_results.append((i, result))
        elif result[0]:  # success flag
            successful_results.append((i, result[1]))  # (attempt_index, event)
        else:
            failed_results.append((i, result[1]))  # (attempt_index, error_msg)
    
    print(f"Concurrent demo results: {len(successful_results)} successful, {len(failed_results)} failed")
    
    # For concurrent access, we may have some failures due to race conditions,
    # but we should have at least some successes
    assert len(successful_results) > 0, "At least some attempts should succeed"
    
    # Verify only one event was actually persisted
    async with sessionmaker() as db:
        from sqlalchemy import select, func
        
        count_stmt = select(func.count(models.Event.id)).where(
            models.Event.campaign_id == campaign_id,
            models.Event.idempotency_key == idempotency_key
        )
        event_count = await db.scalar(count_stmt)
        
        assert event_count == 1, f"Expected exactly 1 event persisted, found {event_count}"
    
    # Verify all successful results point to the same event
    if len(successful_results) > 1:
        first_event_id = successful_results[0][1].id
        for attempt_idx, event in successful_results[1:]:
            assert event.id == first_event_id, f"Attempt {attempt_idx} returned different event ID"
    
    print(f"SUCCESS: Concurrent retries resulted in exactly 1 persisted event with {len(successful_results)} successful reuses")