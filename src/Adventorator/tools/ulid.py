from __future__ import annotations

"""Minimal ULID generator (Crockford base32), no external dependencies.

ULID spec:
- 128-bit value = 48-bit timestamp (ms since UNIX epoch) + 80-bit randomness
- Crockford base32 alphabet: 0123456789ABCDEFGHJKMNPQRSTVWXYZ
"""

import os
import time
from typing import Final

_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    chars.reverse()
    return "".join(chars)


def generate_ulid(ts_ms: int | None = None) -> str:
    """Generate a 26-char ULID string.

    Args:
        ts_ms: Optional timestamp in milliseconds; defaults to current time
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    # 48-bit timestamp
    ts = ts_ms & ((1 << 48) - 1)
    # 80-bit randomness
    rnd_bytes = os.urandom(10)  # 80 bits
    rnd = int.from_bytes(rnd_bytes, "big")
    # Compose 128-bit integer
    value = (ts << 80) | rnd
    return _encode_base32(value, 26)


def is_ulid(s: str) -> bool:
    if len(s) != 26:
        return False
    # Must start with a digit (time-ordered property)
    if not s[0].isdigit():
        return False
    for ch in s:
        if ch not in _ALPHABET:
            return False
    return True
