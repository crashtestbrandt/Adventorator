# test_advantage.py

from hypothesis import given
from hypothesis import strategies as st

from Adventorator.rules.dice import DiceRNG


@given(st.integers(min_value=0, max_value=1_000_000))
def test_advantage_picks_higher(seed):
    rng = DiceRNG(seed=seed)
    res = rng.roll("1d20", advantage=True)
    a, b, p = res.rolls
    assert p == max(a, b)
