import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_ask_enabled_empty_input_increments_failed_and_returns_validation():
    reset_counters()
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
            "features_ask_nlu_rule_based": True,
        },
    )()
    inv = Invocation(
        name="ask",
        subcommand=None,
        options={"message": "   "},
        user_id="u4",
        channel_id="c4",
        guild_id="g4",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a response"
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert "provide a message" in content
    assert get_counter("ask.failed") == 1