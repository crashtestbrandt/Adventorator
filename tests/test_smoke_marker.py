import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_smoke_roll_basic():
    load_all_commands()
    cmd = find_command("roll", None)
    assert cmd is not None
    class _Spy:
        def __init__(self):
            self.msgs = []
        async def send(self, content: str, *, ephemeral: bool = False):
            self.msgs.append((content, ephemeral))
    inv = Invocation(
        name="roll",
        subcommand=None,
        options={"dice": "2d6+3"},
        user_id="u1",
        channel_id="c1",
        guild_id="g1",
        responder=_Spy(),
        settings=type("S", (), {"features_improbability_drive": True, "features_roll": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_smoke_ask_empty_validation():
    load_all_commands()
    cmd = find_command("ask", None)
    assert cmd is not None
    class _Spy:
        def __init__(self):
            self.msgs = []
        async def send(self, content: str, *, ephemeral: bool = False):
            self.msgs.append((content, ephemeral))
    spy = _Spy()
    inv = Invocation(
        name="ask",
        subcommand=None,
        options={"message": "   "},
        user_id="u2",
        channel_id="c2",
        guild_id="g2",
        responder=spy,
        settings=type("S", (), {
            "features_improbability_drive": True,
            "features_ask": True,
            "features_ask_nlu_rule_based": True,
        })(),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)
    assert spy.msgs and spy.msgs[0][1] is True
