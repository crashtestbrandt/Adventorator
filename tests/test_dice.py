# test_dice.py

from Adventorator.rules.dice import DiceRNG


def test_seed_stability():
    rng1 = DiceRNG(seed=42)
    rng2 = DiceRNG(seed=42)
    r1 = [rng1.roll("1d20").total for _ in range(10)]
    r2 = [rng2.roll("1d20").total for _ in range(10)]
    assert r1 == r2


def test_parse_and_mod():
    rng = DiceRNG(seed=1)
    res = rng.roll("2d6+3")
    assert res.sides == 6 and res.count == 2 and res.modifier == 3
