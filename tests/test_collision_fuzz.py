"""Collision fuzz test for idempotency keys (STORY-CDA-CORE-001D)."""

import random
import string
import hashlib
from typing import Set, List, Dict, Any, Tuple
from collections import defaultdict

import pytest
from Adventorator.events.envelope import compute_idempotency_key_v2


class IdempotencyCollisionTester:
    """Fuzz tester for idempotency key collisions."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.generated_keys: Set[bytes] = set()
        self.collision_count = 0
        self.collision_details: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        
    def generate_random_string(self, min_len: int = 1, max_len: int = 50) -> str:
        """Generate a random string."""
        length = self.rng.randint(min_len, max_len)
        return ''.join(self.rng.choices(string.ascii_letters + string.digits + '-_', k=length))
    
    def generate_random_json(self, max_depth: int = 3, max_items: int = 10) -> Dict[str, Any]:
        """Generate random JSON-serializable data."""
        if max_depth <= 0:
            # Base case - return simple value
            return self.rng.choice([
                self.rng.randint(-1000, 1000),
                self.generate_random_string(1, 20),
                self.rng.choice([True, False]),
            ])
        
        # Generate dict with random keys/values
        result = {}
        num_items = self.rng.randint(0, max_items)
        
        for _ in range(num_items):
            key = self.generate_random_string(1, 10)
            value_type = self.rng.choice(['int', 'str', 'bool', 'dict', 'list'])
            
            if value_type == 'int':
                value = self.rng.randint(-1000, 1000)
            elif value_type == 'str':
                value = self.generate_random_string(0, 30)
            elif value_type == 'bool':
                value = self.rng.choice([True, False])
            elif value_type == 'dict':
                value = self.generate_random_json(max_depth - 1, max_items // 2)
            else:  # list
                list_len = self.rng.randint(0, 5)
                value = [self.generate_random_json(max_depth - 1, 2) for _ in range(list_len)]
            
            result[key] = value
        
        return result
    
    def generate_random_idempotency_input(self) -> Dict[str, Any]:
        """Generate random inputs for idempotency key computation."""
        return {
            "plan_id": self.rng.choice([
                None,
                self.generate_random_string(5, 30)
            ]),
            "campaign_id": self.rng.randint(1, 10000),
            "event_type": self.rng.choice([
                "tool.execute",
                "spell.cast", 
                "action.attack",
                "rule.check",
                "system.event",
                self.generate_random_string(3, 20)
            ]),
            "tool_name": self.rng.choice([
                None,
                "dice_roll",
                "spell_check",
                "attack_roll",
                "ability_check",
                self.generate_random_string(3, 20)
            ]),
            "ruleset_version": self.rng.choice([
                None,
                "dnd5e-v1.0",
                "dnd5e-v1.1", 
                "dnd5e-v2.0",
                "pathfinder-v1",
                self.generate_random_string(3, 15)
            ]),
            "args_json": self.rng.choice([
                None,
                {},
                self.generate_random_json(2, 8)
            ])
        }
    
    def test_single_input(self, inputs: Dict[str, Any]) -> bytes:
        """Test a single input and check for collisions."""
        key = compute_idempotency_key_v2(**inputs)
        
        if key in self.generated_keys:
            # Collision detected! Find the original input that generated this key
            self.collision_count += 1
            # Note: In a real implementation, we'd store input->key mapping to show both inputs
            print(f"COLLISION DETECTED! Key: {key.hex()}")
            print(f"New input: {inputs}")
            return key
        
        self.generated_keys.add(key)
        return key
    
    def run_fuzz_test(self, iterations: int) -> Dict[str, Any]:
        """Run fuzz test with specified iterations."""
        print(f"Starting fuzz test with {iterations} iterations...")
        
        # Store input->key mapping for collision analysis  
        input_to_key: Dict[str, bytes] = {}
        key_to_inputs: Dict[bytes, List[Dict[str, Any]]] = defaultdict(list)
        
        for i in range(iterations):
            if i % 1000 == 0:
                print(f"Progress: {i}/{iterations} ({i/iterations*100:.1f}%)")
            
            inputs = self.generate_random_idempotency_input()
            key = compute_idempotency_key_v2(**inputs)
            
            # Track all inputs that generate each key
            key_to_inputs[key].append(inputs)
            
            if len(key_to_inputs[key]) > 1:
                # Collision detected
                self.collision_count += 1
                self.collision_details.append((
                    key_to_inputs[key][0],  # First input
                    inputs  # Colliding input
                ))
        
        return {
            "total_iterations": iterations,
            "unique_keys": len(key_to_inputs),
            "collision_count": self.collision_count,
            "collision_details": self.collision_details,
            "collision_rate": self.collision_count / iterations if iterations > 0 else 0,
        }


@pytest.mark.slow
def test_collision_fuzz_10k_iterations():
    """Fuzz test with 10k iterations to verify collision resistance."""
    tester = IdempotencyCollisionTester(seed=12345)
    results = tester.run_fuzz_test(10_000)
    
    print("\n=== FUZZ TEST RESULTS ===")
    print(f"Total iterations: {results['total_iterations']:,}")
    print(f"Unique keys generated: {results['unique_keys']:,}")
    print(f"Collisions detected: {results['collision_count']}")
    print(f"Collision rate: {results['collision_rate']:.10f}")
    
    # Calculate expected collision probability for 16-byte keys
    # Birthday paradox approximation: P ≈ n²/(2×2^(8×16)) for n trials
    n = results['total_iterations']
    key_space = 2 ** (8 * 16)  # 2^128 for 16-byte keys
    expected_collision_prob = (n * n) / (2 * key_space)
    
    print(f"Expected collision probability: {expected_collision_prob:.2e}")
    print(f"Key space size: 2^128 = {key_space:.2e}")
    
    # The acceptance criteria specify zero collisions for N>=10k
    assert results['collision_count'] == 0, (
        f"Found {results['collision_count']} collisions in {n:,} iterations. "
        f"Expected 0 collisions for acceptance criteria."
    )
    
    # Verify we actually generated diverse keys
    assert results['unique_keys'] == results['total_iterations'], (
        "Each iteration should generate a unique key unless there's a collision"
    )
    
    # Log collision details if any (should be empty for passing test)
    if results['collision_details']:
        print("\n=== COLLISION DETAILS ===")
        for i, (input1, input2) in enumerate(results['collision_details']):
            print(f"Collision #{i+1}:")
            print(f"  Input 1: {input1}")
            print(f"  Input 2: {input2}")
            key1 = compute_idempotency_key_v2(**input1)
            key2 = compute_idempotency_key_v2(**input2)
            print(f"  Same key: {key1.hex()}")
            assert key1 == key2


@pytest.mark.slow  
def test_collision_fuzz_100k_iterations():
    """Extended fuzz test with 100k iterations for thorough validation."""
    tester = IdempotencyCollisionTester(seed=67890)
    results = tester.run_fuzz_test(100_000)
    
    print("\n=== EXTENDED FUZZ TEST RESULTS ===")
    print(f"Total iterations: {results['total_iterations']:,}")
    print(f"Unique keys generated: {results['unique_keys']:,}")
    print(f"Collisions detected: {results['collision_count']}")
    print(f"Collision rate: {results['collision_rate']:.10f}")
    
    # Still expect zero collisions even with 100k iterations
    # 16-byte keys have 2^128 possible values, so collision probability is negligible
    assert results['collision_count'] == 0, (
        f"Found {results['collision_count']} collisions in 100k iterations. "
        f"This suggests a problem with the hash function or key generation."
    )


def test_collision_fuzz_targeted_similar_inputs():
    """Test collision resistance with intentionally similar inputs."""
    tester = IdempotencyCollisionTester(seed=99999)
    
    # Generate variations of the same base input
    base_input = {
        "plan_id": "test-plan-base",
        "campaign_id": 12345,
        "event_type": "tool.execute",
        "tool_name": "dice_roll",
        "ruleset_version": "dnd5e-v1.0",
        "args_json": {"sides": 20, "count": 1}
    }
    
    variations = []
    
    # Create variations by slightly modifying each field
    for i in range(1000):
        variation = base_input.copy()
        
        # Randomly modify one field
        field = tester.rng.choice(list(base_input.keys()))
        
        if field == "plan_id":
            variation[field] = f"test-plan-{i}"
        elif field == "campaign_id":
            variation[field] = 12345 + i
        elif field == "event_type":
            variation[field] = f"tool.execute.{i}"
        elif field == "tool_name":
            variation[field] = f"dice_roll_{i}"
        elif field == "ruleset_version":
            variation[field] = f"dnd5e-v1.{i}"
        elif field == "args_json":
            variation[field] = {"sides": 20, "count": 1, "variation": i}
        
        variations.append(variation)
    
    # Test all variations
    keys = set()
    for i, variation in enumerate(variations):
        key = compute_idempotency_key_v2(**variation)
        
        assert key not in keys, (
            f"Collision detected at variation {i}! "
            f"Input: {variation}, Key: {key.hex()}"
        )
        
        keys.add(key)
    
    print(f"Tested {len(variations)} similar input variations - no collisions found")


def test_collision_fuzz_boundary_conditions():
    """Test collision resistance with boundary condition inputs."""
    boundary_inputs = [
        # Empty/minimal values
        {
            "plan_id": None,
            "campaign_id": 1,
            "event_type": "a",
            "tool_name": None,
            "ruleset_version": None,
            "args_json": None,
        },
        {
            "plan_id": "",
            "campaign_id": 1,
            "event_type": "a",
            "tool_name": "",
            "ruleset_version": "",
            "args_json": {},
        },
        # Maximum length values
        {
            "plan_id": "x" * 1000,
            "campaign_id": 2**31 - 1,  # Max int
            "event_type": "y" * 100,
            "tool_name": "z" * 500,
            "ruleset_version": "v" * 100,
            "args_json": {"long_key_" + "k" * 100: "long_value_" + "v" * 1000},
        },
        # Unicode edge cases
        {
            "plan_id": "🎲🎯🎮",
            "campaign_id": 42,
            "event_type": "test.unicode.🔥",
            "tool_name": "dice_🎲",
            "ruleset_version": "dnd5e-v1.0-🐉",
            "args_json": {"emoji": "🎲", "unicode": "测试", "special": "café"},
        },
        # Numeric edge cases
        {
            "plan_id": "numeric-test",
            "campaign_id": 0,
            "event_type": "boundary.test",
            "tool_name": "boundary_tool",
            "ruleset_version": "v0.0.0",
            "args_json": {"min_int": -2**31, "max_int": 2**31 - 1, "zero": 0},
        },
    ]
    
    keys = set()
    for i, inputs in enumerate(boundary_inputs):
        key = compute_idempotency_key_v2(**inputs)
        
        assert key not in keys, (
            f"Collision detected in boundary condition test {i}! "
            f"Input: {inputs}, Key: {key.hex()}"
        )
        
        keys.add(key)
        
        # Verify key is correct length
        assert len(key) == 16, f"Key should be 16 bytes, got {len(key)}"
    
    print(f"Tested {len(boundary_inputs)} boundary conditions - no collisions found")


if __name__ == "__main__":
    # Allow running the fuzz test directly for development/debugging
    print("Running collision fuzz tests...")
    
    # Quick test
    tester = IdempotencyCollisionTester()
    results = tester.run_fuzz_test(1000)
    print(f"Quick test: {results['collision_count']} collisions in 1000 iterations")
    
    # Standard test
    results = tester.run_fuzz_test(10_000)
    print(f"Standard test: {results['collision_count']} collisions in 10k iterations")
    
    print("Fuzz testing complete!")