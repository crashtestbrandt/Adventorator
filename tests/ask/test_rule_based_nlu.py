from Adventorator.ask_nlu import parse_and_tag


def test_parse_and_tag_basic_attack():
    text = "I attack the goblin quickly"
    intent, tags = parse_and_tag(text)

    assert intent.action == "attack"
    assert intent.target_ref == "goblin"
    assert "quickly" in intent.modifiers

    keys = {t.key for t in tags}
    assert "action.attack" in keys
    assert any(t.key.startswith("target.") for t in tags)
    # Unknown tokens should be minimal and not include known ones
    assert not any(t.key == "unknown.attack" for t in tags)
    assert not any(t.key == "unknown.goblin" for t in tags)


def test_parse_and_tag_unknown_surfaces():
    text = "bonk the frobnicator"
    intent, tags = parse_and_tag(text)

    # Without ontology match, action falls back to first non-stopword token
    assert intent.action in {"bonk", "say"}
    assert any(t.key.startswith("unknown.") for t in tags)
