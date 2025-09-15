from __future__ import annotations

import pytest

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.models import ContentNode, NodeType
from Adventorator.retrieval import SqlFallbackRetriever


@pytest.mark.asyncio
async def test_retrieval_returns_player_text_only(db):
    # Arrange: insert content with both player_text and gm_text
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=1, name="Test")
        s.add(
            ContentNode(
                campaign_id=camp.id,
                node_type=NodeType.location,
                title="Goblin Warrens",
                player_text="A reeking tunnel leads into darkness.",
                gm_text="Hidden trap at entrance. Secret DC 15 to notice.",
                tags=["dungeon", "goblin"],
            )
        )

    r = SqlFallbackRetriever()

    # Act
    out = await r.retrieve(campaign_id=camp.id, query="trap entrance", k=2)

    # Assert: we never expose gm_text; only player_text is returned
    assert len(out) == 1
    assert out[0].title == "Goblin Warrens"
    assert "reeking tunnel" in out[0].text
    assert "Hidden trap" not in out[0].text


@pytest.mark.asyncio
async def test_retrieval_query_truncation(db):
    r = SqlFallbackRetriever()
    long_query = "x" * 1000
    out = await r.retrieve(campaign_id=1, query=long_query, k=1)
    # No crash; empty because no content exists yet for this campaign/query
    assert isinstance(out, list)
