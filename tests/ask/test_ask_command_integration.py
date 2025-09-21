import pytest

from Adventorator.ask_nlu import parse_and_tag
from Adventorator.commands.ask import _safe_echo
from Adventorator.schemas import AskReport


@pytest.mark.asyncio
async def test_safe_echo_truncates():
    s = _safe_echo("hello\nworld" * 20, limit=20)
    assert len(s) <= 21 and s.endswith("…")


def test_parse_round_trip():
    text = "We swing at the guard silently"
    intent, tags = parse_and_tag(text)
    report = AskReport(raw_text=text, intent=intent, tags=tags)
    s = report.to_json()
    same = AskReport.from_json(s)
    assert same.intent.action == "attack"
    assert same.intent.target_ref == "guard"
    assert "silently" in same.intent.modifiers
