# rules/dice.py

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_DICE_RE = re.compile(r"^\s*(?P<count>\d+)?d(?P<sides>\d+)\s*(?P<mod>[+\-]\s*\d+)?\s*$")


@dataclass(frozen=True)
class DiceRoll:
    expr: str
    rolls: list[int]
    total: int
    modifier: int
    sides: int
    count: int
    crit: bool = False


class DiceRNG:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def roll(self, expr: str, advantage: bool = False, disadvantage: bool = False) -> DiceRoll:
        """
        Supports: XdY+Z
        Special case: d20 with adv/dis
        """
        m = _DICE_RE.match(expr.replace(" ", ""))
        if not m:
            raise ValueError(f"Bad dice expression: {expr}")
        count = int(m.group("count") or 1)
        sides = int(m.group("sides"))
        mod = int((m.group("mod") or "0").replace(" ", ""))

        # Advantage/Disadvantage only sensibly applies to d20 single rolls.
        if sides == 20 and count == 1 and (advantage or disadvantage):
            a = self._rng.randint(1, 20)
            b = self._rng.randint(1, 20)
            pick = max(a, b) if advantage else min(a, b)
            total = pick + mod
            return DiceRoll(
                expr=expr,
                rolls=[a, b, pick],
                total=total,
                modifier=mod,
                sides=20,
                count=1,
                crit=(pick == 20),
            )

        rolls = [self._rng.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + mod
        crit = sides == 20 and count == 1 and rolls[0] == 20
        return DiceRoll(
            expr=expr, rolls=rolls, total=total, modifier=mod, sides=sides, count=count, crit=crit
        )
