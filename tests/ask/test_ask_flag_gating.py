import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_ask_disabled_shows_message():
    load_all_commands()
    cmd = find_command("ask", None)
    assert cmd is not None

    responder = _SpyResponder()
    settings = type(
        "S",
        (),
        {
            "features_improbability_drive": False,
            "features_ask": True,
            "features_ask_nlu_rule_based": True,
        },
    )()

    inv = Invocation(
        name="ask",
        subcommand=None,
        options={"message": "attack goblin"},
        user_id="u6",
        channel_id="c6",
        guild_id="g6",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert "disabled" in content


@pytest.mark.asyncio
async def test_ask_rule_based_off_falls_back_to_minimal():
    load_all_commands()
    cmd = find_command("ask", None)
    assert cmd is not None

    responder = _SpyResponder()
    settings = type(
        "S",
        (),
        {
            "features_improbability_drive": True,
            "features_ask": True,
            "features_ask_nlu_rule_based": False,
        },
    )()

    inv = Invocation(
        name="ask",
        subcommand=None,
        options={"message": "please attack the goblin"},
        user_id="u7",
        channel_id="c7",
        guild_id="g7",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages
    content, _ = responder.messages[0]
    assert "action='attack'" in content  # still infers the action via minimal fallback
