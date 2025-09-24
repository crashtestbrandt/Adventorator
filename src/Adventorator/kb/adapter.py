"""KB adapter for read-only entity resolution leveraging existing repos.

Provides deterministic, repo-backed entity lookup with caching and metrics.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import models
from Adventorator.db import get_sessionmaker
from Adventorator.metrics import inc_counter


@dataclass(frozen=True)
class Candidate:
    """A potential entity match with ID and label."""

    id: str
    label: str


@dataclass(frozen=True)
class KBResolution:
    """Result of KB entity resolution with canonical ID and alternatives."""

    canonical_id: str | None
    candidates: list[Candidate]
    reason: str | None
    source: str


class _KBCache:
    """Simple TTL-based cache with size limits."""

    def __init__(self, max_size: int = 1024, ttl_s: float = 60.0):
        self._cache: dict[str, tuple[float, KBResolution]] = {}
        self._max_size = max_size
        self._ttl_s = ttl_s
        self._log = structlog.get_logger()

    def get(self, key: str) -> KBResolution | None:
        """Get cached result if not expired."""
        now = time.time()
        if key in self._cache:
            timestamp, result = self._cache[key]
            if now - timestamp <= self._ttl_s:
                inc_counter("kb.lookup.hit")
                return result
            # Expired, remove it
            del self._cache[key]
            inc_counter("kb.cache.evicted")

        inc_counter("kb.lookup.miss")
        return None

    def set(self, key: str, result: KBResolution) -> None:
        """Set cached result, evicting old entries if needed."""
        now = time.time()

        # Evict expired entries first
        expired_keys = [k for k, (ts, _) in self._cache.items() if now - ts > self._ttl_s]
        for k in expired_keys:
            del self._cache[k]
            inc_counter("kb.cache.evicted")

        # Evict LRU-ish if we're over size
        if len(self._cache) >= self._max_size:
            # Remove the oldest entry
            oldest_key = min(self._cache.items(), key=lambda kv: kv[1][0])[0]
            del self._cache[oldest_key]
            inc_counter("kb.cache.evicted")

        # Set new value
        self._cache[key] = (now, result)


class KBAdapter:
    """Knowledge Base adapter handling entity resolution with caching."""

    def __init__(
        self,
        sessionmaker: Callable[[], AsyncSession] | None = None,
        *,
        cache_max_size: int = 1024,
        cache_ttl_s: float = 60.0,
        max_candidates: int = 5,
        timeout_s: float = 0.05,
        max_terms_per_call: int = 20,
    ):
        self._sm = sessionmaker or get_sessionmaker()
        self._cache = _KBCache(max_size=cache_max_size, ttl_s=cache_ttl_s)
        self._max_candidates = max_candidates
        self._timeout_s = timeout_s
        self._max_terms_per_call = max_terms_per_call
        self._log = structlog.get_logger()

    async def resolve_entity(
        self,
        term: str,
        *,
        limit: int = 5,
        timeout_s: float | None = None,
    ) -> KBResolution:
        """Resolve a single entity term to canonical ID and candidates."""
        if not term or not term.strip():
            return KBResolution(
                canonical_id=None,
                candidates=[],
                reason="Empty term",
                source="repo",
            )

        # Use provided timeout or default
        actual_timeout = timeout_s if timeout_s is not None else self._timeout_s
        actual_limit = min(limit, self._max_candidates)

        # Normalize term for consistent caching
        normalized_term = term.strip().lower()
        cache_key = f"single:{normalized_term}:{actual_limit}"

        # Check cache first
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Perform lookup with timeout
        try:
            result = await asyncio.wait_for(
                self._lookup_single(normalized_term, actual_limit),
                timeout=actual_timeout,
            )
        except asyncio.TimeoutError:
            inc_counter("kb.lookup.timeout")
            result = KBResolution(
                canonical_id=None,
                candidates=[],
                reason=f"Timeout after {actual_timeout}s",
                source="repo",
            )
        except Exception as e:  # pragma: no cover - defensive
            self._log.warning("kb.lookup.error", term=normalized_term, error=str(e))
            result = KBResolution(
                canonical_id=None,
                candidates=[],
                reason=f"Error: {e}",
                source="repo",
            )

        # Cache and return
        self._cache.set(cache_key, result)
        return result

    async def bulk_resolve(
        self,
        terms: list[str],
        *,
        limit: int = 5,
        timeout_s: float | None = None,
        max_terms: int | None = None,
    ) -> list[KBResolution]:
        """Resolve multiple entity terms in batch."""
        if not terms:
            return []

        # Respect max_terms limit
        actual_max_terms = max_terms if max_terms is not None else self._max_terms_per_call
        limited_terms = terms[:actual_max_terms]

        # Use provided timeout or default
        actual_timeout = timeout_s if timeout_s is not None else self._timeout_s

        # Resolve each term but apply only a bulk-level timeout (no per-task timeouts)
        async def _resolve_no_timeout(t: str) -> KBResolution:
            if not t or not t.strip():
                return KBResolution(
                    canonical_id=None, candidates=[], reason="Empty term", source="repo"
                )
            normalized = t.strip().lower()
            actual_limit = min(limit, self._max_candidates)
            cache_key = f"single:{normalized}:{actual_limit}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            try:
                res = await self._lookup_single(normalized, actual_limit)
            except Exception as e:  # pragma: no cover - defensive
                self._log.warning("kb.lookup.error", term=normalized, error=str(e))
                res = KBResolution(
                    canonical_id=None,
                    candidates=[],
                    reason=f"Error: {e}",
                    source="repo",
                )
            self._cache.set(cache_key, res)
            return res

        tasks = [_resolve_no_timeout(term) for term in limited_terms]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=actual_timeout * max(1, len(limited_terms)),
            )
        except asyncio.TimeoutError:
            inc_counter("kb.lookup.timeout")
            # Return timeout results for all terms
            return [
                KBResolution(
                    canonical_id=None,
                    candidates=[],
                    reason=f"Bulk timeout after {actual_timeout * max(1, len(limited_terms))}s",
                    source="repo",
                )
                for _ in limited_terms
            ]

        # Handle any exceptions in individual results
        final_results: list[KBResolution] = []
        for result in results:
            if isinstance(result, BaseException):
                final_results.append(
                    KBResolution(
                        canonical_id=None,
                        candidates=[],
                        reason=f"Error: {result}",
                        source="repo",
                    )
                )
            else:
                # mypy: result is KBResolution here
                final_results.append(result)  # type: ignore[arg-type]

        return final_results

    async def _lookup_single(self, normalized_term: str, limit: int) -> KBResolution:
        """Perform actual database lookup for a single term."""
        candidates: list[Candidate] = []
        canonical_id: str | None = None
        reason: str | None = None

        # Use async session; support awaitable sessionmaker callables from tests
        sm_ctx = self._sm()
        if asyncio.iscoroutine(sm_ctx):  # e.g., AsyncMock returning a coroutine
            sm_ctx = await sm_ctx
        async with sm_ctx as session:
            assert isinstance(session, AsyncSession) or hasattr(session, "execute"), (
                "Session must be an AsyncSession-like object"
            )

            # Look up in character names first (most likely canonical entities)
            char_query = (
                select(models.Character)
                .where(models.Character.name.ilike(f"%{normalized_term}%"))
                .limit(limit)
            )
            char_result = await session.execute(char_query)
            scalars_obj = char_result.scalars()
            if asyncio.iscoroutine(scalars_obj):
                scalars_obj = await scalars_obj
            all_obj = scalars_obj.all()
            if asyncio.iscoroutine(all_obj):
                characters = await all_obj
            else:
                characters = all_obj

            for char in characters:
                candidates.append(Candidate(id=f"character:{char.id}", label=char.name))
                # First exact match becomes canonical
                if canonical_id is None and char.name.lower() == normalized_term:
                    canonical_id = f"character:{char.id}"

            # If we need more candidates and haven't hit limit, look in other entities
            if len(candidates) < limit:
                remaining = limit - len(candidates)

                # Look in campaign names
                campaign_query = (
                    select(models.Campaign)
                    .where(models.Campaign.name.ilike(f"%{normalized_term}%"))
                    .limit(remaining)
                )
                campaign_result = await session.execute(campaign_query)
                camp_scalars = campaign_result.scalars()
                if asyncio.iscoroutine(camp_scalars):
                    camp_scalars = await camp_scalars
                camp_all = camp_scalars.all()
                if asyncio.iscoroutine(camp_all):
                    campaigns = await camp_all
                else:
                    campaigns = camp_all

                for campaign in campaigns:
                    candidates.append(Candidate(id=f"campaign:{campaign.id}", label=campaign.name))
                    # First exact match becomes canonical if none found yet
                    if canonical_id is None and campaign.name.lower() == normalized_term:
                        canonical_id = f"campaign:{campaign.id}"

        # Sort candidates by relevance (exact matches first, then alphabetical)
        def sort_key(c: Candidate) -> tuple[int, str]:
            exact_match = 0 if c.label.lower() == normalized_term else 1
            return (exact_match, c.label.lower())

        candidates.sort(key=sort_key)
        # Enforce candidate limit even if upstream mocks bypass SQL query limits
        if len(candidates) > limit:
            candidates = candidates[:limit]

        # Determine reason
        if candidates:
            reason = "Exact match found" if canonical_id else "Partial matches found"
        else:
            reason = "No matches found"

        return KBResolution(
            canonical_id=canonical_id,
            candidates=candidates,
            reason=reason,
            source="repo",
        )


# Global instance for easy access
_kb_adapter: KBAdapter | None = None


def get_kb_adapter(**kwargs) -> KBAdapter:
    """Get or create the global KB adapter instance."""
    global _kb_adapter
    if _kb_adapter is None:
        _kb_adapter = KBAdapter(**kwargs)
    return _kb_adapter


# Convenience functions matching the interface specification
async def resolve_entity(
    term: str, *, limit: int = 5, timeout_s: float | None = None
) -> KBResolution:
    """Convenience function for single entity resolution."""
    adapter = get_kb_adapter()
    return await adapter.resolve_entity(term, limit=limit, timeout_s=timeout_s)


async def bulk_resolve(
    terms: list[str],
    *,
    limit: int = 5,
    timeout_s: float | None = None,
    max_terms: int | None = None,
) -> list[KBResolution]:
    """Convenience function for bulk entity resolution."""
    adapter = get_kb_adapter()
    return await adapter.bulk_resolve(terms, limit=limit, timeout_s=timeout_s, max_terms=max_terms)
