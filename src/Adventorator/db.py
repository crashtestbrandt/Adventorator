# src/Adventorator/db.py
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from Adventorator.config import load_settings
import structlog

settings = load_settings()
log = structlog.get_logger()


def _normalize_url(url: str) -> str:
    # Upgrade to async drivers if user supplies sync URLs
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


DATABASE_URL = _normalize_url(settings.database_url)


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        # Safer defaults per backend
        kwargs: dict[str, object] = {}
        if DATABASE_URL.startswith("sqlite+aiosqlite://"):
            # SQLite ignores pool_size; keep it minimal and avoid pre_ping
            kwargs.update(connect_args={"timeout": 30})
        else:
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=10)

        _engine = create_async_engine(DATABASE_URL, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker  # type: ignore[return-value]


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as s:
        try:
            yield s
            await s.commit()
        except:  # noqa: E722
            # Log with full exception info for observability
            log.error("db.session.error", exc_info=True)
            await s.rollback()
            raise
