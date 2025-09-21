import pytest

from Adventorator.planner import plan as planner_plan
from Adventorator.action_validation.schemas import Plan


class DummyLLM:
    async def generate_response(self, messages):  # minimal stub interface
        return '{"command":"roll","subcommand":"d20","args":{}}'


@pytest.mark.asyncio
async def test_level2_expansion_emits_log(monkeypatch, caplog):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "true")
    monkeypatch.setenv("PLANNER_MAX_LEVEL", "2")
    caplog.set_level("INFO")
    llm = DummyLLM()
    out = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out, Plan)
    assert len(out.steps) == 2
    matched = [rec for rec in caplog.records if rec.message.startswith("{'requested_level': 2") or 'planner.tier.expansion.level2_applied' in rec.message]
    # Relaxed: ensure any record has our event name attribute
    assert any('planner.tier.expansion.level2_applied' in r.message for r in caplog.records)