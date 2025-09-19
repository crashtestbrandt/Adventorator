"""Predicate Gate implementation for the planner pipeline (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.planner_schemas import PlannerOutput
from Adventorator.rules.checks import ABILS


@dataclass(frozen=True)
class PredicateFailure:
    """Normalized representation of a predicate failure."""

    code: str
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {"predicate": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


@dataclass(frozen=True)
class PredicateContext:
    """Context provided to the predicate gate."""

    campaign_id: int
    scene_id: int
    user_id: int | None = None
    allowed_actors: Sequence[str] = ()


@dataclass(frozen=True)
class PredicateGateResult:
    ok: bool
    failed: list[PredicateFailure] = field(default_factory=list)


async def evaluate_predicates(
    output: PlannerOutput, *, context: PredicateContext
) -> PredicateGateResult:
    """Evaluate deterministic predicates against the planner output."""

    args = dict(output.args or {})
    failures: list[PredicateFailure] = []

    ability = _extract_ability(args)
    if ability is not None:
        ability_norm = ability.upper()
        if ability_norm not in ABILS:
            failures.append(
                PredicateFailure(
                    code="known_ability",
                    message=f"Unknown ability '{ability}'.",
                    detail={"ability": ability},
                )
            )

    dc = _extract_dc(args)
    if dc is not None:
        if dc < 1 or dc > 40:
            failures.append(
                PredicateFailure(
                    code="dc_in_bounds",
                    message="Difficulty class must be between 1 and 40.",
                    detail={"dc": dc},
                )
            )

    allowed_lookup = {_normalize_name(a): a for a in context.allowed_actors if a}

    actor = _extract_actor(args)
    actor_norm = _normalize_name(actor) if actor else None
    if actor and actor_norm:
        if allowed_lookup and actor_norm not in allowed_lookup:
            failures.append(
                PredicateFailure(
                    code="actor_in_allowed_actors",
                    message=f"Actor '{actor}' is not part of the active scene.",
                    detail={"actor": actor},
                )
            )
        if context.campaign_id:
            exists = await _character_exists(actor, context.campaign_id)
            if not exists:
                failures.append(
                    PredicateFailure(
                        code="exists(actor)",
                        message=f"Actor '{actor}' was not found in this campaign.",
                        detail={"actor": actor},
                    )
                )

    target = _extract_target(args)
    if target and context.campaign_id:
        exists = await _character_exists(target, context.campaign_id)
        if not exists:
            failures.append(
                PredicateFailure(
                    code="exists(target)",
                    message=f"Target '{target}' was not found in this campaign.",
                    detail={"target": target},
                )
            )

    return PredicateGateResult(ok=not failures, failed=failures)


def _extract_actor(args: Mapping[str, Any]) -> str | None:
    for key in ("actor", "actor_id", "character", "character_name"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_target(args: Mapping[str, Any]) -> str | None:
    for key in ("target", "target_ref", "target_name"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_ability(args: Mapping[str, Any]) -> str | None:
    value = args.get("ability")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_dc(args: Mapping[str, Any]) -> int | None:
    value = args.get("dc")
    try:
        if value is None:
            return None
        parsed = int(value)
        return parsed
    except Exception:
        return None


def _normalize_name(name: str | None) -> str | None:
    if not name:
        return None
    return name.strip().lower()


async def _character_exists(name: str, campaign_id: int) -> bool:
    if not name:
        return False
    try:
        async with session_scope() as session:
            character = await repos.get_character(session, campaign_id, name)
            return character is not None
    except Exception:
        # Fail open on repository errors to avoid false negatives.
        return True
