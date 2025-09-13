import json
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
async def test_act_routes_check():
    reset_counters()
    load_all_commands()
    cmd = find_command("act", None)
    assert cmd is not None

    llm = _FakeLLM('{"command": "check", "args": {"ability": "DEX", "dc": 10}}')
    responder = _SpyResponder()
    inv = Invocation(
        name="act",
        subcommand=None,
        options={"message": "make a dexterity check vs 10"},
        user_id="2",
        channel_id="201",
        guild_id="301",
        responder=responder,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=llm,
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a check response"
    assert get_counter("planner.decision.accepted") >= 1


@pytest.mark.asyncio
async def test_act_routes_ooc():
    reset_counters()
    load_all_commands()
    cmd = find_command("act", None)
    assert cmd is not None

    llm = _FakeLLM('{"command": "ooc", "args": {"message": "tell a short neutral scene"}}')
    responder = _SpyResponder()
    inv = Invocation(
        name="act",
        subcommand=None,
        options={"message": "narrate something out of character"},
        user_id="3",
        channel_id="202",
        guild_id="302",
        responder=responder,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=_FakeLLM('{"command": "ooc", "args": {"message": "a simple scene"}}'),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    # ooc may run in shadow mode → ephemeral response acceptable
    assert responder.messages, "Expected an ooc response"


@pytest.mark.asyncio
async def test_act_sheet_show_and_create_invalid_args():
    reset_counters()
    load_all_commands()
    cmd = find_command("act", None)
    assert cmd is not None

    # sheet.show with missing name (invalid args for option model)
    responder1 = _SpyResponder()
    inv1 = Invocation(
        name="act",
        subcommand=None,
        options={"message": "show the sheet"},
        user_id="4",
        channel_id="203",
        guild_id="303",
        responder=responder1,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=_FakeLLM('{"command": "sheet.show", "args": {}}'),
    )
    opts1 = cmd.option_model.model_validate(inv1.options)
    await cmd.handler(inv1, opts1)
    assert responder1.messages, "Expected an error for invalid args"
    assert any(ep for _, ep in responder1.messages)

    # sheet.create with invalid JSON payload
    bad_json = "{"  # invalid JSON
    responder2 = _SpyResponder()
    inv2 = Invocation(
        name="act",
        subcommand=None,
        options={"message": "create a character named Aria"},
        user_id="5",
        channel_id="204",
        guild_id="304",
        responder=responder2,
        settings=type("S", (), {"features_llm": True, "features_llm_visible": False})(),
        llm_client=_FakeLLM(json.dumps({"command": "sheet.create", "args": {"json": bad_json}})),
    )
    opts2 = cmd.option_model.model_validate(inv2.options)
    await cmd.handler(inv2, opts2)
    # The sheet.create handler will catch JSON error and send ephemeral error
    assert responder2.messages, "Expected an error for invalid JSON"
    assert any(ep for _, ep in responder2.messages)
