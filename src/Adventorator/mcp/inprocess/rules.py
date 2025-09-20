"""In-process MCP adapters that delegate to Adventorator rules helpers."""

from __future__ import annotations

from Adventorator.rules.checks import compute_check
from Adventorator.rules.dice import DiceRNG
from Adventorator.rules.engine import Dnd5eRuleset

from ..interfaces import (
    ApplyDamageRequest,
    ApplyDamageResponse,
    ComputeCheckRequest,
    ComputeCheckResponse,
    RollAttackRequest,
    RollAttackResponse,
)


class InProcessRulesAdapter:
    """Concrete rules adapter that calls local helper functions."""

    def compute_check(self, request: ComputeCheckRequest) -> ComputeCheckResponse:
        check_input = request.check
        rng = DiceRNG(seed=request.seed)
        if request.d20_rolls:
            d20_rolls = list(request.d20_rolls)
        else:
            rolls = 2 if check_input.advantage or check_input.disadvantage else 1
            d20_rolls = [rng.roll("1d20").rolls[0] for _ in range(rolls)]
        result = compute_check(check_input, d20_rolls=d20_rolls)
        return ComputeCheckResponse(result=result)

    def roll_attack(self, request: RollAttackRequest) -> RollAttackResponse:
        rules = Dnd5eRuleset(seed=request.seed)
        roll = rules.make_attack_roll(
            request.attack_bonus,
            advantage=request.advantage,
            disadvantage=request.disadvantage,
        )
        total = int(getattr(roll, "total", request.attack_bonus))
        d20 = int(getattr(roll, "d20_roll", total - request.attack_bonus))
        is_crit = bool(getattr(roll, "is_critical_hit", False))
        is_fumble = bool(getattr(roll, "is_critical_miss", False))
        hit = (total >= request.target_ac) and not is_fumble
        damage_total: int | None = None
        if hit:
            try:
                dmg_roll = rules.roll_damage(
                    request.damage_dice,
                    request.damage_modifier,
                    is_critical=is_crit,
                )
                damage_total = int(getattr(dmg_roll, "total", 0))
            except Exception:
                damage_total = 0
        return RollAttackResponse(
            total=total,
            d20=d20,
            is_critical=is_crit,
            is_fumble=is_fumble,
            hit=hit,
            damage_total=damage_total,
        )

    def apply_damage(self, request: ApplyDamageRequest) -> ApplyDamageResponse:
        if request.current_hp is None:
            return ApplyDamageResponse(remaining_hp=None, remaining_temp_hp=None)
        rules = Dnd5eRuleset()
        temp_hp = request.temp_hp or 0
        new_hp, new_temp = rules.apply_damage(request.current_hp, request.amount, temp_hp)
        return ApplyDamageResponse(remaining_hp=new_hp, remaining_temp_hp=new_temp)
