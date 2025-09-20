import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command


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
async def test_map_show_disabled_ephemeral_message():
    load_all_commands()

    cmd = find_command("map", "show")
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="map",
        subcommand="show",
        options={},
        user_id="u1",
        channel_id="c1",
        guild_id="g1",
        responder=responder,
        settings=type("S", (), {"features_map": False})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a response"
    content, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert "Map rendering is disabled" in content


@pytest.mark.asyncio
async def test_map_show_demo_placeholder_message():
    load_all_commands()

    cmd = find_command("map", "show")
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="map",
        subcommand="show",
        options={"demo": True},
        user_id="u2",
        channel_id="c2",
        guild_id="g2",
        responder=responder,
        settings=type("S", (), {"features_map": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a response"
    content, ephemeral = responder.messages[0]
    # With a non-Discord responder, we fall back to a normal text message
    assert ephemeral is False
    assert "Encounter Map" in content


@pytest.mark.asyncio
async def test_map_show_demo_verbose_fallback_and_debug():
    load_all_commands()

    cmd = find_command("map", "show")
    assert cmd is not None

    responder = _SpyResponder()
    inv = Invocation(
        name="map",
        subcommand="show",
        options={"demo": True, "verbose": True},
        user_id="u3",
        channel_id="c3",
        guild_id="g3",
        responder=responder,
        settings=type("S", (), {"features_map": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)

    await cmd.handler(inv, opts)

    # Expect two messages: normal then ephemeral debug
    assert len(responder.messages) >= 2
    content0, eph0 = responder.messages[0]
    content1, eph1 = responder.messages[1]
    assert eph0 is False
    assert "Encounter Map" in content0
    assert eph1 is True
    assert content1.startswith("debug: sent_as=")
