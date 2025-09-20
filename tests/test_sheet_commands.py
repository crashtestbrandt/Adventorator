import json

import pytest
from sqlalchemy import select

from Adventorator import models, repos
from Adventorator.commanding import Invocation
from Adventorator.commands.sheet import (
    SheetCreateOpts,
    SheetShowOpts,
    sheet_create,
    sheet_show,
)
from Adventorator.db import session_scope


class _SpyResponder:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_sheet_create_rejects_invalid_json():
    responder = _SpyResponder()
    inv = Invocation(
        name="sheet",
        subcommand="create",
        options={},
        user_id="1",
        channel_id="10",
        guild_id="20",
        responder=responder,
        settings=None,
        llm_client=None,
    )
    opts = SheetCreateOpts.model_validate({"json": "{"})

    await sheet_create(inv, opts)

    assert responder.messages
    msg, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert msg.startswith("❌ Invalid JSON or schema:")


@pytest.mark.asyncio
async def test_sheet_create_rejects_large_payload():
    responder = _SpyResponder()
    inv = Invocation(
        name="sheet",
        subcommand="create",
        options={},
        user_id="1",
        channel_id="10",
        guild_id="20",
        responder=responder,
        settings=None,
        llm_client=None,
    )
    oversize = "{" + ("a" * 16010)
    opts = SheetCreateOpts.model_validate({"json": oversize})

    await sheet_create(inv, opts)

    assert responder.messages == [("❌ JSON missing or too large (16KB max).", True)]


@pytest.mark.asyncio
async def test_sheet_create_and_show_round_trip(db):
    guild_id = "51"
    channel_id = "601"
    user_id = "777"
    payload = {
        "name": "Aria",
        "class": "Wizard",
        "level": 5,
        "abilities": {
            "STR": 10,
            "DEX": 14,
            "CON": 12,
            "INT": 18,
            "WIS": 11,
            "CHA": 13,
        },
        "proficiency_bonus": 3,
        "skills": {"arcana": True, "history": False},
        "ac": 15,
        "hp": {"current": 30, "max": 30, "temp": 0},
        "speed": 30,
        "senses": {},
        "inventory": [],
        "features": [],
        "spells": [],
        "conditions": [],
        "notes": "Test sheet",
    }

    create_responder = _SpyResponder()
    create_inv = Invocation(
        name="sheet",
        subcommand="create",
        options={},
        user_id=user_id,
        channel_id=channel_id,
        guild_id=guild_id,
        responder=create_responder,
        settings=None,
        llm_client=None,
    )
    create_opts = SheetCreateOpts.model_validate({"json": json.dumps(payload)})

    await sheet_create(create_inv, create_opts)

    assert create_responder.messages
    create_msg, create_ephemeral = create_responder.messages[0]
    assert create_ephemeral is False
    assert "✅ Sheet saved for" in create_msg

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=int(guild_id))
        character = await repos.get_character(s, camp.id, payload["name"])
        assert character is not None
        transcripts = (await s.execute(select(models.Transcript))).scalars().all()
        assert transcripts, "Expected a transcript entry from sheet.create"

    show_responder = _SpyResponder()
    show_inv = Invocation(
        name="sheet",
        subcommand="show",
        options={},
        user_id=user_id,
        channel_id=channel_id,
        guild_id=guild_id,
        responder=show_responder,
        settings=None,
        llm_client=None,
    )
    show_opts = SheetShowOpts.model_validate({"name": payload["name"]})

    await sheet_show(show_inv, show_opts)

    assert show_responder.messages
    show_msg, show_ephemeral = show_responder.messages[0]
    assert show_ephemeral is True
    assert "**Aria**" in show_msg
    assert "Wizard" in show_msg

    async with session_scope() as s:
        transcripts = (await s.execute(select(models.Transcript))).scalars().all()
        assert len(transcripts) >= 2, "Expected transcript log for sheet.show"


@pytest.mark.asyncio
async def test_sheet_show_missing_character(db):
    responder = _SpyResponder()
    inv = Invocation(
        name="sheet",
        subcommand="show",
        options={},
        user_id="9",
        channel_id="90",
        guild_id="99",
        responder=responder,
        settings=None,
        llm_client=None,
    )
    opts = SheetShowOpts.model_validate({"name": "Unknown"})

    await sheet_show(inv, opts)

    assert responder.messages == [("❌ No character named **Unknown**", True)]


@pytest.mark.asyncio
async def test_sheet_show_requires_name():
    responder = _SpyResponder()
    inv = Invocation(
        name="sheet",
        subcommand="show",
        options={},
        user_id="5",
        channel_id="50",
        guild_id="60",
        responder=responder,
        settings=None,
        llm_client=None,
    )
    opts = SheetShowOpts.model_validate({"name": ""})

    await sheet_show(inv, opts)

    assert responder.messages == [("❌ You must provide a character name.", True)]
