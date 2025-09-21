from Adventorator.ask_nlu import parse_and_tag


def test_multi_action_tags_sequence_sentence():
    text = "go to the door and attack"
    intent, tags = parse_and_tag(text)

    # Primary action remains the first recognized action
    assert intent.action == "move"
    assert intent.target_ref == "door"

    keys = {t.key for t in tags}
    assert "action.move" in keys
    assert "action.attack" in keys, "secondary action should be surfaced via tags"

    # Ensure door is recognized as the target object
    target_tag = next((t for t in tags if t.key == "target.object"), None)
    assert target_tag is not None
    assert getattr(target_tag, "value", None) == "obj:door"
