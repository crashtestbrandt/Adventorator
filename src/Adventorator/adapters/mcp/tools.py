"""Framework-agnostic MCP tool handlers.

Each function is a thin adapter over core/domain logic and returns plain
Python data structures so it can be wrapped by any MCP server library.
"""

from __future__ import annotations

from typing import Any, TypedDict

from Adventorator.rules.dice import DiceRNG
from Adventorator.rules.checks import CheckInput, CheckResult, compute_check


class RollDiceInput(TypedDict, total=False):
    formula: str
    advantage: bool
    disadvantage: bool
    seed: int


class RollDiceOutput(TypedDict):
    expr: str
    rolls: list[int]
    total: int
    modifier: int
    sides: int
    count: int
    crit: bool


def roll_dice_tool(params: RollDiceInput | dict[str, Any]) -> RollDiceOutput:
    """Roll dice according to an expression like "XdY+Z".

    Inputs:
      - formula: required dice expression (e.g., "1d20+5", "2d6")
      - advantage / disadvantage: only applies to single d20 rolls
      - seed: optional RNG seed for determinism
    """
    if not isinstance(params, dict):  # defensive: allow TypedDict or plain dict
        raise TypeError("params must be a mapping")

    formula = params.get("formula")
    if not isinstance(formula, str) or not formula.strip():
        raise ValueError("'formula' is required and must be a non-empty string")

    advantage = bool(params.get("advantage", False))
    disadvantage = bool(params.get("disadvantage", False))
    seed_val = params.get("seed")
    seed = int(seed_val) if seed_val is not None else None

    rng = DiceRNG(seed=seed)
    roll = rng.roll(formula, advantage=advantage, disadvantage=disadvantage)

    return {
        "expr": roll.expr,
        "rolls": roll.rolls,
        "total": roll.total,
        "modifier": roll.modifier,
        "sides": roll.sides,
        "count": roll.count,
        "crit": roll.crit,
    }


class ComputeCheckInputParams(TypedDict, total=False):
    ability: str
    score: int
    proficient: bool
    expertise: bool
    proficiency_bonus: int
    dc: int | None
    advantage: bool
    disadvantage: bool
    seed: int


class ComputeCheckOutput(TypedDict):
    total: int
    d20: list[int]
    pick: int
    mod: int
    success: bool | None


def compute_check_tool(params: ComputeCheckInputParams | dict[str, Any]) -> ComputeCheckOutput:
    """Compute an ability check using deterministic d20 rolls.

    - Rolls: 2 d20 for advantage/disadvantage, else 1 d20.
    - Uses the same proficiency/ability rules as `rules.checks`.
    """
    if not isinstance(params, dict):
        raise TypeError("params must be a mapping")

    ability = params.get("ability")
    score = params.get("score")
    if not isinstance(ability, str) or not ability:
        raise ValueError("'ability' is required and must be a non-empty string")
    if not isinstance(score, int):
        raise ValueError("'score' is required and must be an integer")

    proficient = bool(params.get("proficient", False))
    expertise = bool(params.get("expertise", False))
    proficiency_bonus = int(params.get("proficiency_bonus", 2))
    dc = params.get("dc")
    if dc is not None and not isinstance(dc, int):
        raise ValueError("'dc' must be an integer if provided")

    advantage = bool(params.get("advantage", False))
    disadvantage = bool(params.get("disadvantage", False))
    seed_val = params.get("seed")
    seed = int(seed_val) if seed_val is not None else None

    # Prepare d20 rolls
    rng = DiceRNG(seed=seed)
    if advantage or disadvantage:
        d20_rolls = [rng.roll("1d20").rolls[0], rng.roll("1d20").rolls[0]]
    else:
        d20_rolls = [rng.roll("1d20").rolls[0]]

    inp = CheckInput(
        ability=ability,
        score=score,
        proficient=proficient,
        expertise=expertise,
        proficiency_bonus=proficiency_bonus,
        dc=dc,
        advantage=advantage,
        disadvantage=disadvantage,
    )
    res: CheckResult = compute_check(inp, d20_rolls=d20_rolls)
    return {
        "total": res.total,
        "d20": res.d20,
        "pick": res.pick,
        "mod": res.mod,
        "success": res.success,
    }
