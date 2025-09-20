"""Metrics helpers for the action validation rollout."""

from __future__ import annotations

from Adventorator.metrics import inc_counter

from .schemas import Plan


def record_plan_steps(plan: Plan) -> None:
    """Record plan step metrics for observability.

    Emits a counter equal to the number of steps present so that callers can
    understand the shape of generated plans without inspecting the payloads.
    Also emits feasibility counters to distinguish success/failure cases.
    """

    inc_counter("plan.steps.count", len(plan.steps))
    if plan.feasible is True:
        inc_counter("planner.feasible")
    elif plan.feasible is False:
        inc_counter("planner.infeasible")


def record_predicate_gate_outcome(*, ok: bool) -> None:
    """Record predicate gate outcomes.

    Emits success/failure counters. Failure is distinguished from internal
    errors by using `.fail` (explicit predicate failure) vs `.error` (exception
    path callers may raise separately if needed).
    """

    if ok:
        inc_counter("predicate.gate.ok")
    else:
        # Maintain backward compatibility with existing tests expecting predicate.gate.error
        inc_counter("predicate.gate.fail")
        inc_counter("predicate.gate.error")


def record_planner_failure(kind: str) -> None:
    """Record planner failure kinds (parse, allowlist, timeout, arg_validation, other).

    A generic helper so command handlers can uniformly emit counters without
    scattering metric name construction logic.
    """
    safe = kind.replace(" ", "_").replace("/", "_")
    inc_counter(f"planner.failure.{safe}")
