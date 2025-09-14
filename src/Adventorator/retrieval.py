from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa

from Adventorator.db import get_sessionmaker
from Adventorator.models import ContentNode


@dataclass(frozen=True)
class ContentSnippet:
    id: int
    node_type: str
    title: str
    text: str  # player-visible only


class BaseRetriever:
    async def retrieve(self, campaign_id: int, query: str, k: int = 4) -> list[ContentSnippet]:
        raise NotImplementedError


class SqlFallbackRetriever(BaseRetriever):
    """Lightweight LIKE/ILIKE search backed by the primary DB.

    Guaranteed to return only player-visible text; gm_text is never surfaced.
    """

    def __init__(self):
        self._sm = get_sessionmaker()

    async def retrieve(self, campaign_id: int, query: str, k: int = 4) -> list[ContentSnippet]:
        q = (query or "").strip()
        if not q:
            return []
        # Limit query length to prevent pathological LIKE scans
        q = q[:128]
        async with self._sm() as s:
            stmt = (
                sa.select(ContentNode)
                .where(ContentNode.campaign_id == campaign_id)
                .where(
                    sa.or_(
                        ContentNode.title.ilike(f"%{q}%"),
                        ContentNode.player_text.ilike(f"%{q}%"),
                    )
                )
                .limit(k)
            )
            result = await s.execute(stmt)
            rows = list(result.scalars().all())
        return [
            ContentSnippet(
                id=n.id, node_type=n.node_type.value, title=n.title, text=n.player_text
            )
            for n in rows
        ]


def build_retriever(settings) -> BaseRetriever:
    # For now: only SQL fallback. Future: switch on settings.retrieval.provider
    return SqlFallbackRetriever()
