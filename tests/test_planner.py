"""Planner tests for safety, intent mapping, and catalog shape."""

import pytest

from Adventorator.planner import _catalog, plan
from Adventorator.planner_schemas import PlannerOutput


class _FakeLLM:
    def __init__(self, payload: str):
        self._payload = payload

    async def generate_response(self, messages):  # noqa: ANN001
        return self._payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_msg,payload,expected_cmd",
    [
        (
            "heal me for 10 HP",
            '{"command": "error", "args": {"message": "That action is not supported."}}',
            "error",
        ),
        (
            "add a sword to my inventory",
            '{"command": "error", "args": {"message": "That action is not supported."}}',
            "error",
        ),
        (
            "roll 2d6+3 for damage",
            '{"command": "roll", "args": {"expr": "2d6+3"}}',
            "roll",
        ),
        (
            "make a dexterity check against DC 15",
            '{"command": "check", "args": {"ability": "DEX", "dc": 15}}',
            "check",
        ),
        (
            "I sneak along the wall",
            '{"command": "do", "args": {"message": "I sneak along the wall"}}',
            "do",
        ),
        (
            "show my character sheet",
            '{"command": "sheet.show", "args": {"name": "YourCharacterName"}}',
            "sheet.show",
        ),
        (
            "do something impossible",
            '{"command": "error", "args": {"message": "That action is not supported."}}',
            "error",
        ),
    ],
)
async def test_planner_safety_and_intent(user_msg, payload, expected_cmd):  # noqa: ANN001
    out = await plan(_FakeLLM(payload), user_msg)
    assert out is not None
    assert out.command == expected_cmd


def test_catalog_has_known_keys():
    cat = _catalog()
    assert isinstance(cat, list)
    # At least one command should be registered (e.g., do or ooc)
    assert any("name" in e and "options_schema" in e for e in cat)


@pytest.mark.asyncio
async def test_plan_happy_path():
    payload = '{"command": "do", "args": {"message": "I climb the wall."}}'
    out = await plan(_FakeLLM(payload), "Climb up")  # type: ignore[arg-type]
    assert isinstance(out, PlannerOutput)
    assert out.command == "do"
    assert out.args.get("message")
