import hashlib
import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator import repos
from Adventorator.db import session_scope


class _SpyResponder:
    def __init__(self):
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_map_show_non_demo_no_active_encounter_warns(db):
    load_all_commands()
    cmd = find_command("map", "show")
    assert cmd is not None

    # Create a scene and a setup (non-active) encounter
    guild_id = 101
    channel_id = 202
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, camp.id, channel_id)
        await repos.create_encounter(s, scene_id=scene.id)

    responder = _SpyResponder()
    inv = Invocation(
        name="map",
        subcommand="show",
        options={},  # non-demo
        user_id="u",
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=responder,
        settings=type("S", (), {"features_map": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    assert responder.messages, "Expected at least one message"
    content, eph = responder.messages[0]
    assert eph is True
    assert "No active encounter" in content


@pytest.mark.asyncio
async def test_renderer_demo_snapshot_deterministic_bytes():
    from Adventorator.services.renderer import RenderInput, Token, render_map, reset_cache

    reset_cache()
    inp = RenderInput(
        encounter_id=-42,
        last_event_id=None,
        width=256,
        height=256,
        grid_size=8,
        cell_px=24,
        tokens=[
            Token(name="A", x=1, y=1, color=(10, 20, 30), active=False),
            Token(name="B", x=3, y=2, color=(200, 100, 50), active=True),
        ],
    )
    png1 = render_map(inp)
    png2 = render_map(inp)
    assert isinstance(png1, (bytes, bytearray)) and len(png1) > 0
    assert png1 == png2, "Renderer should be deterministic for identical input and cache hit"


@pytest.mark.asyncio
async def test_map_show_non_demo_active_path_text_fallback(db):
    load_all_commands()
    cmd = find_command("map", "show")
    assert cmd is not None

    guild_id = 303
    channel_id = 404
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, camp.id, channel_id)
        enc = await repos.create_encounter(s, scene_id=scene.id)
        # Add two combatants and mark as active
    await repos.add_combatant(s, encounter_id=enc.id, name="Aria", hp=10)
    await repos.add_combatant(s, encounter_id=enc.id, name="Borin", hp=12)
    await repos.update_encounter_state(
        s, encounter_id=enc.id, status="active", round=1, active_idx=0
    )

    responder = _SpyResponder()
    inv = Invocation(
        name="map",
        subcommand="show",
        options={},  # non-demo
        user_id="u",
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=responder,
        settings=type("S", (), {"features_map": True})(),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    assert responder.messages, "Expected a response"
    content, eph = responder.messages[0]
    assert eph is False
    assert "Encounter Map" in content
