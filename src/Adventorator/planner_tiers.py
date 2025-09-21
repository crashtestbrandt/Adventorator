"""Tiered planning scaffolding.

Level 1: single-step (current behavior)
Level 2+: reserved for future HTN/GOAP style expansions.

All higher-level expansions currently return the original single step and emit
structured log events so tests can assert placeholder behavior deterministically.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from Adventorator.action_validation.schemas import Plan, PlanStep
from Adventorator.config import Settings

log = structlog.get_logger()


def resolve_planning_level(settings: Settings | None) -> int:
    """Return the effective planning level.

    Logic:
    - If feature flag `features_planning_tiers` is false: always 1.
    - Else clamp requested max_level (planner_max_level) to >=1.
    """
    if settings is None:
        return 1
    if not getattr(settings, "features_planning_tiers", False):
        return 1
    max_level = int(getattr(settings, "planner_max_level", 1) or 1)
    if max_level < 1:
        max_level = 1
    return max_level


def expand_plan(plan: Plan, level: int) -> Plan:
    """Expand a Plan to the requested level.

    Current behavior:
    - Level <=1: return unchanged (single-step baseline).
    - Level >=2: If exactly one existing step, produce a trivial two-step sequence
      by injecting a deterministic preparation step ahead of the original.
      This is a reversible scaffold to exercise multi-step serialization and metrics
      without introducing domain complexity. Further HTN/GOAP decomposition will
      replace this logic in later stories.
    """
    if level <= 1:
        return plan
    if len(plan.steps) == 1:
        original = plan.steps[0]
        prep = PlanStep(op="prepare." + original.op.split(".")[0], args={})
        new_steps = [prep, original]
        new_plan = plan.model_copy(update={"steps": new_steps})
        log.info(
            "planner.tier.expansion.level2_applied",
            requested_level=level,
            new_steps=len(new_steps),
        )
        return new_plan
    else:  # pragma: no cover - future-proof branch
        log.info(
            "planner.tier.expansion.noop",
            requested_level=level,
            steps=len(plan.steps),
        )
    return plan


def guards_for_steps(steps: Sequence[PlanStep], *, tiers_enabled: bool = False) -> None:
    """Populate guards metadata.

    Deterministic rule for this story:
    - If tiers are enabled (feature flag on), add a baseline capability guard to each step
      if not already present. This validates populated serialization + metrics without
      leaking future predicate semantics prematurely.
    - If tiers disabled: leave guards unchanged (usually empty) to preserve rollback parity.
    """
    if not tiers_enabled:
        return None
    for step in steps:
        if "capability:basic_action" not in step.guards:
            step.guards.append("capability:basic_action")
    return None
