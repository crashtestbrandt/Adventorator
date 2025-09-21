import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_ask_echo_truncates_and_sanitizes():
    load_all_commands()

    cmd = find_command("ask", None)
    assert cmd is not None

    long = "walk\n\n  to the market\tand buy apples " + ("!" * 200)
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
        options={"message": long},
        user_id="u5",
        channel_id="c5",
        guild_id="g5",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages
    content, _ = responder.messages[0]
    # Sanitized newlines/tabs should be spaces and we should see ellipsis for truncation
    assert "you said: \"walk to the market and buy apples" in content
    assert content.endswith("…\"") or "…\"" in content