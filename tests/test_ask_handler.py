import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


@pytest.fixture(scope="session", autouse=True)
async def _app_engine_lifecycle():  # noqa: D401
    """No-op DB lifecycle for this module."""
    yield


@pytest.fixture(autouse=True)
async def _reset_db_per_test():  # noqa: D401
    """No-op DB reset for this module."""
    yield


@pytest.mark.asyncio
async def test_ask_disabled_by_default():
    reset_counters()
    load_all_commands()

    cmd = find_command("ask", None)
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="ask",
        subcommand=None,
        options={"message": "attack the goblin"},
        user_id="u1",
        channel_id="c1",
        guild_id="g1",
        responder=responder,
        settings=type("S", (), {"features_improbability_drive": False, "features_ask": False})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    # Disabled message and no counters incremented
    assert responder.messages, "Expected a response when disabled"
    content, ephemeral = responder.messages[0]
    assert "disabled" in content
    assert ephemeral is True
    assert get_counter("ask.received") == 0
    assert get_counter("ask.ask_report.emitted") == 0


@pytest.mark.asyncio
async def test_ask_enabled_happy_path_emits_metrics_and_summary():
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
        options={"message": "attack the goblin"},
        user_id="u2",
        channel_id="c2",
        guild_id="g2",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    # Summary returned and counters incremented
    assert responder.messages, "Expected a response"
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert content.startswith("🧭 Interpreted intent:")
    assert get_counter("ask.received") == 1
    assert get_counter("ask.ask_report.emitted") == 1


@pytest.mark.asyncio
async def test_ask_infers_action_skipping_pronouns_and_stopwords():
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
        options={"message": "I slap the goblin with a salmon"},
        user_id="u3",
        channel_id="c3",
        guild_id="g3",
        responder=responder,
        settings=settings,
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a response"
    content, _ = responder.messages[0]
    assert "action='slap'" in content
