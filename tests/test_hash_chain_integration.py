"""Integration test demonstrating hash chain verification usage.

Shows how to verify a complete campaign's event chain using the new
verification API from STORY-CDA-CORE-001C.
"""

import pytest

from Adventorator import repos
from Adventorator.events.envelope import verify_hash_chain, HashChainMismatchError
from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.asyncio
async def test_campaign_hash_chain_verification_integration(db):
    """Demonstrate complete campaign verification workflow."""
    reset_counters()
    
    # Setup campaign with multiple scenes and events
    camp = await repos.get_or_create_campaign(db, guild_id=12345, name="Integration Test Campaign")
    scene1 = await repos.ensure_scene(db, camp.id, channel_id=1001)
    scene2 = await repos.ensure_scene(db, camp.id, channel_id=1002)
    
    # Add events across multiple scenes to build a campaign-wide chain
    for i in range(10):
        scene_id = scene1.id if i % 2 == 0 else scene2.id
        await repos.append_event(
            db,
            scene_id=scene_id,
            actor_id=f"player_{i}",
            type="integration_test",
            payload={"action": f"step_{i}", "scene": "scene1" if i % 2 == 0 else "scene2"},
            request_id=f"integration_req_{i}",
        )
    
    # Retrieve all campaign events using the new convenience function
    events = await repos.get_campaign_events_for_verification(db, campaign_id=camp.id)
    
    assert len(events) == 10
    
    # Verify the complete campaign hash chain
    result = verify_hash_chain(events)
    
    assert result["status"] == "success"
    assert result["verified_count"] == 10
    assert result["chain_length"] == 10
    
    # No hash mismatches should be detected
    assert get_counter("events.hash_mismatch") == 0
    
    # Events should be properly ordered by replay_ordinal
    for i, event in enumerate(events):
        assert event.replay_ordinal == i
        assert f"step_{i}" in str(event.payload)


@pytest.mark.asyncio
async def test_verification_with_real_data_patterns(db):
    """Test verification with realistic D&D event patterns."""
    reset_counters()
    
    # Setup typical D&D campaign
    camp = await repos.get_or_create_campaign(db, guild_id=54321, name="D&D Campaign")
    scene = await repos.ensure_scene(db, camp.id, channel_id=2001)
    
    # Simulate typical game events
    event_sequence = [
        ("character_creation", {"character": "Thorin", "class": "Fighter"}),
        ("roll_initiative", {"character": "Thorin", "roll": 15}),
        ("attack", {"attacker": "Thorin", "target": "Goblin", "damage": 8}),
        ("spell_cast", {"caster": "Mage", "spell": "Magic Missile", "target": "Goblin"}),
        ("end_combat", {"victor": "party", "xp_gained": 100}),
    ]
    
    for i, (event_type, payload) in enumerate(event_sequence):
        await repos.append_event(
            db,
            scene_id=scene.id,
            actor_id="dm" if "end_" in event_type else payload.get("character", "player"),
            type=event_type,
            payload=payload,
            request_id=f"dnd_event_{i}",
        )
    
    # Verify chain integrity
    events = await repos.get_campaign_events_for_verification(db, campaign_id=camp.id)
    result = verify_hash_chain(events)
    
    assert result["status"] == "success"
    assert result["verified_count"] == len(event_sequence)
    assert get_counter("events.hash_mismatch") == 0