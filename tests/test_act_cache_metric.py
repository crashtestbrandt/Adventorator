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
async def test_plan_planner_cache_hit_increments():
    reset_counters()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    # First invocation seeds the cache
    responder = _SpyResponder()
    inv1 = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "roll a d20"},
        user_id="10",
        channel_id="501",
        guild_id="601",
        responder=responder,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=_FakeLLM('{"command": "roll", "args": {"expr": "1d20"}}'),
    )
    opts1 = cmd.option_model.model_validate(inv1.options)
    await cmd.handler(inv1, opts1)

    # Second identical invocation within TTL should hit cache
    inv2 = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "roll a d20"},
        user_id="10",
        channel_id="501",
        guild_id="601",
        responder=_SpyResponder(),
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=_FakeLLM('{"command": "roll", "args": {"expr": "1d20"}}'),
    )
    opts2 = cmd.option_model.model_validate(inv2.options)
    await cmd.handler(inv2, opts2)

    # Assert cache hit metric incremented once
    assert get_counter("planner.cache.hit") == 1
