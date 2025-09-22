"""Golden vector tests for canonical JSON encoder (STORY-CDA-CORE-001B).

This module contains tests that verify the canonical JSON encoder produces
identical output to precomputed golden vectors, ensuring no accidental drift
in the canonicalization algorithm.
"""

import json
from pathlib import Path

import pytest

from Adventorator.canonical_json import canonical_json_bytes, compute_canonical_hash


class TestGoldenVectors:
    """Test canonical JSON encoder against stored golden vectors."""

    @pytest.fixture
    def golden_dir(self):
        return Path(__file__).parent / "golden" / "canonical_json"

    def _test_golden_vector(self, golden_dir: Path, vector_name: str, payload: dict):
        """Helper to test a golden vector against stored files."""
        # Compute current results
        canonical_bytes = canonical_json_bytes(payload)
        hash_bytes = compute_canonical_hash(payload)
        
        # Check against stored canonical bytes
        canonical_file = golden_dir / f"{vector_name}.canonical"
        if canonical_file.exists():
            expected_bytes = canonical_file.read_bytes()
            assert canonical_bytes == expected_bytes, f"Canonical bytes mismatch for {vector_name}"
        
        # Check against stored hash
        hash_file = golden_dir / f"{vector_name}.sha256"
        if hash_file.exists():
            expected_hash = bytes.fromhex(hash_file.read_text().strip())
            assert hash_bytes == expected_hash, f"Hash mismatch for {vector_name}"

    def test_vector_01_empty_object(self, golden_dir):
        """Empty object (genesis payload compatibility)."""
        payload = {}
        self._test_golden_vector(golden_dir, "01_empty_object", payload)
        
        # Extra validation - should match genesis hash
        from Adventorator.events.envelope import GENESIS_PAYLOAD_HASH
        hash_bytes = compute_canonical_hash(payload)
        assert hash_bytes == GENESIS_PAYLOAD_HASH

    def test_vector_02_simple_keys(self, golden_dir):
        """Simple key ordering test."""
        payload = {"z": 1, "a": 2, "m": 3}
        self._test_golden_vector(golden_dir, "02_simple_keys", payload)
        
        # Verify canonical output format
        result = canonical_json_bytes(payload)
        assert result == b'{"a":2,"m":3,"z":1}'

    def test_vector_03_unicode_normalization(self, golden_dir):
        """Unicode NFC normalization test."""
        payload = {"café": "naïve", "key_é": "value_ë"}
        self._test_golden_vector(golden_dir, "03_unicode_normalization", payload)

    def test_vector_04_null_elision(self, golden_dir):
        """Null field elision test."""
        payload = {
            "keep": "value",
            "remove": None,
            "nested": {
                "keep_nested": "val",
                "remove_nested": None
            }
        }
        self._test_golden_vector(golden_dir, "04_null_elision", payload)
        
        # Verify null fields are omitted
        result = canonical_json_bytes(payload)
        assert b"remove" not in result
        assert b"remove_nested" not in result

    def test_vector_05_nested_objects(self, golden_dir):
        """Nested object key ordering test."""
        payload = {
            "outer_z": {"inner_b": 1, "inner_a": 2},
            "outer_a": {"inner_z": 3, "inner_m": 4}
        }
        self._test_golden_vector(golden_dir, "05_nested_objects", payload)

    def test_vector_06_arrays_preserved(self, golden_dir):
        """Array order preservation with null elements."""
        payload = {"mixed": [1, None, "string", {"nested": "object"}]}
        self._test_golden_vector(golden_dir, "06_arrays_preserved", payload)
        
        # Verify null in array is preserved
        result = canonical_json_bytes(payload)
        assert b"null" in result

    def test_vector_07_edge_integers(self, golden_dir):
        """Edge case integer values."""
        payload = {
            "max_int64": 9223372036854775807,
            "min_int64": -9223372036854775808,
            "zero": 0
        }
        self._test_golden_vector(golden_dir, "07_edge_integers", payload)

    def test_vector_08_boolean_values(self, golden_dir):
        """Boolean value canonicalization."""
        payload = {"true_val": True, "false_val": False, "number": 42}
        self._test_golden_vector(golden_dir, "08_boolean_values", payload)
        
        # Verify lowercase boolean representation
        result = canonical_json_bytes(payload)
        assert b"true" in result
        assert b"false" in result
        assert b"True" not in result
        assert b"False" not in result

    def test_vector_09_complex_mixed(self, golden_dir):
        """Complex structure with mixed types."""
        payload = {
            "users": [
                {"name": "Alice", "active": True},
                {"name": "Bob", "active": False}
            ],
            "metadata": {
                "version": 1,
                "created": None  # Should be elided
            }
        }
        self._test_golden_vector(golden_dir, "09_complex_mixed", payload)

    def test_vector_10_large_structure(self, golden_dir):
        """Large nested structure."""
        payload = {
            "campaigns": {
                "123": {
                    "players": ["Alice", "Bob"],
                    "status": "active"
                },
                "456": {
                    "players": ["Charlie"],
                    "status": "pending"
                }
            },
            "system": {
                "version": 2
            }
        }
        self._test_golden_vector(golden_dir, "10_large_structure", payload)

    def test_all_golden_vectors_deterministic(self, golden_dir):
        """Verify all golden vectors produce deterministic results across multiple runs."""
        vector_files = list(golden_dir.glob("*.json"))
        assert len(vector_files) >= 10, "Should have at least 10 golden vectors"
        
        for json_file in vector_files:
            with open(json_file) as f:
                payload = json.load(f)
            
            # Run multiple times to ensure determinism
            results = []
            hashes = []
            for _ in range(3):
                results.append(canonical_json_bytes(payload))
                hashes.append(compute_canonical_hash(payload))
            
            # All results should be identical
            assert all(r == results[0] for r in results), (
                f"Non-deterministic output for {json_file.name}"
            )
            assert all(h == hashes[0] for h in hashes), (
                f"Non-deterministic hash for {json_file.name}"
            )

    def test_golden_vector_hash_integrity(self, golden_dir):
        """Verify all stored hashes are valid SHA-256 hashes."""
        hash_files = list(golden_dir.glob("*.sha256"))
        assert len(hash_files) >= 10, "Should have at least 10 hash files"
        
        for hash_file in hash_files:
            hash_hex = hash_file.read_text().strip()
            
            # Should be valid hex string of correct length
            assert len(hash_hex) == 64, f"Invalid hash length in {hash_file.name}"
            try:
                bytes.fromhex(hash_hex)
            except ValueError:
                pytest.fail(f"Invalid hex format in {hash_file.name}")

    def test_key_ordering_regression(self):
        """Regression test for key ordering with complex nested structures."""
        # This test specifically guards against key ordering bugs
        payload = {
            "zzz": {"nnn": 1, "aaa": 2},
            "aaa": {"zzz": 3, "mmm": 4},
            "mmm": ["z", "a", {"zzz": 5, "aaa": 6}]
        }
        
        result = canonical_json_bytes(payload)
        decoded = json.loads(result.decode())
        
        # Verify top-level keys are sorted
        keys = list(decoded.keys())
        assert keys == sorted(keys)
        
        # Verify nested object keys are sorted
        for value in decoded.values():
            if isinstance(value, dict):
                nested_keys = list(value.keys())
                assert nested_keys == sorted(nested_keys)

    def test_unicode_regression(self):
        """Regression test for Unicode normalization."""
        import unicodedata
        
        # Create payload with mixed Unicode forms
        composed = "café"
        decomposed = unicodedata.normalize("NFD", composed)
        
        payload1 = {"key": composed}
        payload2 = {"key": decomposed}
        
        # Should produce identical results
        result1 = canonical_json_bytes(payload1)
        result2 = canonical_json_bytes(payload2)
        hash1 = compute_canonical_hash(payload1)
        hash2 = compute_canonical_hash(payload2)
        
        assert result1 == result2
        assert hash1 == hash2