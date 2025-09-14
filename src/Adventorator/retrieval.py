from __future__ import annotations

import re
import time
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession] | None = None):
        """Create a SQL fallback retriever.

        Parameters
        - sessionmaker: An async session factory to use for DB access. Injecting this
          improves testability and follows the codebase's DI patterns.
        """
        self._sm = sessionmaker or get_sessionmaker()

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
                # Tokenize query into alphanumeric terms and filter common stopwords
                terms = [t for t in re.findall(r"[A-Za-z0-9]+", q.lower()) if t]
                stopwords = {
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "of",
                    "to",
                    "in",
                    "on",
                    "with",
                    "at",
                    "by",
                    "for",
                    "from",
                    "is",
                    "are",
                    "be",
                    "was",
                    "were",
                    # common chatty verbs/prompts
                    "please",
                    "describe",
                    "tell",
                    "show",
                    "about",
                    "look",
                    "examine",
                    "inspect",
                }
                terms = [t for t in terms if t not in stopwords]
                if not terms:
                    return []
                # Build a broad OR across tokens (each token matches title/player/gm_text)
                or_clauses = []
                for t in terms:
                    pat = f"%{t}%"
                    or_clauses.append(
                        sa.or_(
                            ContentNode.title.ilike(pat),
                            ContentNode.player_text.ilike(pat),
                            # Allow matches against GM notes for recall quality,
                            # but never expose gm_text in returned snippets.
                            ContentNode.gm_text.ilike(pat),
                        )
                    )
                stmt = sa.select(ContentNode).where(ContentNode.campaign_id == campaign_id)
                if or_clauses:
                    stmt = stmt.where(sa.or_(*or_clauses))
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
    return SqlFallbackRetriever(get_sessionmaker())
