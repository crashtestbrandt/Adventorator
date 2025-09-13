import pytest

from Adventorator.planner import _catalog, build_planner_messages, plan
from Adventorator.planner_schemas import PlannerOutput


def test_catalog_has_known_keys():
    cat = _catalog()
    assert isinstance(cat, list)
    # At least one command should be registered (e.g., do or ooc)
    assert any("name" in e and "options_schema" in e for e in cat)


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    async def generate_response(self, messages):  # noqa: ANN001
        # Return JSON string directly
        return self._payload


@pytest.mark.asyncio
async def test_plan_happy_path():
    payload = '{"command": "do", "args": {"message": "I climb the wall."}}'
    llm = _FakeLLM(payload)
    out = await plan(llm, "Climb up")  # type: ignore[arg-type]
    assert isinstance(out, PlannerOutput)
    assert out.command == "do"
    assert out.args.get("message")
