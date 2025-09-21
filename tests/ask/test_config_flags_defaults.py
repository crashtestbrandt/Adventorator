from Adventorator.config import load_settings


def test_improbability_and_ask_flags_default_off(tmp_path, monkeypatch, chdir=None):
    # Ensure no config.toml in temp dir so defaults apply
    monkeypatch.chdir(tmp_path)
    s = load_settings()
    assert s.features_improbability_drive is False
    assert s.features_ask is False
    assert s.features_ask_nlu_rule_based is True
    assert s.features_ask_kb_lookup is False
    assert s.features_ask_planner_handoff is False
