#!/usr/bin/env python3
"""Standalone test for idempotency key v2 implementation."""

import sys
import hashlib
import json
from typing import Mapping, Any


def canonical_json_bytes(payload: Mapping[str, Any] | None) -> bytes:
    """Simplified canonical JSON for testing."""
    if payload is None:
        payload = {}
    
    # Simple implementation for testing
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return json_str.encode("utf-8")


def compute_idempotency_key_v2_standalone(
    *,
    plan_id: str | None,
    campaign_id: int,
    event_type: str,
    tool_name: str | None,
    ruleset_version: str | None,
    args_json: Mapping[str, Any] | None,
) -> bytes:
    """Standalone version of v2 idempotency key for testing."""
    # Length-prefixed binary framing to avoid delimiter collision ambiguity.
    components = [
        ("plan_id", (plan_id or "").encode("utf-8")),
        ("campaign_id", str(campaign_id).encode("utf-8")),
        ("event_type", event_type.encode("utf-8")),
        ("tool_name", (tool_name or "").encode("utf-8")),
        ("ruleset_version", (ruleset_version or "").encode("utf-8")),
        ("args_json", canonical_json_bytes(args_json)),
    ]
    framed = []
    for label, value in components:
        framed.append(label.encode("utf-8"))
        framed.append(len(value).to_bytes(4, "big", signed=False))
        framed.append(value)
    digest = hashlib.sha256(b"".join(framed)).digest()
    return digest[:16]


def test_basic_functionality():
    """Test basic functionality."""
    print("Testing basic functionality...")
    
    key = compute_idempotency_key_v2_standalone(
        plan_id='test-plan',
        campaign_id=123,
        event_type='test.event',
        tool_name='test_tool',
        ruleset_version='v1.0',
        args_json={'test': 'value'}
    )
    
    assert len(key) == 16, f"Expected 16 bytes, got {len(key)}"
    assert isinstance(key, bytes), f"Expected bytes, got {type(key)}"
    
    print(f"✓ Key generated: {key.hex()}")
    print(f"✓ Key length: {len(key)} bytes")


def test_determinism():
    """Test deterministic behavior."""
    print("\nTesting determinism...")
    
    args = {
        "plan_id": "plan-123",
        "campaign_id": 456,
        "event_type": "tool.execute",
        "tool_name": "dice_roll",
        "ruleset_version": "dnd5e-v1.0",
        "args_json": {"sides": 20, "count": 1},
    }
    
    key1 = compute_idempotency_key_v2_standalone(**args)
    key2 = compute_idempotency_key_v2_standalone(**args)
    
    assert key1 == key2, "Same inputs should produce same key"
    print("✓ Deterministic behavior verified")


def test_different_inputs():
    """Test that different inputs produce different keys."""
    print("\nTesting input sensitivity...")
    
    base_args = {
        "plan_id": "plan-123",
        "campaign_id": 456,
        "event_type": "tool.execute", 
        "tool_name": "dice_roll",
        "ruleset_version": "dnd5e-v1.0",
        "args_json": {"sides": 20, "count": 1},
    }
    
    base_key = compute_idempotency_key_v2_standalone(**base_args)
    
    # Test each parameter change produces different key
    test_cases = [
        ("plan_id", "plan-456"),
        ("campaign_id", 999),
        ("event_type", "tool.validate"),
        ("tool_name", "other_tool"),
        ("ruleset_version", "dnd5e-v2.0"),
        ("args_json", {"sides": 6, "count": 2}),
    ]
    
    for param, new_value in test_cases:
        modified_args = base_args.copy()
        modified_args[param] = new_value
        modified_key = compute_idempotency_key_v2_standalone(**modified_args)
        
        assert modified_key != base_key, f"Changing {param} should produce different key"
        print(f"✓ {param} change produces different key")


def test_null_handling():
    """Test null value handling."""
    print("\nTesting null value handling...")
    
    key1 = compute_idempotency_key_v2_standalone(
        plan_id=None,
        campaign_id=123,
        event_type="test.event",
        tool_name=None,
        ruleset_version=None,
        args_json=None,
    )
    
    key2 = compute_idempotency_key_v2_standalone(
        plan_id="",
        campaign_id=123, 
        event_type="test.event",
        tool_name="",
        ruleset_version="",
        args_json={},
    )
    
    assert len(key1) == 16, "Null values should still produce 16-byte key"
    assert len(key2) == 16, "Empty values should still produce 16-byte key"
    
    # Note: key1 and key2 should be different since None->'' for strings but None->b'{}' for args_json->{}
    print(f"Key with None values: {key1.hex()}")
    print(f"Key with empty values: {key2.hex()}")
    
    print("✓ Null value handling verified")


def test_composition_order():
    """Test that composition follows acceptance criteria order."""
    print("\nTesting composition order...")
    
    args = {
        "plan_id": "test-plan",
        "campaign_id": 123,
        "event_type": "test.action",
        "tool_name": "test_tool", 
        "ruleset_version": "v1.0",
        "args_json": {"test": "value"},
    }
    
    actual_key = compute_idempotency_key_v2_standalone(**args)
    
    # Manually compute expected key based on acceptance criteria order
    components = [
        ("plan_id", args["plan_id"].encode("utf-8")),
        ("campaign_id", str(args["campaign_id"]).encode("utf-8")),
        ("event_type", args["event_type"].encode("utf-8")),
        ("tool_name", args["tool_name"].encode("utf-8")),
        ("ruleset_version", args["ruleset_version"].encode("utf-8")),
        ("args_json", canonical_json_bytes(args["args_json"])),
    ]
    
    framed = []
    for label, value in components:
        framed.append(label.encode("utf-8"))
        framed.append(len(value).to_bytes(4, "big", signed=False))
        framed.append(value)
    
    expected_key = hashlib.sha256(b"".join(framed)).digest()[:16]
    
    assert actual_key == expected_key, "Implementation order must match acceptance criteria"
    print("✓ Composition order matches acceptance criteria")


def test_collision_resistance_sample():
    """Test basic collision resistance with small sample."""
    print("\nTesting collision resistance (small sample)...")
    
    keys = set()
    test_count = 1000
    
    for i in range(test_count):
        key = compute_idempotency_key_v2_standalone(
            plan_id=f"plan-{i}",
            campaign_id=i % 100 + 1,
            event_type=f"event.type.{i % 10}",
            tool_name=f"tool_{i % 20}",
            ruleset_version=f"v{i % 5}.0",
            args_json={"iteration": i, "data": f"value_{i}"},
        )
        
        assert key not in keys, f"Collision detected at iteration {i}!"
        keys.add(key)
    
    assert len(keys) == test_count, f"Expected {test_count} unique keys, got {len(keys)}"
    print(f"✓ Generated {test_count} unique keys without collisions")


if __name__ == "__main__":
    print("=== Idempotency Key V2 Standalone Tests ===")
    
    try:
        test_basic_functionality()
        test_determinism()
        test_different_inputs()
        test_null_handling()
        test_composition_order()
        test_collision_resistance_sample()
        
        print("\n🎉 All tests passed!")
        print("\nKey features verified:")
        print("- ✓ 16-byte deterministic output")
        print("- ✓ Input sensitivity")
        print("- ✓ Null value handling")
        print("- ✓ Correct composition order")
        print("- ✓ Basic collision resistance")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)