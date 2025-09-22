"""Canonical JSON encoder implementing ADR-0007 specification.

This module provides deterministic JSON encoding with:
- UTF-8 NFC Unicode normalization
- Lexicographic key ordering
- Null field elision
- Integer-only numeric policy (rejects floats/NaN)
- SHA-256 hash computation helper

Ensures stable cross-platform hashing for event payloads and idempotency keys.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from typing import Any


class CanonicalJSONError(ValueError):
    """Raised when input violates canonical JSON constraints."""

    pass


def _normalize_unicode(value: str) -> str:
    """Normalize Unicode string to NFC form per ADR-0007."""
    return unicodedata.normalize("NFC", value)


def _validate_number(value: int | float) -> int:
    """Validate numeric value meets integer-only policy.
    
    Args:
        value: Number to validate
        
    Returns:
        The validated integer value
        
    Raises:
        CanonicalJSONError: If value is float, NaN, infinity, or outside signed 64-bit range
    """
    if isinstance(value, float):
        if math.isnan(value):
            raise CanonicalJSONError(
                "NaN values not permitted in canonical JSON. "
                "Consider using null or a string representation."
            )
        if math.isinf(value):
            raise CanonicalJSONError(
                "Infinity values not permitted in canonical JSON. "
                "Consider using a large integer or string representation."
            )
        # Check if it's actually an integer disguised as float
        if value.is_integer():
            value = int(value)
        else:
            raise CanonicalJSONError(
                f"Float values not permitted in canonical JSON: {value}. "
                "Convert to integer, use fixed-point representation (multiply by 100), "
                "or store as string for non-semantic fields."
            )
    
    if isinstance(value, int):
        # Check signed 64-bit range: -2^63 to 2^63-1
        if value < -9223372036854775808 or value > 9223372036854775807:
            raise CanonicalJSONError(
                f"Integer {value} outside signed 64-bit range. "
                "Large integers must be stored as strings in non-semantic fields."
            )
        return value
    
    raise CanonicalJSONError(f"Unexpected numeric type: {type(value)}")


def _canonicalize_value(value: Any) -> Any:
    """Recursively canonicalize a JSON value per ADR-0007 rules.
    
    Args:
        value: JSON-compatible value to canonicalize
        
    Returns:
        Canonicalized value with:
        - Unicode strings normalized to NFC
        - Numbers validated as integers within 64-bit range
        - Null values removed from objects
        - Object keys sorted lexicographically
        
    Raises:
        CanonicalJSONError: If value violates canonical constraints
    """
    if value is None:
        return None
    elif isinstance(value, bool):
        return value
    elif isinstance(value, str):
        return _normalize_unicode(value)
    elif isinstance(value, int | float):
        return _validate_number(value)
    elif isinstance(value, list):
        return [_canonicalize_value(item) for item in value]
    elif isinstance(value, dict):
        # Elide null values and sort keys
        result = {}
        for key, val in value.items():
            if val is not None:
                canonical_val = _canonicalize_value(val)
                if canonical_val is not None:
                    # Normalize key as well
                    canonical_key = _normalize_unicode(str(key))
                    result[canonical_key] = canonical_val
        return result
    else:
        raise CanonicalJSONError(
            f"Unsupported type {type(value)} in canonical JSON. "
            "Only dict, list, str, int, bool, and null are permitted."
        )


def canonical_json_bytes(payload: Mapping[str, Any] | None) -> bytes:
    """Encode payload as canonical JSON bytes per ADR-0007.
    
    Args:
        payload: Dictionary to encode, or None (treated as empty dict)
        
    Returns:
        UTF-8 encoded canonical JSON bytes with:
        - Keys sorted lexicographically
        - Unicode normalized to NFC form
        - Null fields omitted
        - Compact separators (no whitespace)
        - Integer-only numbers
        
    Raises:
        CanonicalJSONError: If payload contains invalid types or values
    """
    if payload is None:
        payload = {}
    
    # Canonicalize the entire payload structure
    canonical_payload = _canonicalize_value(payload)
    
    # Encode with deterministic settings
    json_str = json.dumps(
        canonical_payload,
        ensure_ascii=False,  # Allow Unicode characters
        separators=(",", ":"),  # Compact format
        sort_keys=True,  # Lexicographic key ordering
        allow_nan=False,  # Reject NaN/Infinity (redundant with validation)
    )
    
    # Normalize the entire JSON string and encode as UTF-8
    return _normalize_unicode(json_str).encode("utf-8")


def compute_canonical_hash(payload: Mapping[str, Any] | None) -> bytes:
    """Compute SHA-256 hash of canonical JSON representation.
    
    Args:
        payload: Dictionary to hash, or None (treated as empty dict)
        
    Returns:
        32-byte SHA-256 digest of canonical JSON encoding
        
    Raises:
        CanonicalJSONError: If payload contains invalid types or values
    """
    canonical_bytes = canonical_json_bytes(payload)
    return hashlib.sha256(canonical_bytes).digest()


__all__ = [
    "CanonicalJSONError",
    "canonical_json_bytes", 
    "compute_canonical_hash",
]