# tests/conftest.py

import gc
import os
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure the app code (which uses Adventorator.db.get_engine) also points to a
# shared in-memory database during tests, before any app modules are imported.
# Use a pure process-local in-memory DB to avoid creating a stray file named
# literally "file::memory:" on disk. Tests use a single engine from app code.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Import models so all ORM tables are registered on Base.metadata before create_all
from Adventorator import models as _models  # noqa: F401
from Adventorator.db import Base, get_engine, get_sessionmaker


@pytest.fixture(scope="session", autouse=True)
async def _app_engine_lifecycle() -> AsyncIterator[None]:
    """Create tables on the app engine and dispose it after the test session.

    This prevents sporadic ResourceWarnings about unclosed sqlite connections
    from engines created by the application code during tests.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield None
    finally:
        await engine.dispose()
    gc.collect()


# Ensure a clean slate before each test. Since some helpers commit using
# session_scope(), we must clear committed rows across the shared in-memory DB.
@pytest.fixture(autouse=True)
async def _reset_db_per_test() -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        # Defensive: ensure schema exists (idempotent for SQLite in-memory)
        await conn.run_sync(Base.metadata.create_all)
        # Disable FKs to allow arbitrary delete order (SQLite only)
        is_sqlite = conn.dialect.name == "sqlite"
        if is_sqlite:
            await conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        # Purge all known tables, ignoring any that may not yet exist
        for table in reversed(Base.metadata.sorted_tables):
            try:
                await conn.execute(table.delete())
            except sa.exc.OperationalError as e:
                if is_sqlite and "no such table" in str(e).lower():
                    continue
                raise
        if is_sqlite:
            await conn.execute(sa.text("PRAGMA foreign_keys=ON"))
    yield None


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as s:
        try:
            yield s
        finally:
            # Ensure clean rollback and explicit close to release aiosqlite connection
            await s.rollback()
            await s.close()
