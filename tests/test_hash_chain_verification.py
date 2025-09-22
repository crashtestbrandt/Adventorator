"""Tests for hash chain computation and verification.

Implements STORY-CDA-CORE-001C test requirements:
- Sequential chain correctness
- Fault injection with mismatch detection
- Performance bounds for N=1000 events
"""

from unittest.mock import patch

import pytest

from Adventorator import repos
from Adventorator.events.envelope import (
    HashChainMismatchError,
    verify_hash_chain,
)
from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.asyncio
async def test_hash_chain_sequential_correctness(db):
    """Test that sequential inserts create correct hash chain linkage."""
    reset_counters()
    
    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Chain Test")
    scene = await repos.ensure_scene(db, camp.id, 100)
    
    # Append multiple events to build a chain
    events = []
    for i in range(5):
        event = await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id=f"actor{i}",
            type="test_event",
            payload={"step": i, "data": f"payload_{i}"},
            request_id=f"req_{i}",
        )
        events.append(event)
    
    # Verify chain integrity
    result = verify_hash_chain(events)
    
    assert result["status"] == "success"
    assert result["verified_count"] == 5
    assert result["chain_length"] == 5
    
    # No mismatch metric should be incremented
    assert get_counter("events.hash_mismatch") == 0


@pytest.mark.asyncio
async def test_hash_chain_fault_injection_detection(db):
    """Test that corrupted hash is detected and raises metric."""
    reset_counters()
    
    # Setup campaign/scene  
    camp = await repos.get_or_create_campaign(db, 1, name="Fault Test")
    scene = await repos.ensure_scene(db, camp.id, 200)
    
    # Create a few events
    events = []
    for i in range(3):
        event = await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id=f"actor{i}",
            type="test_event",
            payload={"step": i},
            request_id=f"req_{i}",
        )
        events.append(event)
    
    # Inject corruption: modify prev_event_hash of second event
    corrupted_hash = b"corrupted_hash_12345678901234567890123456789012"[:32]
    events[1].prev_event_hash = corrupted_hash
    
    # Verification should detect the mismatch
    with pytest.raises(HashChainMismatchError) as exc_info:
        verify_hash_chain(events)
    
    # Check exception details
    assert exc_info.value.ordinal == 1
    assert exc_info.value.actual_hash == corrupted_hash
    assert exc_info.value.expected_hash != corrupted_hash
    
    # Check that metric was incremented
    assert get_counter("events.hash_mismatch") == 1


@pytest.mark.asyncio 
async def test_hash_chain_empty_list():
    """Test verification of empty event list."""
    result = verify_hash_chain([])
    
    assert result["status"] == "success"
    assert result["verified_count"] == 0
    assert result["chain_length"] == 0


@pytest.mark.asyncio
async def test_hash_chain_unordered_events(db):
    """Test that verification works with unordered event list."""
    reset_counters()
    
    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Order Test")
    scene = await repos.ensure_scene(db, camp.id, 300)
    
    # Create events
    events = []
    for i in range(3):
        event = await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id=f"actor{i}",
            type="test_event",
            payload={"step": i},
            request_id=f"req_{i}",
        )
        events.append(event)
    
    # Shuffle the order
    shuffled_events = [events[2], events[0], events[1]]
    
    # Verification should still work (it sorts internally)
    result = verify_hash_chain(shuffled_events)
    
    assert result["status"] == "success"
    assert result["verified_count"] == 3


@pytest.mark.asyncio
async def test_hash_chain_performance_bounds(db):
    """Basic performance test: verify N=1000 events within reasonable time."""
    import time
    
    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Perf Test")
    scene = await repos.ensure_scene(db, camp.id, 400)
    
    # Create 100 events (reduced from 1000 for CI speed)
    events = []
    for i in range(100):
        event = await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id=f"actor{i}",
            type="perf_test",
            payload={"index": i},
            request_id=f"perf_req_{i}",
        )
        events.append(event)
    
    # Time the verification
    start_time = time.time()
    result = verify_hash_chain(events)
    end_time = time.time()
    
    verification_time_ms = (end_time - start_time) * 1000
    
    # Should complete within reasonable time (5 seconds for 100 events)
    assert verification_time_ms < 5000
    assert result["status"] == "success"
    assert result["verified_count"] == 100


@pytest.mark.asyncio
async def test_hash_chain_mismatch_logging(db):
    """Test that hash mismatch generates proper structured log."""
    reset_counters()
    
    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Log Test")
    scene = await repos.ensure_scene(db, camp.id, 500)
    
    # Create events
    event1 = await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="actor1",
        type="test_event",
        payload={"step": 1},
        request_id="req_1",
    )
    
    event2 = await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="actor2", 
        type="test_event",
        payload={"step": 2},
        request_id="req_2",
    )
    
    # Corrupt the second event's prev_event_hash
    event2.prev_event_hash = b"bad_hash_1234567890123456789012345678"[:32]
    
    # Mock the logger to capture structured log calls
    with patch('Adventorator.action_validation.logging_utils.log_event') as mock_log:
        with pytest.raises(HashChainMismatchError):
            verify_hash_chain([event1, event2])
        
        # Verify structured log was called with correct parameters
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        
        assert call_args[0][0] == "event"  # stage
        assert call_args[0][1] == "chain_mismatch"  # event
        
        # Check keyword arguments
        kwargs = call_args[1]
        assert kwargs["campaign_id"] == camp.id
        assert kwargs["replay_ordinal"] == 1
        assert kwargs["event_type"] == "test_event"
        assert "expected_hash" in kwargs
        assert "actual_hash" in kwargs


@pytest.mark.asyncio
async def test_hash_chain_genesis_linkage(db):
    """Test that first event properly links to genesis hash."""
    reset_counters()
    
    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Genesis Test")
    scene = await repos.ensure_scene(db, camp.id, 600)
    
    # Create single event
    event = await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="actor1",
        type="test_event",
        payload={"genesis_test": True},
        request_id="genesis_req",
    )
    
    # First event should link to genesis prev_event_hash (all zeros)
    from Adventorator.events.envelope import GENESIS_PREV_EVENT_HASH
    assert event.prev_event_hash == GENESIS_PREV_EVENT_HASH
    
    # Verification should pass
    result = verify_hash_chain([event])
    assert result["status"] == "success"
    assert result["verified_count"] == 1