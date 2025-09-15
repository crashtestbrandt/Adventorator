import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


# These tests don't need the DB; override the global autouse fixtures
@pytest.fixture(scope="session", autouse=True)
async def _app_engine_lifecycle():  # noqa: D401
    """No-op DB lifecycle for this module."""
    yield


@pytest.fixture(autouse=True)
async def _reset_db_per_test():  # noqa: D401
    """No-op DB reset for this module."""
    yield


@pytest.mark.asyncio
async def test_help_happy_path_enabled_llm():
    reset_counters()
    load_all_commands()

    cmd = find_command("help", None)
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="help",
        subcommand=None,
        options={"topic": None},
        user_id="u1",
        channel_id="c1",
        guild_id="g1",
        responder=responder,
        settings=type("S", (), {"features_llm": True, "feature_planner_enabled": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    # One ephemeral help message with expected headings/content and reasonable size for Discord
    assert responder.messages, "Expected help response"
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert "Adventorator — Quick Start" in content
    assert "Quick start:" in content
    # When LLM features are enabled, planner mention should be positive
    assert "Try /plan" in content
    assert len(content) < 2000


@pytest.mark.asyncio
async def test_help_planner_disabled_message():
    reset_counters()
    load_all_commands()

    cmd = find_command("help", None)
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="help",
        subcommand=None,
        options={},
        user_id="u2",
        channel_id="c2",
        guild_id="g2",
        responder=responder,
        settings=type("S", (), {"features_llm": False, "feature_planner_enabled": False})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages, "Expected help response"
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    # With planner disabled by flags, help should indicate it's disabled
    assert "Planner (/plan) is currently disabled" in content


@pytest.mark.asyncio
async def test_help_increments_metric():
    reset_counters()
    load_all_commands()

    cmd = find_command("help", None)
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="help",
        subcommand=None,
        options={},
        user_id="u3",
        channel_id="c3",
        guild_id="g3",
        responder=responder,
        settings=type("S", (), {})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert get_counter("help.view") == 1
