"""Tests for canonical JSON encoder (STORY-CDA-CORE-001B)."""

import unicodedata
from pathlib import Path

import pytest

from Adventorator.canonical_json import (
    CanonicalJSONError,
    canonical_json_bytes,
    compute_canonical_hash,
)


class TestKeyOrdering:
    """Test deterministic key ordering."""

    def test_keys_sorted_lexicographically(self):
        # Same logical content, different key order
        payload1 = {"z": 1, "a": 2, "m": 3}
        payload2 = {"a": 2, "m": 3, "z": 1}
        payload3 = {"m": 3, "z": 1, "a": 2}
        
        result1 = canonical_json_bytes(payload1)
        result2 = canonical_json_bytes(payload2)
        result3 = canonical_json_bytes(payload3)
        
        # All should produce identical bytes
        assert result1 == result2 == result3
        assert result1 == b'{"a":2,"m":3,"z":1}'

    def test_nested_objects_keys_sorted(self):
        payload = {
            "outer_z": {"inner_b": 1, "inner_a": 2},
            "outer_a": {"inner_z": 3, "inner_m": 4},
        }
        
        result = canonical_json_bytes(payload)
        expected = b'{"outer_a":{"inner_m":4,"inner_z":3},"outer_z":{"inner_a":2,"inner_b":1}}'
        assert result == expected

    def test_hash_identical_for_different_key_orders(self):
        payload1 = {"campaign_id": 123, "event_type": "test", "actor": "player1"}
        payload2 = {"event_type": "test", "actor": "player1", "campaign_id": 123}
        
        hash1 = compute_canonical_hash(payload1)
        hash2 = compute_canonical_hash(payload2)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # SHA-256 produces 32 bytes


class TestUnicodeNormalization:
    """Test UTF-8 NFC normalization."""

    def test_nfc_normalization_composed_vs_decomposed(self):
        # é can be represented as:
        # 1. Single character (NFC): é (U+00E9) 
        # 2. Decomposed (NFD): e + ́ (U+0065 + U+0301)
        composed = "café"  # NFC form
        decomposed = unicodedata.normalize("NFD", composed)  # NFD form
        
        assert composed != decomposed  # Different Unicode representations
        
        payload1 = {"name": composed}
        payload2 = {"name": decomposed}
        
        result1 = canonical_json_bytes(payload1)
        result2 = canonical_json_bytes(payload2)
        
        # Should produce identical output after NFC normalization
        assert result1 == result2

    def test_unicode_hash_stability(self):
        # Various Unicode forms should hash identically after normalization
        text_nfc = "naïve"
        text_nfd = unicodedata.normalize("NFD", text_nfc)
        text_nfkc = unicodedata.normalize("NFKC", text_nfc)
        
        payload_nfc = {"description": text_nfc}
        payload_nfd = {"description": text_nfd}
        payload_nfkc = {"description": text_nfkc}
        
        hash_nfc = compute_canonical_hash(payload_nfc)
        hash_nfd = compute_canonical_hash(payload_nfd)
        hash_nfkc = compute_canonical_hash(payload_nfkc)
        
        # NFC and NFD should normalize to same result
        assert hash_nfc == hash_nfd
        # NFKC might be different due to compatibility decomposition
        # but our normalizer uses NFC so it should also match
        assert hash_nfc == hash_nfkc

    def test_unicode_keys_normalized(self):
        # Unicode in keys should also be normalized
        key_composed = "café"
        key_decomposed = unicodedata.normalize("NFD", key_composed)
        
        payload1 = {key_composed: "value"}
        payload2 = {key_decomposed: "value"}
        
        result1 = canonical_json_bytes(payload1)
        result2 = canonical_json_bytes(payload2)
        
        assert result1 == result2


class TestNullElision:
    """Test null value omission."""

    def test_null_values_omitted(self):
        payload = {
            "keep": "value",
            "remove": None,
            "also_keep": 42,
            "also_remove": None,
        }
        
        result = canonical_json_bytes(payload)
        # Only non-null values should remain
        expected = b'{"also_keep":42,"keep":"value"}'
        assert result == expected

    def test_nested_null_elision(self):
        payload = {
            "outer": {
                "inner_keep": "value",
                "inner_remove": None,
                "nested": {
                    "deep_keep": 123,
                    "deep_remove": None,
                }
            },
            "top_remove": None,
        }
        
        result = canonical_json_bytes(payload)
        expected = b'{"outer":{"inner_keep":"value","nested":{"deep_keep":123}}}'
        assert result == expected

    def test_null_in_arrays_preserved(self):
        # Per ADR-0007, arrays preserve order and null elements
        payload = {
            "array": [1, None, 3, None, 5]
        }
        
        result = canonical_json_bytes(payload)
        expected = b'{"array":[1,null,3,null,5]}'
        assert result == expected

    def test_empty_object_after_null_elision(self):
        payload = {
            "empty_after_elision": {"all": None, "fields": None, "null": None},
            "keep": "value"
        }
        
        result = canonical_json_bytes(payload)
        # Empty object should remain after null elision
        expected = b'{"empty_after_elision":{},"keep":"value"}'
        assert result == expected


class TestNumericPolicy:
    """Test integer-only numeric validation."""

    def test_integers_accepted(self):
        payload = {
            "small": 42,
            "negative": -123,
            "zero": 0,
            "large": 9223372036854775807,  # Max int64
            "large_negative": -9223372036854775808,  # Min int64
        }
        
        result = canonical_json_bytes(payload)
        # Should not raise an exception
        assert b"42" in result
        assert b"-123" in result

    def test_float_rejected_with_helpful_error(self):
        payload = {"invalid": 3.14}
        
        with pytest.raises(CanonicalJSONError) as exc_info:
            canonical_json_bytes(payload)
        
        error_msg = str(exc_info.value)
        assert "Float values not permitted" in error_msg
        assert "fixed-point representation" in error_msg
        assert "multiply by 100" in error_msg

    def test_nan_rejected_with_helpful_error(self):
        payload = {"invalid": float("nan")}
        
        with pytest.raises(CanonicalJSONError) as exc_info:
            canonical_json_bytes(payload)
        
        error_msg = str(exc_info.value)
        assert "NaN values not permitted" in error_msg
        assert "null or a string representation" in error_msg

    def test_infinity_rejected_with_helpful_error(self):
        payload = {"invalid": float("inf")}
        
        with pytest.raises(CanonicalJSONError) as exc_info:
            canonical_json_bytes(payload)
        
        error_msg = str(exc_info.value)
        assert "Infinity values not permitted" in error_msg

    def test_large_integer_rejected(self):
        # Beyond signed 64-bit range
        payload = {"too_large": 9223372036854775808}  # Max int64 + 1
        
        with pytest.raises(CanonicalJSONError) as exc_info:
            canonical_json_bytes(payload)
        
        error_msg = str(exc_info.value)
        assert "outside signed 64-bit range" in error_msg
        assert "strings in non-semantic fields" in error_msg

    def test_integer_disguised_as_float_accepted(self):
        # Some APIs might return 42.0 instead of 42
        payload = {"value": 42.0}
        
        result = canonical_json_bytes(payload)
        # Should be converted to integer
        assert result == b'{"value":42}'


class TestGoldenVectors:
    """Test against golden vector fixtures."""

    @pytest.fixture
    def golden_vectors_dir(self):
        return Path(__file__).parent / "golden" / "canonical_json"

    def test_golden_vector_1_empty_object(self, golden_vectors_dir):
        """Empty object should match genesis payload."""
        payload = {}
        result = canonical_json_bytes(payload)
        hash_result = compute_canonical_hash(payload)
        
        hash_file = golden_vectors_dir / "01_empty_object.sha256"
        
        assert result == b"{}"
        
        # Check against stored hash if files exist
        if hash_file.exists():
            expected_hash = bytes.fromhex(hash_file.read_text().strip())
            assert hash_result == expected_hash

    def test_golden_vector_2_key_ordering(self, golden_vectors_dir):
        """Complex key ordering test."""
        payload = {
            "zebra": 1,
            "alpha": 2,
            "beta": {"gamma": 3, "delta": 4},
            "charlie": [1, 2, {"zulu": 5, "alpha": 6}]
        }
        
        result = canonical_json_bytes(payload)
        
        # Keys should be sorted at every level
        expected = (
            b'{"alpha":2,"beta":{"delta":4,"gamma":3},'
            b'"charlie":[1,2,{"alpha":6,"zulu":5}],"zebra":1}'
        )
        assert result == expected

    def test_golden_vector_3_unicode_normalization(self, golden_vectors_dir):
        """Unicode normalization test with accented characters."""
        # Mix of composed and decomposed forms
        composed_e = "é"  # U+00E9
        decomposed_e = "é"  # U+0065 + U+0301
        
        payload = {
            "composed": composed_e + "clair",
            "decomposed": decomposed_e + "clair",
            "mixed": {"key_" + composed_e: "value_" + decomposed_e}
        }
        
        result = canonical_json_bytes(payload)
        # All forms should normalize to the same NFC representation
        assert result.count(b"\xc3\xa9") >= 3  # UTF-8 encoding of é (NFC form)

    def test_golden_vector_4_null_elision(self, golden_vectors_dir):
        """Comprehensive null elision test."""
        payload = {
            "keep_string": "value",
            "remove_null": None,
            "keep_number": 42,
            "keep_boolean": True,
            "nested": {
                "keep_nested": "nested_value",
                "remove_nested_null": None,
                "keep_array": [1, None, 3],  # nulls in arrays are preserved
            },
            "remove_top_null": None,
        }
        
        result = canonical_json_bytes(payload)
        expected = (
            b'{"keep_boolean":true,"keep_number":42,"keep_string":"value",'
            b'"nested":{"keep_array":[1,null,3],"keep_nested":"nested_value"}}'
        )
        assert result == expected

    def test_golden_vector_5_edge_case_integers(self, golden_vectors_dir):
        """Edge case integer values."""
        payload = {
            "max_int64": 9223372036854775807,
            "min_int64": -9223372036854775808,
            "zero": 0,
            "small_positive": 1,
            "small_negative": -1,
        }
        
        result = canonical_json_bytes(payload)
        hash_result = compute_canonical_hash(payload)
        
        # Should not raise an exception and produce deterministic output
        assert len(result) > 0
        assert len(hash_result) == 32


class TestBackwardCompatibility:
    """Test compatibility with existing envelope functions."""

    def test_genesis_payload_compatibility(self):
        """Ensure new encoder produces same result as existing genesis hash."""
        from Adventorator.events.envelope import GENESIS_PAYLOAD, GENESIS_PAYLOAD_HASH
        
        # Our new encoder should produce the same hash for empty dict
        new_hash = compute_canonical_hash(GENESIS_PAYLOAD)
        assert new_hash == GENESIS_PAYLOAD_HASH

    def test_canonical_bytes_compatibility(self):
        """Ensure new encoder bytes match existing canonical bytes for simple cases."""
        from Adventorator.events.envelope import canonical_json_bytes as old_canonical
        
        # For simple cases without Unicode issues, should match
        simple_payload = {"a": 1, "b": 2}
        
        old_result = old_canonical(simple_payload)
        new_result = canonical_json_bytes(simple_payload)
        
        # Both should produce same result for simple ASCII cases
        assert new_result == old_result


class TestErrorHandling:
    """Test error conditions and edge cases."""

    def test_unsupported_types_rejected(self):
        import datetime
        
        payload = {"date": datetime.datetime.now()}
        
        with pytest.raises(CanonicalJSONError) as exc_info:
            canonical_json_bytes(payload)
        
        assert "Unsupported type" in str(exc_info.value)

    def test_none_payload_treated_as_empty_dict(self):
        result = canonical_json_bytes(None)
        assert result == b"{}"

    def test_empty_string_keys_handled(self):
        payload = {"": "empty_key", "normal": "value"}
        
        result = canonical_json_bytes(payload)
        # Empty string key should be sorted first
        assert result == b'{"":"empty_key","normal":"value"}'