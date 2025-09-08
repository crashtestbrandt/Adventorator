from Adventorator.llm_utils import extract_first_json, validate_llm_output


def test_extract_first_json_happy():
    text = 'before {"proposal": {"action": "ability_check", "ability": "DEX", "suggested_dc": 15, "reason": "well-made lock"}, "narration": "You deftly work the picks..."} after'
    data = extract_first_json(text)
    assert isinstance(data, dict)
    assert data["proposal"]["action"] == "ability_check"
    assert data["proposal"]["ability"] == "DEX"
    assert data["proposal"]["suggested_dc"] == 15


def test_extract_first_json_no_json():
    assert extract_first_json("no braces here") is None


def test_extract_first_json_unbalanced():
    assert extract_first_json('{"a": 1') is None


def test_validate_llm_output_valid():
    data = {
        "proposal": {
            "action": "ability_check",
            "ability": "STR",
            "suggested_dc": 10,
            "reason": "simple door",
        },
        "narration": "You push the door.",
    }
    model = validate_llm_output(data)
    assert model is not None
    assert model.proposal.ability == "STR"


def test_validate_llm_output_invalid_schema():
    data = {
        "proposal": {
            "action": "unknown_action",
            "ability": "INT",
            "suggested_dc": 12,
            "reason": "-",
        },
        "narration": "Text",
    }
    assert validate_llm_output(data) is None
