import json
from pathlib import Path

from Adventorator.ask_nlu import parse_and_tag
from Adventorator.schemas import IntentFrame


def _read_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _intent_to_dict(i: IntentFrame) -> dict:
    return {
        "action": i.action,
        "actor_ref": i.actor_ref,
        "target_ref": i.target_ref,
        "modifiers": list(i.modifiers),
    }


def test_golden_basic_fixture():
    fx = Path("tests/fixtures/ask/golden_basic.json")
    data = _read_fixture(fx)

    intent, tags = parse_and_tag(data["input"])

    assert _intent_to_dict(intent) == data["intent"]
    # Compare tag keys and values ignoring ordering; confidence defaults to 1.0
    exp = {(t.get("key"), t.get("value")) for t in data["tags"]}
    got = {
        (t.key, getattr(t, "value", None))
        for t in tags
        if t.key.startswith("action.") or t.key.startswith("target.")
    }
    assert exp.issubset(got)


def test_golden_ambiguous_fixture():
    fx = Path("tests/fixtures/ask/golden_ambiguous.json")
    data = _read_fixture(fx)

    intent, tags = parse_and_tag(data["input"])

    assert _intent_to_dict(intent) == data["intent"]
    exp = {(t.get("key"), t.get("value")) for t in data["tags"]}
    got = {
        (t.key, getattr(t, "value", None))
        for t in tags
        if t.key.startswith("action.") or t.key.startswith("target.")
    }
    assert exp.issubset(got)


def test_golden_sequence_fixture():
    fx = Path("tests/fixtures/ask/golden_sequence.json")
    data = _read_fixture(fx)

    intent, tags = parse_and_tag(data["input"])

    assert _intent_to_dict(intent) == data["intent"]
    exp = {(t.get("key"), t.get("value")) for t in data["tags"]}
    got = {
        (t.key, getattr(t, "value", None))
        for t in tags
        if t.key.startswith("action.") or t.key.startswith("target.")
    }
    assert exp.issubset(got)
