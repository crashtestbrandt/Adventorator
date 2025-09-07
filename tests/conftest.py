# tests/conftest.py

import os
import gc
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure the app code (which uses Adventorator.db.get_engine) also points to an
# in-memory database during tests, before any app modules are imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from Adventorator.db import Base, get_engine


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


@pytest.fixture(scope="session")
async def test_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Use in-memory DB for tests with a single shared connection (StaticPool).
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, echo=False, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
    # Clean up any lingering references to connections
    # that could trigger ResourceWarnings
    gc.collect()


@pytest.fixture
async def db(test_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with test_sessionmaker() as s:
        try:
            yield s
        finally:
            # Ensure clean rollback and explicit close to release aiosqlite connection
            await s.rollback()
            await s.close()
