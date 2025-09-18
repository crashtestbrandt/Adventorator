import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters


class _SpyResponder:
    def __init__(self):
        self.messages = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


class _FakeLLM:
    def __init__(self, payload: str):
        self._payload = payload

    async def generate_response(self, messages):  # noqa: ANN001
        return self._payload


@pytest.mark.asyncio
async def test_plan_routes_roll_happy_path(monkeypatch):
    reset_counters()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    # Mock planner via LLM: choose roll 2d6+3
    llm = _FakeLLM('{"command": "roll", "args": {"expr": "2d6+3"}}')

    inv = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "roll 2d6+3 for damage"},
        user_id="1",
        channel_id="100",
        guild_id="200",
        responder=_SpyResponder(),
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=llm,
    )
    opts = cmd.option_model.model_validate(inv.options)

    # Run
    await cmd.handler(inv, opts)

    # Assert at least one message was sent (roll output)
    assert inv.responder.messages, "Expected a roll response"
    # Accepted decision counter incremented
    assert get_counter("planner.decision.accepted") == 1


@pytest.mark.asyncio
async def test_plan_rejects_unknown_tool(monkeypatch):
    reset_counters()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    # Mock planner via LLM: choose unknown command
    llm = _FakeLLM('{"command": "bananas", "args": {}}')

    responder = _SpyResponder()
    inv = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "do something weird"},
        user_id="1",
        channel_id="101",
        guild_id="201",
        responder=responder,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=llm,
    )
    opts = cmd.option_model.model_validate(inv.options)

    # Run
    await cmd.handler(inv, opts)

    # Should have ephemeral error
    assert responder.messages, "Expected an error response"
    assert any(ep for _, ep in responder.messages), "Expected an ephemeral message"
    # Rejected counter incremented
    assert get_counter("planner.decision.rejected") == 1
    assert get_counter("planner.allowlist.rejected") == 1
