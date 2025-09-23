"""Retry storm test harness (STORY-CDA-CORE-001D)."""

import asyncio
import pytest
import time
from datetime import datetime, timezone
from typing import Dict, Any

from Adventorator.events.envelope import compute_idempotency_key_v2, compute_payload_hash
from Adventorator.events.envelope import GENESIS_SCHEMA_VERSION


class RetryStormSimulator:
    """Simulates rapid retry attempts for idempotency testing."""
    
    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker
        self.retry_count = 0
        self.successful_inserts = 0
        self.idempotent_reuses = 0
        
    async def simulate_event_creation_attempt(
        self, 
        campaign_id: int,
        idempotency_key: bytes,
        event_data: Dict[str, Any]
    ) -> tuple[bool, Any]:
        """Attempt to create an event, handling idempotency conflicts.
        
        Uses a separate database session to avoid concurrency issues.
        
        Returns:
            (success: bool, event_or_existing)
        """
        from Adventorator import models
        from sqlalchemy.exc import IntegrityError, OperationalError
        
        self.retry_count += 1
        
        # Use a separate session for each attempt to avoid concurrency issues
        async with self.sessionmaker() as db:
            try:
                # Check if event already exists with this idempotency key
                from sqlalchemy import select
                stmt = select(models.Event).where(
                    models.Event.campaign_id == campaign_id,
                    models.Event.idempotency_key == idempotency_key
                )
                existing = await db.scalar(stmt)
                
                if existing:
                    self.idempotent_reuses += 1
                    return True, existing
                
                # Try to create new event
                event = models.Event(
                    campaign_id=campaign_id,
                    idempotency_key=idempotency_key,
                    **event_data
                )
                
                db.add(event)
                await db.commit()  # Use commit instead of flush for full transaction
                
                self.successful_inserts += 1
                return True, event
                
            except (IntegrityError, OperationalError) as e:
                # Race condition - another attempt won
                await db.rollback()
                
                # Fetch the winning event
                stmt = select(models.Event).where(
                    models.Event.campaign_id == campaign_id,
                    models.Event.idempotency_key == idempotency_key
                )
                existing = await db.scalar(stmt)
                
                if existing:
                    self.idempotent_reuses += 1
                    return True, existing
                else:
                    # This should not happen
                    return False, f"No event found after integrity error: {e}"
            except Exception as e:
                # Catch any other exceptions for debugging
                await db.rollback()
                return False, f"Unexpected error: {type(e).__name__}: {e}"


@pytest.mark.asyncio
async def test_retry_storm_single_winner(db):
    """Test that rapid retries of same operation result in single event."""
    from Adventorator import repos
    
    # Setup test campaign and scene
    campaign = await repos.get_or_create_campaign(db, 9999, name="Retry Storm Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 8888)
    
    # Create genesis event
    from Adventorator.events.envelope import GenesisEvent
    genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.commit()  # Commit so other sessions can see it
    
    # Define the operation that will be retried
    plan_id = "retry-storm-plan-123"
    tool_name = "dice_roll"
    ruleset_version = "dnd5e-v1.0"
    args_json = {"sides": 20, "count": 1, "modifier": 3}
    
    # Compute idempotency key
    idempotency_key = compute_idempotency_key_v2(
        plan_id=plan_id,
        campaign_id=campaign.id,
        event_type="tool.execute",
        tool_name=tool_name,
        ruleset_version=ruleset_version,
        args_json=args_json,
    )
    
    # Common event data
    payload = {"result": 15, "details": "d20 roll + 3"}
    event_data = {
        "scene_id": scene.id,
        "replay_ordinal": genesis.replay_ordinal + 1,
        "type": "tool.execute",
        "event_schema_version": GENESIS_SCHEMA_VERSION,
        "world_time": genesis.world_time + 1,
        "wall_time_utc": datetime.now(timezone.utc),
        "prev_event_hash": genesis.payload_hash,
        "payload_hash": compute_payload_hash(payload),
        "actor_id": "player-1",
        "plan_id": plan_id,
        "execution_request_id": "req-storm-test",
        "approved_by": None,
        "payload": payload,
        "migrator_applied_from": None,
    }
    
    # Simulate rapid retry storm (minimum 10 as per acceptance criteria)
    from Adventorator.db import get_sessionmaker
    sessionmaker = get_sessionmaker()
    simulator = RetryStormSimulator(sessionmaker)
    retry_attempts = 15  # Exceed minimum requirement
    
    # Execute retries rapidly
    tasks = []
    for i in range(retry_attempts):
        task = simulator.simulate_event_creation_attempt(
            campaign.id, idempotency_key, event_data
        )
        tasks.append(task)
    
    # Execute all attempts concurrently to maximize race conditions
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify results
    successful_results = [r for r in results if not isinstance(r, Exception) and r[0]]
    assert len(successful_results) == retry_attempts, "All attempts should succeed (create or reuse)"
    
    # Verify only one event was actually persisted
    from sqlalchemy import select, func
    from Adventorator import models
    
    count_stmt = select(func.count(models.Event.id)).where(
        models.Event.campaign_id == campaign.id,
        models.Event.idempotency_key == idempotency_key
    )
    event_count = await db.scalar(count_stmt)
    
    assert event_count == 1, f"Expected 1 event, found {event_count}"
    
    # Verify metrics
    assert simulator.retry_count == retry_attempts
    assert simulator.successful_inserts == 1, f"Expected 1 insert, got {simulator.successful_inserts}"
    assert simulator.idempotent_reuses == retry_attempts - 1, f"Expected {retry_attempts - 1} reuses, got {simulator.idempotent_reuses}"
    
    # Verify all results point to the same event
    events = [r[1] for r in successful_results]
    first_event = events[0]
    for event in events[1:]:
        assert event.id == first_event.id, "All attempts should return the same event"
        assert event.idempotency_key == idempotency_key


@pytest.mark.asyncio
async def test_retry_storm_different_operations_different_events(db):
    """Test that different operations create different events even under retry storm."""
    from Adventorator import repos
    
    # Setup
    campaign = await repos.get_or_create_campaign(db, 8888, name="Multi-Op Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 7777)
    
    from Adventorator.events.envelope import GenesisEvent
    genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.commit()  # Commit so other sessions can see it
    
    # Define two different operations
    operations = [
        {
            "plan_id": "plan-A",
            "tool_name": "dice_roll",
            "args_json": {"sides": 20, "count": 1},
            "payload": {"result": 15},
        },
        {
            "plan_id": "plan-B", 
            "tool_name": "spell_check",
            "args_json": {"spell": "fireball", "level": 3},
            "payload": {"result": "valid"},
        },
    ]
    
    # Create retry storms for both operations simultaneously
    tasks = []
    for op_idx, op in enumerate(operations):
        idempotency_key = compute_idempotency_key_v2(
            plan_id=op["plan_id"],
            campaign_id=campaign.id,
            event_type="tool.execute",
            tool_name=op["tool_name"],
            ruleset_version="dnd5e-v1.0",
            args_json=op["args_json"],
        )
        
        event_data = {
            "scene_id": scene.id,
            "replay_ordinal": genesis.replay_ordinal + 1 + op_idx,
            "type": "tool.execute",
            "event_schema_version": GENESIS_SCHEMA_VERSION,
            "world_time": genesis.world_time + 1 + op_idx,
            "wall_time_utc": datetime.now(timezone.utc),
            "prev_event_hash": genesis.payload_hash,
            "payload_hash": compute_payload_hash(op["payload"]),
            "actor_id": f"player-{op_idx + 1}",
            "plan_id": op["plan_id"],
            "execution_request_id": f"req-op-{op_idx}",
            "approved_by": None,
            "payload": op["payload"],
            "migrator_applied_from": None,
        }
        
        # 5 retries per operation
        from Adventorator.db import get_sessionmaker
        sessionmaker = get_sessionmaker()
        simulator = RetryStormSimulator(sessionmaker)
        for retry in range(5):
            task = simulator.simulate_event_creation_attempt(
                campaign.id, idempotency_key, event_data
            )
            tasks.append(task)
    
    # Execute all retries concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify all succeeded
    successful_results = [r for r in results if not isinstance(r, Exception) and r[0]]
    assert len(successful_results) == 10  # 5 retries × 2 operations
    
    # Verify exactly 2 unique events were created (one per operation)
    from sqlalchemy import select, func
    from Adventorator import models
    
    count_stmt = select(func.count(models.Event.id)).where(
        models.Event.campaign_id == campaign.id,
        models.Event.type == "tool.execute"
    )
    event_count = await db.scalar(count_stmt)
    
    assert event_count == 2, f"Expected 2 events (one per operation), found {event_count}"


@pytest.mark.asyncio 
async def test_retry_storm_performance_baseline(db):
    """Measure retry storm handling performance for observability."""
    import time
    from Adventorator import repos
    
    # Setup
    campaign = await repos.get_or_create_campaign(db, 7777, name="Perf Test Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 6666)
    
    from Adventorator.events.envelope import GenesisEvent
    genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.commit()  # Commit so other sessions can see it
    
    # Define operation
    idempotency_key = compute_idempotency_key_v2(
        plan_id="perf-test-plan",
        campaign_id=campaign.id,
        event_type="performance.test",
        tool_name="perf_tool",
        ruleset_version="test-v1.0",
        args_json={"test": "performance"},
    )
    
    event_data = {
        "scene_id": scene.id,
        "replay_ordinal": genesis.replay_ordinal + 1,
        "type": "performance.test",
        "event_schema_version": GENESIS_SCHEMA_VERSION,
        "world_time": genesis.world_time + 1,
        "wall_time_utc": datetime.now(timezone.utc),
        "prev_event_hash": genesis.payload_hash,
        "payload_hash": compute_payload_hash({"test": True}),
        "actor_id": "perf-tester",
        "plan_id": "perf-test-plan",
        "execution_request_id": "perf-req",
        "approved_by": None,
        "payload": {"test": True},
        "migrator_applied_from": None,
    }
    
    # Time the retry storm
    from Adventorator.db import get_sessionmaker
    sessionmaker = get_sessionmaker()
    simulator = RetryStormSimulator(sessionmaker)
    retry_count = 25  # Higher count for performance test
    
    start_time = time.time()
    
    tasks = []
    for i in range(retry_count):
        task = simulator.simulate_event_creation_attempt(
            campaign.id, idempotency_key, event_data
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    elapsed_ms = (end_time - start_time) * 1000
    
    # Verify correctness
    successful_results = [r for r in results if not isinstance(r, Exception) and r[0]]
    assert len(successful_results) == retry_count
    assert simulator.successful_inserts == 1
    assert simulator.idempotent_reuses == retry_count - 1
    
    # Log performance metrics for observability
    avg_retry_time_ms = elapsed_ms / retry_count
    
    print(f"Retry storm performance: {retry_count} retries in {elapsed_ms:.2f}ms")
    print(f"Average time per retry: {avg_retry_time_ms:.2f}ms")
    print(f"Successful inserts: {simulator.successful_inserts}")
    print(f"Idempotent reuses: {simulator.idempotent_reuses}")
    
    # Performance assertion - should complete quickly
    assert elapsed_ms < 5000, f"Retry storm took too long: {elapsed_ms}ms"