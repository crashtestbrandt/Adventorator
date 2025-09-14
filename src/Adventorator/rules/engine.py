from typing import Protocol
from .checks import CheckInput, CheckResult
from .dice import DiceRoll

# Types AttackRollResult and DamageRollResult will be imported from .types (to be created)

class Ruleset(Protocol):
    """
    Defines the interface for a game system's rules, abstracting away
    the specific mechanics of dice rolling and check resolution.
    """
    def roll_dice(self, expr: str, *, advantage: bool = False, disadvantage: bool = False) -> DiceRoll:
        ...

    def perform_check(self, inp: CheckInput, d20_rolls: list[int] | None = None) -> CheckResult:
        ...

    def get_ability_modifier(self, score: int) -> int:
        ...

    def get_proficiency_bonus(self, level: int) -> int:
        ...

    def roll_initiative(self, dex_modifier: int) -> int:
        ...

    def make_attack_roll(self, attack_bonus: int, *, advantage: bool = False, disadvantage: bool = False):
        ...

    def roll_damage(self, damage_dice: str, strength_modifier: int, is_critical: bool = False):
        ...

    def apply_damage(self, current_hp: int, damage_amount: int, temp_hp: int = 0) -> tuple[int, int]:
        ...

    def apply_healing(self, current_hp: int, max_hp: int, healing_amount: int) -> int:
        ...


from .dice import DiceRNG

class Dnd5eRuleset:
    """
    D&D 5e implementation of the Ruleset interface.
    """
    def __init__(self, seed: int | None = None):
        self.rng = DiceRNG(seed)

    def roll_dice(self, expr: str, *, advantage: bool = False, disadvantage: bool = False) -> DiceRoll:
        return self.rng.roll(expr, advantage=advantage, disadvantage=disadvantage)

    def perform_check(self, inp: CheckInput, d20_rolls: list[int] | None = None) -> CheckResult:
        # If d20_rolls not provided, roll them
        if d20_rolls is None:
            rolls = self._get_d20_rolls(inp)
        else:
            rolls = d20_rolls
        # Use the same logic as compute_check
        a = inp.ability.upper()
        ABILS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
        if a not in ABILS:
            raise ValueError("unknown ability")
        pick = max(rolls) if inp.advantage else min(rolls) if inp.disadvantage else rolls[0]
        mod = self.get_ability_modifier(inp.score)
        prof = (
            inp.proficiency_bonus * (2 if inp.expertise else 1)
            if inp.proficient or inp.expertise
            else 0
        )
        total = pick + mod + prof
        success = (total >= inp.dc) if inp.dc is not None else None
        # CheckResult: total, d20, pick, mod, success
        from .checks import CheckResult
        return CheckResult(total=total, d20=rolls, pick=pick, mod=mod + prof, success=success)

    def _get_d20_rolls(self, inp: CheckInput) -> list[int]:
        # For adv/dis, roll two d20s, else one
        if inp.advantage or inp.disadvantage:
            roll1 = self.rng.roll("1d20").rolls[0]
            roll2 = self.rng.roll("1d20").rolls[0]
            return [roll1, roll2]
        else:
            return [self.rng.roll("1d20").rolls[0]]

    def get_ability_modifier(self, score: int) -> int:
        return (score - 10) // 2

    def get_proficiency_bonus(self, level: int) -> int:
        # D&D 5e proficiency bonus table
        # 1-4: +2, 5-8: +3, 9-12: +4, 13-16: +5, 17-20: +6
        if level < 5:
            return 2
        elif level < 9:
            return 3
        elif level < 13:
            return 4
        elif level < 17:
            return 5
        else:
            return 6

    def roll_initiative(self, dex_modifier: int) -> int:
        # Initiative is a Dexterity check with no proficiency bonus.
        d20_roll = self.rng.roll("1d20").total
        return d20_roll + dex_modifier

    def make_attack_roll(self, attack_bonus: int, *, advantage: bool = False, disadvantage: bool = False):
        from .types import AttackRollResult
        roll_result = self.rng.roll("1d20", advantage=advantage, disadvantage=disadvantage)
        # The 'pick' is the last value in rolls for adv/dis, else the only value
        d20_roll = roll_result.rolls[-1] if (advantage or disadvantage) else roll_result.rolls[0]
        return AttackRollResult(
            total=d20_roll + attack_bonus,
            d20_roll=d20_roll,
            is_critical_hit=(d20_roll == 20),
            is_critical_miss=(d20_roll == 1)
        )

    def roll_damage(self, damage_dice: str, strength_modifier: int, is_critical: bool = False):
        from .types import DamageRollResult
        roll1 = self.rng.roll(damage_dice)
        total_damage = roll1.total + strength_modifier
        all_rolls = list(roll1.rolls)
        if is_critical:
            # On a critical, roll the dice again and add them to the total
            roll2 = self.rng.roll(damage_dice)
            total_damage += roll2.total  # Modifiers are NOT added a second time
            all_rolls.extend(roll2.rolls)
        return DamageRollResult(total=max(0, total_damage), rolls=all_rolls)

    def apply_damage(self, current_hp: int, damage_amount: int, temp_hp: int = 0) -> tuple[int, int]:
        damage_to_temp = min(temp_hp, damage_amount)
        new_temp_hp = temp_hp - damage_to_temp
        remaining_damage = damage_amount - damage_to_temp
        new_hp = current_hp - remaining_damage
        return (new_hp, new_temp_hp)

    def apply_healing(self, current_hp: int, max_hp: int, healing_amount: int) -> int:
        new_hp = current_hp + healing_amount
        return min(new_hp, max_hp)
