from __future__ import annotations

import re
import time
from dataclasses import dataclass

import sqlalchemy as sa
import structlog

from Adventorator.db import get_sessionmaker
from Adventorator.metrics import inc_counter
from Adventorator.models import ContentNode

log = structlog.get_logger()


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
        start = time.time()
        inc_counter("retrieval.calls")
        q = (query or "").strip()
        if not q:
            return []
        # Limit query length to prevent pathological LIKE scans
        q = q[:128]
        try:
            async with self._sm() as s:
                # Tokenize query into alphanumeric terms and require all terms to match
                terms = [t for t in re.findall(r"[A-Za-z0-9]+", q.lower()) if t]
                if not terms:
                    return []
                and_clauses = []
                for t in terms:
                    pat = f"%{t}%"
                    and_clauses.append(
                        sa.or_(
                            ContentNode.title.ilike(pat),
                            ContentNode.player_text.ilike(pat),
                            # Allow matches against GM notes for recall quality,
                            # but never expose gm_text in returned snippets.
                            ContentNode.gm_text.ilike(pat),
                        )
                    )
                stmt = sa.select(ContentNode).where(ContentNode.campaign_id == campaign_id)
                if and_clauses:
                    stmt = stmt.where(sa.and_(*and_clauses))
                stmt = stmt.limit(k)
                result = await s.execute(stmt)
                rows = list(result.scalars().all())
            inc_counter("retrieval.snippets", value=len(rows))
            return [
                ContentSnippet(
                    id=n.id, node_type=n.node_type.value, title=n.title, text=n.player_text
                )
                for n in rows
            ]
        except Exception:
            inc_counter("retrieval.errors")
            log.warning("retrieval.sql.error", exc_info=True)
            return []
        finally:
            dur_ms = int((time.time() - start) * 1000)
            inc_counter("retrieval.latency_ms", value=dur_ms)


def build_retriever(settings) -> BaseRetriever:
    # For now: only SQL fallback. Future: switch on settings.retrieval.provider
    return SqlFallbackRetriever()
