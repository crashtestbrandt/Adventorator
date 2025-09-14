# test_engine.py
import pytest
from Adventorator.rules.engine import Dnd5eRuleset
from Adventorator.rules.types import AttackRollResult, DamageRollResult

@pytest.fixture
def ruleset():
    return Dnd5eRuleset(seed=42)

def test_roll_initiative(ruleset):
    # Should be deterministic with seed, but just check type and plausible range
    result = ruleset.roll_initiative(dex_modifier=3)
    assert isinstance(result, int)
    # Initiative should be at least 4 (1+3) and at most 23 (20+3)
    assert 4 <= result <= 23

def test_make_attack_roll(ruleset):
    res = ruleset.make_attack_roll(attack_bonus=5)
    assert isinstance(res, AttackRollResult)
    assert res.total == res.d20_roll + 5
    assert not res.is_critical_hit
    assert not res.is_critical_miss

def test_roll_damage_normal(ruleset):
    res = ruleset.roll_damage("2d6", strength_modifier=3, is_critical=False)
    assert isinstance(res, DamageRollResult)
    assert res.total >= 3  # At least the modifier
    assert len(res.rolls) == 2

def test_roll_damage_critical(ruleset):
    res = ruleset.roll_damage("1d8", strength_modifier=2, is_critical=True)
    assert isinstance(res, DamageRollResult)
    assert len(res.rolls) == 2  # 1d8 rolled twice
    assert res.total >= 2

def test_apply_damage_and_healing(ruleset):
    # Damage with temp HP
    hp, temp = ruleset.apply_damage(current_hp=10, damage_amount=7, temp_hp=5)
    assert temp == 0
    assert hp == 8  # 5 temp absorbed, 2 to HP
    # Healing
    healed = ruleset.apply_healing(current_hp=8, max_hp=10, healing_amount=5)
    assert healed == 10  # Not above max
    healed = ruleset.apply_healing(current_hp=5, max_hp=10, healing_amount=3)
    assert healed == 8
