"""Minimal in-process metrics shim for counters and timers.

This is intentionally simple; production can replace these with a real backend.
"""
from __future__ import annotations

from collections import defaultdict

_counters: dict[str, int] = defaultdict(int)


def inc_counter(name: str, value: int = 1) -> None:
    _counters[name] += int(value)


def get_counter(name: str) -> int:
    return _counters.get(name, 0)


def reset_counters() -> None:
    _counters.clear()


def get_counters() -> dict[str, int]:
    """Return a shallow copy of all counters for diagnostics."""
    return dict(_counters)
