# src/Adventorator/db.py
from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from Adventorator.config import load_settings

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
_schema_initialized: bool = False


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        # Safer defaults per backend
        kwargs: dict[str, object] = {}
        if DATABASE_URL.startswith("sqlite+aiosqlite://"):
            # SQLite ignores pool_size; keep it minimal and avoid pre_ping
            # If using special file::memory:?cache=shared URI, enable uri flag
            connect_args = {"timeout": 30}
            if (
                DATABASE_URL.endswith("file::memory:?cache=shared")
                or "file::memory:?cache=shared" in DATABASE_URL
            ):
                connect_args["uri"] = True
            kwargs.update(connect_args=connect_args)
            # Critical for in-memory DBs: share a single connection so schema persists
            if ":memory:" in DATABASE_URL or "file::memory:?cache=shared" in DATABASE_URL:
                kwargs.update(poolclass=StaticPool)
            # Optionally force a single shared connection even for file-backed SQLite
            # to serialize writers during tests and avoid "database is locked".
            if os.environ.get("ADVENTORATOR_SQLITE_STATIC_POOL") == "1":
                kwargs.update(poolclass=StaticPool)
        elif DATABASE_URL.startswith("postgresql+asyncpg://"):
            # Production-oriented Postgres pool settings (per-instance)
            kwargs.update(
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
            )

        _engine = create_async_engine(DATABASE_URL, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
        # Emit a one-time sanitized connection config log (no password)
        try:  # defensive: never block startup on logging
            from sqlalchemy.engine import make_url  # local import to avoid unused at module load

            url = make_url(DATABASE_URL)
            backend = "postgres" if DATABASE_URL.startswith("postgresql") else (
                "sqlite" if DATABASE_URL.startswith("sqlite") else "other"
            )
            log.info(
                "db.connection.config",
                backend=backend,
                user=url.username or "",
                host=url.host or "",
                database=url.database or "",
                driver=url.drivername,
            )
            if backend == "postgres" and (not url.username or not url.password):
                log.warning(
                    "db.connection.missing_credentials",
                    has_user=bool(url.username),
                    has_password=bool(url.password),
                )
        except Exception:
            pass
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker  # type: ignore[return-value]


async def _ensure_schema_created_if_needed() -> None:
    """Ensure tables exist for in-memory SQLite during tests.

    In CI/tests we use an in-memory SQLite database. Even with StaticPool,
    some tests may access the engine before the session-scoped fixture runs.
    Creating the schema here is idempotent and fast for SQLite.
    """
    global _schema_initialized
    if _schema_initialized:
        return
    # Only auto-create for in-memory SQLite; avoid interfering with real DBs
    if DATABASE_URL.startswith("sqlite+aiosqlite://") and ":memory:" in DATABASE_URL:
        # Ensure models module is imported so all tables are registered
        try:
            from Adventorator import models as _models  # noqa: F401
        except Exception:
            # If import fails, proceed; create_all will just create what's known
            pass
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    _schema_initialized = True


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    # Defensive: ensure schema exists in in-memory test DBs BEFORE session open
    await _ensure_schema_created_if_needed()
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
