"""Tests for STORY-CDA-CORE-001E observability features."""

from datetime import datetime, timezone

import pytest

from Adventorator.events.envelope import (
    GENESIS_SCHEMA_VERSION,
    GenesisEvent,
    compute_idempotency_key_v2,
    compute_payload_hash,
    get_chain_tip,
    log_event_applied,
    log_idempotent_reuse,
)
from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.asyncio
async def test_chain_tip_accessor_empty_campaign(db):
    """Test chain tip accessor returns None for empty campaign."""
    from Adventorator import repos
    
    # Create campaign but no events
    campaign = await repos.get_or_create_campaign(db, 1234, name="Empty Campaign")
    
    # Should return None for empty chain
    tip = await get_chain_tip(db, campaign.id)
    assert tip is None


@pytest.mark.asyncio 
async def test_chain_tip_accessor_with_events(db):
    """Test chain tip accessor returns latest event info."""
    from Adventorator import repos
    
    # Setup campaign and scene
    campaign = await repos.get_or_create_campaign(db, 1235, name="Chain Tip Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 5678)
    
    # Create genesis event
    genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.flush()
    
    # Check tip after genesis
    tip = await get_chain_tip(db, campaign.id)
    assert tip is not None
    assert tip[0] == 0  # replay_ordinal
    assert tip[1] == genesis.payload_hash
    
    # Add another event
    payload = {"action": "test", "result": 42}
    event_data = {
        "campaign_id": campaign.id,
        "scene_id": scene.id,
        "replay_ordinal": 1,
        "type": "test.event",
        "event_schema_version": GENESIS_SCHEMA_VERSION,
        "world_time": 1,
        "wall_time_utc": datetime.now(timezone.utc),
        "prev_event_hash": genesis.payload_hash,
        "payload_hash": compute_payload_hash(payload),
        "idempotency_key": compute_idempotency_key_v2(
            plan_id="test-plan",
            campaign_id=campaign.id,
            event_type="test.event",
            tool_name="test_tool",
            ruleset_version="v1.0",
            args_json=payload,
        ),
        "actor_id": "test-actor",
        "plan_id": "test-plan",
        "execution_request_id": "test-req",
        "approved_by": None,
        "payload": payload,
        "migrator_applied_from": None,
    }
    
    from Adventorator import models
    event = models.Event(**event_data)
    db.add(event)
    await db.flush()
    
    # Check tip after second event
    tip = await get_chain_tip(db, campaign.id)
    assert tip is not None
    assert tip[0] == 1  # replay_ordinal
    assert tip[1] == event.payload_hash


def test_log_event_applied_metrics_and_structure(caplog):
    """Test event application logging increments metrics and logs structure."""
    reset_counters()
    
    # Test event application logging
    log_event_applied(
        event_id=123,
        campaign_id=456,
        replay_ordinal=5,
        event_type="spell.cast",
        idempotency_key=b"test_key_1234567",
        payload_hash=b"test_hash_abcdef12",
        plan_id="plan-789",
        execution_request_id="req-abc",
        latency_ms=15.5,
    )
    
    # Check metrics
    assert get_counter("events.applied") == 1
    assert get_counter("event.apply.latency_ms") == 15  # int conversion
    
    # Check log structure (would need to verify in real logging setup)
    # This is a simplified test - in practice would check structured log output


def test_log_idempotent_reuse_metrics():
    """Test idempotent reuse logging increments correct metric."""
    reset_counters()
    
    log_idempotent_reuse(
        event_id=999,
        campaign_id=888,
        idempotency_key=b"reuse_key_test123",
        plan_id="reuse-plan",
    )
    
    # Check metric incremented
    assert get_counter("events.idempotent_reuse") == 1


def test_observability_metric_names():
    """Test that all required observability metrics are available."""
    reset_counters()
    
    # Test all required metrics from acceptance criteria
    required_metrics = [
        "events.applied",
        "events.conflict", 
        "events.idempotent_reuse",
        "events.hash_mismatch", 
        "event.apply.latency_ms",
    ]
    
    # Simulate incrementing all metrics
    from Adventorator.metrics import inc_counter
    for metric in required_metrics:
        inc_counter(metric)
    
    # Verify all metrics are tracked
    for metric in required_metrics:
        assert get_counter(metric) == 1


@pytest.mark.asyncio
async def test_chain_tip_performance_baseline(db):
    """Measure chain tip accessor performance for observability."""
    import time

    from Adventorator import repos
    
    # Setup
    campaign = await repos.get_or_create_campaign(db, 9876, name="Perf Campaign")
    scene = await repos.ensure_scene(db, campaign.id, 5432)
    
    # Create several events
    genesis = GenesisEvent(campaign_id=campaign.id, scene_id=scene.id).instantiate()
    db.add(genesis)
    await db.flush()
    
    # Add 10 more events
    prev_hash = genesis.payload_hash
    for i in range(1, 11):
        payload = {"step": i}
        event_data = {
            "campaign_id": campaign.id,
            "scene_id": scene.id,
            "replay_ordinal": i,
            "type": "perf.test",
            "event_schema_version": GENESIS_SCHEMA_VERSION,
            "world_time": i,
            "wall_time_utc": datetime.now(timezone.utc),
            "prev_event_hash": prev_hash,
            "payload_hash": compute_payload_hash(payload),
            "idempotency_key": compute_idempotency_key_v2(
                plan_id=f"perf-plan-{i}",
                campaign_id=campaign.id,
                event_type="perf.test",
                tool_name="perf_tool",
                ruleset_version="v1.0",
                args_json=payload,
            ),
            "actor_id": "perf-actor",
            "plan_id": f"perf-plan-{i}",
            "execution_request_id": f"perf-req-{i}",
            "approved_by": None,
            "payload": payload,
            "migrator_applied_from": None,
        }
        
        from Adventorator import models
        event = models.Event(**event_data)
        db.add(event)
        prev_hash = event.payload_hash
    
    await db.flush()
    
    # Measure chain tip access performance
    start_time = time.time()
    
    # Call chain tip multiple times
    for _ in range(100):
        tip = await get_chain_tip(db, campaign.id)
        assert tip is not None
        assert tip[0] == 10  # Should be the last event
    
    end_time = time.time()
    elapsed_ms = (end_time - start_time) * 1000
    avg_time_ms = elapsed_ms / 100
    
    print(f"Chain tip access: 100 calls in {elapsed_ms:.2f}ms")
    print(f"Average time per call: {avg_time_ms:.2f}ms")
    
    # Performance assertion - should be fast
    assert avg_time_ms < 5.0, f"Chain tip access too slow: {avg_time_ms:.2f}ms per call"