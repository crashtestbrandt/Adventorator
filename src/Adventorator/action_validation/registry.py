"""Simple in-memory registry for transient Plans during the rollout."""

from __future__ import annotations

from .schemas import Plan

_PLANS: dict[str, Plan] = {}


def register_plan(plan: Plan) -> None:
    _PLANS[plan.plan_id] = plan


def get_plan(plan_id: str) -> Plan | None:
    return _PLANS.get(plan_id)


def reset() -> None:
    _PLANS.clear()
