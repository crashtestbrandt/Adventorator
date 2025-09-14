from dataclasses import dataclass

@dataclass(frozen=True)
class AttackRollResult:
    total: int
    d20_roll: int
    is_critical_hit: bool
    is_critical_miss: bool

@dataclass(frozen=True)
class DamageRollResult:
    total: int
    rolls: list[int]
