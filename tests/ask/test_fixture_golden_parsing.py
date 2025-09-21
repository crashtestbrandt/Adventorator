import json
from pathlib import Path

from Adventorator.ask_nlu import parse_and_tag


def test_golden_basic_fixture():
    p = Path("tests/fixtures/ask/golden_basic.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    intent, tags = parse_and_tag(data["input"])  # type: ignore[index]

    assert intent.action == data["intent"]["action"]
    assert intent.target_ref == data["intent"]["target_ref"]
    for m in data["intent"]["modifiers"]:
        assert m in intent.modifiers

    tag_keys = {(t.key, t.value) for t in tags}
    for t in data["tags"]:
        tup = (t.get("key"), t.get("value"))
        assert tup in tag_keys


def test_golden_ambiguous_fixture():
    p = Path("tests/fixtures/ask/golden_ambiguous.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    intent, tags = parse_and_tag(data["input"])  # type: ignore[index]
    assert intent.action == data["intent"]["action"]
    assert intent.target_ref == data["intent"]["target_ref"]
    assert intent.modifiers == data["intent"]["modifiers"]
    keys = {t.key for t in tags}
    assert "action.attack" in keys


def test_golden_sequence_fixture():
    p = Path("tests/fixtures/ask/golden_sequence.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    intent, tags = parse_and_tag(data["input"])  # type: ignore[index]
    assert intent.action == data["intent"]["action"]
    assert intent.target_ref == data["intent"]["target_ref"]
    keys = {(t.key, t.value) for t in tags}
    for t in data["tags"]:
        tup = (t.get("key"), t.get("value"))
        assert tup in keys
