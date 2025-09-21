import json
import re
from pathlib import Path

import pytest

from Adventorator.config import load_settings, Settings
from Adventorator.planner_tiers import resolve_planning_level
from Adventorator.planner import plan as planner_plan
from Adventorator.action_validation.schemas import Plan


class DummyLLM:
    async def generate_response(self, messages):  # minimal stub interface
        return '{"command":"roll","subcommand":"d20","args":{}}'


@pytest.mark.asyncio
async def test_plan_serialization_level1_stable(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "false")
    llm = DummyLLM()
    out = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out, Plan)
    # Load golden fixture and compare structure (ignore dynamic plan_id)
    fixture_path = Path("tests/golden/plan_single_step_level1.json")
    data = json.loads(fixture_path.read_text())
    assert out.feasible is data["feasible"]
    assert len(out.steps) == 1
    assert out.steps[0].op == data["steps"][0]["op"]
    assert out.steps[0].guards == []
    # plan_id should be a 16 hex digest
    assert re.fullmatch(r"[0-9a-f]{16}", out.plan_id)


def test_resolve_planning_level_defaults(monkeypatch):
    monkeypatch.delenv("FEATURES_PLANNING_TIERS", raising=False)
    s = load_settings()
    assert resolve_planning_level(s) == 1


def test_resolve_planning_level_disabled(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "false")
    monkeypatch.setenv("PLANNER_MAX_LEVEL", "3")
    s = load_settings()
    assert resolve_planning_level(s) == 1


def test_resolve_planning_level_enabled(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "true")
    monkeypatch.setenv("PLANNER_MAX_LEVEL", "3")
    s = load_settings()
    assert resolve_planning_level(s) == 3


@pytest.mark.asyncio
async def test_level2_expansion_inserts_prepare_step(monkeypatch):
    monkeypatch.setenv("FEATURES_PLANNING_TIERS", "true")
    monkeypatch.setenv("PLANNER_MAX_LEVEL", "2")
    s = load_settings()
    assert resolve_planning_level(s) == 2

    class DummyLLM2:
        async def generate_response(self, messages):  # minimal stub interface
            return '{"command":"roll","subcommand":"d20","args":{}}'

    from Adventorator.planner import plan as planner_plan

    llm = DummyLLM2()
    out = await planner_plan(llm, "roll a d20", return_plan=True)
    assert isinstance(out, Plan)
    assert len(out.steps) == 2
    assert out.steps[0].op.startswith("prepare.")
    assert out.steps[1].op == "roll.d20"
    # Golden structural comparison (ignore plan_id)
    golden_path = Path("tests/golden/plan_level2_two_steps.json")
    import json

    data = json.loads(golden_path.read_text())
    assert [s.op for s in out.steps] == [step["op"] for step in data["steps"]]
    assert [s.args for s in out.steps] == [step["args"] for step in data["steps"]]
    assert [s.guards for s in out.steps] == [step["guards"] for step in data["steps"]]
