"""Minimal in-process metrics shim for counters and timers.

This is intentionally simple; production can replace these with a real backend.

Adds a lightweight histogram helper with fixed or custom buckets. Values are
exported into flattened counters for the /metrics endpoint to keep payloads
simple and avoid changing types in existing consumers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

# Note: Avoid heavy imports at module import time; import test-only helpers lazily.

_counters: dict[str, int] = defaultdict(int)
_histograms: dict[str, dict[str, int]] = {}
_hist_sums: dict[str, int] = defaultdict(int)
_hist_counts: dict[str, int] = defaultdict(int)
_reset_plan_cache_cb: Callable[[], None] | None = None


def inc_counter(name: str, value: int = 1) -> None:
    _counters[name] += int(value)


def register_reset_plan_cache_callback(callback: Callable[[], None]) -> None:
    """Register a callback used to clear the planner cache when metrics reset."""

    global _reset_plan_cache_cb
    _reset_plan_cache_cb = callback


def get_counter(name: str) -> int:
    return _counters.get(name, 0)


def reset_counters() -> None:
    _counters.clear()
    _histograms.clear()
    _hist_sums.clear()
    _hist_counts.clear()
    # Also clear the planner cache to prevent cross-test cache hits when
    # tests expect a clean slate after calling reset_counters().
    if _reset_plan_cache_cb is not None:
        try:
            _reset_plan_cache_cb()
        except Exception:
            # If the callback fails in some contexts, ignore silently.
            pass
    try:
        from Adventorator.action_validation import plan_registry

        plan_registry.reset()
    except Exception:
        pass
    # Also clear per-user planner rate limiter (plan command) so prior tests
    # do not cause inadvertent rate-limit early returns in cache metric tests.
    try:
        from Adventorator.commands import plan as _plan_module  # type: ignore

        if hasattr(_plan_module, "_rl") and isinstance(_plan_module._rl, dict):  # noqa: SLF001
            _plan_module._rl.clear()  # noqa: SLF001
    except Exception:
        pass


def get_counters() -> dict[str, int]:
    """Return a shallow copy of all counters for diagnostics."""
    out = dict(_counters)
    # Flatten histograms as counters for easy scraping
    for name, buckets in _histograms.items():
        for b_lbl, cnt in buckets.items():
            out[f"histo.{name}.{b_lbl}"] = cnt
        out[f"histo.{name}.sum"] = _hist_sums.get(name, 0)
        out[f"histo.{name}.count"] = _hist_counts.get(name, 0)
    return out


def observe_histogram(name: str, value: int, *, buckets: list[int] | None = None) -> None:
    """Record a value in a histogram with <=-style buckets.

    - buckets: the upper bounds for each bucket in milliseconds. Defaults to
      [1, 2, 5, 10, 20, 50, 100, 250, 500, 1000, 2000, 5000].
    - We also emit an overflow bucket labeled 'gt_{last}'.
    """
    if buckets is None:
        buckets = [1, 2, 5, 10, 20, 50, 100, 250, 500, 1000, 2000, 5000]
    h = _histograms.setdefault(name, {})
    placed = False
    for ub in buckets:
        if value <= ub:
            key = f"le_{ub}"
            h[key] = h.get(key, 0) + 1
            placed = True
            break
    if not placed:
        key = f"gt_{buckets[-1]}"
        h[key] = h.get(key, 0) + 1
    _hist_sums[name] += int(value)
    _hist_counts[name] += 1


# Convenience functions for STORY-CDA-CORE-001E event metrics

def record_event_conflict() -> None:
    """Record an event conflict (placeholder until executor implementation)."""
    inc_counter("events.conflict")


def record_idempotent_reuse() -> None:
    """Record event idempotency reuse."""
    inc_counter("events.idempotent_reuse")
