# tests/test_transcript.py
import pytest
from sqlalchemy import text

from Adventorator import repos


@pytest.mark.asyncio
async def test_transcript_write(db):
    camp = await repos.get_or_create_campaign(db, 123)
    scene = await repos.ensure_scene(db, camp.id, channel_id=999)
    await repos.write_transcript(
        db, camp.id, scene.id, 999, "player", "/roll 1d20", "42", {"opts": {"expr": "1d20"}}
    )
    result = await db.execute(text("SELECT COUNT(*) FROM transcripts"))
    assert result.scalar_one() == 1
