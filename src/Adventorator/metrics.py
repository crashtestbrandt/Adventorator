"""Minimal in-process metrics shim for counters and timers.

This is intentionally simple; production can replace these with a real backend.
"""
from __future__ import annotations

from collections import defaultdict

# Note: Avoid heavy imports at module import time; import test-only helpers lazily.

_counters: dict[str, int] = defaultdict(int)


def inc_counter(name: str, value: int = 1) -> None:
    _counters[name] += int(value)


def get_counter(name: str) -> int:
    return _counters.get(name, 0)


def reset_counters() -> None:
    _counters.clear()
    # Also clear the planner cache to prevent cross-test cache hits when
    # tests expect a clean slate after calling reset_counters().
    try:
        from Adventorator.planner import reset_plan_cache  # local import to avoid cycles

        reset_plan_cache()
    except Exception:
        # If planner isn't importable in some contexts, ignore silently.
        pass


def get_counters() -> dict[str, int]:
    """Return a shallow copy of all counters for diagnostics."""
    return dict(_counters)
