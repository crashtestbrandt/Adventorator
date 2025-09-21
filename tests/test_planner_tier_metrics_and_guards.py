import json
import re
from pathlib import Path

import pytest

from Adventorator.metrics import reset_counters, get_counter
from Adventorator.planner import plan as planner_plan
from Adventorator.action_validation.schemas import Plan


class DummyLLM:
    async def generate_response(self, messages):  # minimal stub interface
        return '{"command":"roll","subcommand":"d20","args":{}}'


@pytest.mark.asyncio
async def test_planner_metrics_level1_empty_guards(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "false")
    reset_counters()
    llm = DummyLLM()
    out = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out, Plan)
    assert out.steps[0].guards == []  # tiers disabled → no deterministic guard
    # Counters
    assert get_counter("planner.tier.level.1") == 1
    assert get_counter("plan.steps.count") == 1
    assert get_counter("plan.guards.count") == 0


@pytest.mark.asyncio
async def test_planner_monkeypatched_guards_population(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "true")
    # Monkeypatch the guards population hook to inject sample guards
    from Adventorator import planner_tiers

    def _fake_guards_for_steps(steps, *, tiers_enabled: bool = False):  # noqa: D401
        # Simulate base population (if tiers_enabled true, base impl would add capability:basic_action)
        if tiers_enabled:
            for s in steps:
                if "capability:basic_action" not in s.guards:
                    s.guards.append("capability:basic_action")
        for s in steps:
            if "predicate:exists:actor" not in s.guards:
                s.guards.append("predicate:exists:actor")

    monkeypatch.setattr(planner_tiers, "guards_for_steps", _fake_guards_for_steps)
    reset_counters()
    llm = DummyLLM()
    out = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out, Plan)
    # Deterministic guard added by implementation plus monkeypatch extras
    assert set(out.steps[0].guards) == {"capability:basic_action", "predicate:exists:actor"}
    # Counters now reflect two guards
    assert get_counter("plan.guards.count") == 2
    # plan serialization matches golden except plan_id
    fixture_path = Path("tests/golden/plan_single_step_with_guards.json")
    data = json.loads(fixture_path.read_text())
    assert len(out.steps) == 1
    assert out.steps[0].op == data["steps"][0]["op"]
    assert out.steps[0].guards == data["steps"][0]["guards"]
    assert re.fullmatch(r"[0-9a-f]{16}", out.plan_id)


@pytest.mark.asyncio
async def test_planner_flag_enable_then_disable_stability(monkeypatch):
    # Enable tiers then disable to ensure rollback stability (still Level 1)
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "true")
    # Force level 1 to avoid prepare step injection so we isolate guard diff only
    monkeypatch.setenv("PLANNER_MAX_LEVEL", "1")
    llm = DummyLLM()
    out_enabled = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out_enabled, Plan)
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "false")
    out_disabled = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out_disabled, Plan)
    assert len(out_enabled.steps) == 1  # stays single-step at level 1
    assert len(out_disabled.steps) == 1
    assert out_enabled.steps[0].guards == ["capability:basic_action"]
    assert out_disabled.steps[0].guards == []
