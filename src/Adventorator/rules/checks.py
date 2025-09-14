# rules/checks.py

from dataclasses import dataclass

import structlog

ABILS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


def ability_mod(score: int) -> int:
    return (score - 10) // 2


@dataclass(frozen=True)
class CheckInput:
    ability: str
    score: int
    proficient: bool = False
    expertise: bool = False
    proficiency_bonus: int = 2
    dc: int | None = None
    advantage: bool = False
    disadvantage: bool = False


@dataclass(frozen=True)
class CheckResult:
    total: int
    d20: list[int]  # raw d20(s)
    pick: int  # selected d20 (adv/dis)
    mod: int  # ability +/- proficiency
    success: bool | None


def compute_check(inp: CheckInput, d20_rolls: list[int]) -> CheckResult:
    log = structlog.get_logger()
    log.debug("rules.checks.compute.start", inputs=inp.__dict__, d20_rolls=d20_rolls)
    a = inp.ability.upper()
    if a not in ABILS:
        raise ValueError("unknown ability")

    pick = max(d20_rolls) if inp.advantage else min(d20_rolls) if inp.disadvantage else d20_rolls[0]

    mod = ability_mod(inp.score)
    prof = (
        inp.proficiency_bonus * (2 if inp.expertise else 1)
        if inp.proficient or inp.expertise
        else 0
    )

    total = pick + mod + prof
    success = (total >= inp.dc) if inp.dc is not None else None
    out = CheckResult(total=total, d20=d20_rolls, pick=pick, mod=mod + prof, success=success)
    log.debug("rules.checks.compute.result", result=out.__dict__)
    return out
