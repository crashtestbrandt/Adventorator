import types

import pytest

from Adventorator.db import session_scope
from Adventorator.metrics import get_counter, reset_counters
from Adventorator.models import ContentNode, NodeType
from Adventorator.retrieval import SqlFallbackRetriever


class _Settings(types.SimpleNamespace):
    pass


@pytest.mark.asyncio
async def test_sql_retriever_metrics_success():
    # Insert a simple content node
    async with session_scope() as s:
        n = ContentNode(
            campaign_id=1,
            node_type=NodeType.lore,
            title="Ancient Door",
            player_text="A heavy stone door with faded runes.",
            gm_text=None,
        )
        s.add(n)

    reset_counters()
    r = SqlFallbackRetriever()
    out = await r.retrieve(1, "door", k=5)
    assert len(out) >= 1
    assert get_counter("retrieval.calls") == 1
    # at least one snippet recorded
    assert get_counter("retrieval.snippets") >= 1
    # latency recorded
    assert get_counter("retrieval.latency_ms") >= 0


@pytest.mark.asyncio
async def test_sql_retriever_metrics_error(monkeypatch):
    # Force an exception by monkeypatching execute to raise
    import sqlalchemy as sa


    r = SqlFallbackRetriever()

    # Patch to break SELECT execution

    def _boom(*a, **k):  # type: ignore[no-redef]
        raise RuntimeError("boom")

    monkeypatch.setattr(sa, "select", _boom)

    reset_counters()
    out = await r.retrieve(1, "anything", k=1)
    assert out == []
    assert get_counter("retrieval.calls") == 1
    assert get_counter("retrieval.errors") == 1
    # latency still recorded
    assert get_counter("retrieval.latency_ms") >= 0
