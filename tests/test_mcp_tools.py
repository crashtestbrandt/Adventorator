from Adventorator.adapters.mcp.tools import compute_check_tool, roll_dice_tool


def test_roll_dice_basic_seeded():
    out = roll_dice_tool({"formula": "1d20+5", "seed": 42})
    assert out["expr"] == "1d20+5"
    assert out["sides"] == 20
    assert out["count"] == 1
    # With seed=42, Python's first randint(1,20) is deterministic.
    assert isinstance(out["total"], int)
    assert len(out["rolls"]) == 1


def test_roll_dice_advantage_seeded():
    out = roll_dice_tool({"formula": "1d20+0", "seed": 123, "advantage": True})
    # Should produce three entries: a, b, pick
    assert len(out["rolls"]) == 3
    assert out["sides"] == 20
    assert out["count"] == 1
    assert out["total"] == out["rolls"][2] + out["modifier"]


def test_roll_dice_validation():
    try:
        roll_dice_tool({})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_check_basic():
    out = compute_check_tool({
        "ability": "DEX",
        "score": 14,
        "proficient": True,
        "proficiency_bonus": 2,
        "dc": 12,
        "seed": 7,
    })
    assert isinstance(out["total"], int)
    assert isinstance(out["d20"], list) and len(out["d20"]) == 1
    assert out["success"] in (True, False)


def test_compute_check_advantage():
    out = compute_check_tool({
        "ability": "STR",
        "score": 10,
        "advantage": True,
        "seed": 9,
    })
    assert len(out["d20"]) == 2
    assert out["pick"] == max(out["d20"])  # advantage
