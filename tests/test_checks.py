# test_checks.py

from Adventorator.rules.checks import CheckInput, ability_mod, compute_check


def test_mods():
    assert ability_mod(10) == 0
    assert ability_mod(8) == -1
    assert ability_mod(18) == 4


def test_simple_check_success():
    inp = CheckInput(ability="DEX", score=16, proficient=True, proficiency_bonus=2, dc=15)
    out = compute_check(inp, [12])  # d20=12
    # 12 + DEX(3) + prof(2) = 17 >= 15
    assert out.total == 17 and out.success is True
