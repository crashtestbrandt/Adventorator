#!/usr/bin/env python3
"""Standalone collision test demonstration for idempotency key v2."""

import os
import sys

# Import the standalone implementation
sys.path.insert(0, os.path.dirname(__file__))
import random
import string

from test_idempotency_standalone import compute_idempotency_key_v2_standalone


def generate_random_string(rng, min_len=1, max_len=50):
    """Generate a random string."""
    length = rng.randint(min_len, max_len)
    return ''.join(rng.choices(string.ascii_letters + string.digits + '-_', k=length))


def generate_random_inputs(rng):
    """Generate random inputs for testing."""
    return {
        "plan_id": rng.choice([None, generate_random_string(rng, 5, 30)]),
        "campaign_id": rng.randint(1, 10000),
        "event_type": rng.choice([
            "tool.execute", "spell.cast", "action.attack", "rule.check",
            generate_random_string(rng, 3, 20)
        ]),
        "tool_name": rng.choice([None, "dice_roll", "spell_check", generate_random_string(rng, 3, 20)]),
        "ruleset_version": rng.choice([None, "dnd5e-v1.0", "dnd5e-v1.1", generate_random_string(rng, 3, 15)]),
        "args_json": rng.choice([None, {}, {"test": rng.randint(1, 100)}])
    }


def run_collision_test(iterations=1000):
    """Run a collision test with the specified number of iterations."""
    print(f"Running collision test with {iterations:,} iterations...")
    
    rng = random.Random(42)  # Fixed seed for reproducibility
    keys = set()
    collisions = 0
    
    for i in range(iterations):
        if i % 100 == 0 and i > 0:
            print(f"Progress: {i:,}/{iterations:,} ({i/iterations*100:.1f}%)")
        
        inputs = generate_random_inputs(rng)
        key = compute_idempotency_key_v2_standalone(**inputs)
        
        if key in keys:
            collisions += 1
            print(f"COLLISION #{collisions} at iteration {i}!")
            print(f"  Key: {key.hex()}")
            print(f"  Inputs: {inputs}")
        else:
            keys.add(key)
    
    print("\n=== COLLISION TEST RESULTS ===")
    print(f"Total iterations: {iterations:,}")
    print(f"Unique keys: {len(keys):,}")
    print(f"Collisions: {collisions}")
    print(f"Collision rate: {collisions/iterations:.10f}")
    
    if collisions == 0:
        print("✅ PASSED: No collisions detected!")
    else:
        print(f"❌ FAILED: {collisions} collisions detected")
    
    return collisions == 0


def test_determinism():
    """Test that same inputs produce same keys."""
    print("\nTesting determinism...")
    
    test_inputs = {
        "plan_id": "test-plan-123",
        "campaign_id": 456,
        "event_type": "tool.execute",
        "tool_name": "dice_roll",
        "ruleset_version": "dnd5e-v1.0",
        "args_json": {"sides": 20, "count": 1}
    }
    
    key1 = compute_idempotency_key_v2_standalone(**test_inputs)
    key2 = compute_idempotency_key_v2_standalone(**test_inputs)
    
    if key1 == key2:
        print("✅ Determinism test passed")
        return True
    else:
        print("❌ Determinism test failed")
        print(f"  Key 1: {key1.hex()}")
        print(f"  Key 2: {key2.hex()}")
        return False


def test_input_sensitivity():
    """Test that different inputs produce different keys."""
    print("\nTesting input sensitivity...")
    
    base_inputs = {
        "plan_id": "plan-123",
        "campaign_id": 456,
        "event_type": "tool.execute",
        "tool_name": "dice_roll",
        "ruleset_version": "dnd5e-v1.0",
        "args_json": {"sides": 20, "count": 1}
    }
    
    base_key = compute_idempotency_key_v2_standalone(**base_inputs)
    
    test_cases = [
        ("plan_id", "plan-456"),
        ("campaign_id", 999),
        ("event_type", "tool.validate"),
        ("tool_name", "other_tool"),
        ("ruleset_version", "dnd5e-v2.0"),
        ("args_json", {"sides": 6, "count": 2}),
    ]
    
    all_passed = True
    for param, new_value in test_cases:
        modified_inputs = base_inputs.copy()
        modified_inputs[param] = new_value
        modified_key = compute_idempotency_key_v2_standalone(**modified_inputs)
        
        if modified_key != base_key:
            print(f"✅ {param} change produces different key")
        else:
            print(f"❌ {param} change did NOT produce different key")
            all_passed = False
    
    if all_passed:
        print("✅ All input sensitivity tests passed")
    else:
        print("❌ Some input sensitivity tests failed")
    
    return all_passed


if __name__ == "__main__":
    print("=== Idempotency Key V2 Collision Testing ===")
    
    # Run basic tests
    determinism_ok = test_determinism()
    sensitivity_ok = test_input_sensitivity()
    
    if not determinism_ok or not sensitivity_ok:
        print("\n❌ Basic tests failed - aborting collision test")
        sys.exit(1)
    
    # Run collision tests
    print("\n" + "="*50)
    collision_ok = run_collision_test(1000)
    
    # Summary
    print("\n" + "="*50)
    print("=== FINAL RESULTS ===")
    
    if determinism_ok and sensitivity_ok and collision_ok:
        print("🎉 ALL TESTS PASSED!")
        print("\nKey features validated:")
        print("- ✅ Deterministic behavior")
        print("- ✅ Input sensitivity")
        print("- ✅ Collision resistance (1000 iterations)")
        print("\nIdempotency key v2 implementation is working correctly!")
    else:
        print("❌ Some tests failed")
        sys.exit(1)