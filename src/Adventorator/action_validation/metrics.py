"""Metrics helpers for the action validation rollout."""

from __future__ import annotations

from Adventorator.metrics import inc_counter

from .schemas import Plan


def record_plan_steps(plan: Plan) -> None:
    """Record plan step metrics for observability.

    Emits a counter equal to the number of steps present so that callers can
    understand the shape of generated plans without inspecting the payloads.
    """

    inc_counter("plan.steps.count", len(plan.steps))


def record_predicate_gate_outcome(*, ok: bool) -> None:
    """Record predicate gate outcomes.

    The gate implementation can call this helper to track allow/deny decisions
    without taking a dependency on the metrics module directly. Using a keyword
    argument makes the call sites self-documenting when more metadata is added
    later.
    """

    if ok:
        inc_counter("predicate.gate.ok")
    else:
        inc_counter("predicate.gate.error")
