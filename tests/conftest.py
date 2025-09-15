# tests/conftest.py

import gc
import os
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure the app code (which uses Adventorator.db.get_engine) also points to a
# test database before any app modules are imported. Default to an in-memory DB
# for speed, but allow switching to a file-backed SQLite with WAL to reduce
# write-lock contention on platforms where concurrent writers are more common.
if os.environ.get("ADVENTORATOR_TEST_USE_FILE_SQLITE") == "1":
    # File-backed SQLite in the local workspace; enables WAL and better concurrency.
    test_db_path = os.path.abspath(os.environ.get(
        "ADVENTORATOR_TEST_DB_PATH", "./adventorator_test.sqlite3"
    ))
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db_path}"
else:
    # Use a pure process-local in-memory DB.
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# For CI stability, default to StaticPool for SQLite to avoid cross-connection
# write locks during concurrent async usage in tests. Can be disabled by setting 0.
if os.environ.get("ADVENTORATOR_SQLITE_STATIC_POOL", "1") != "0":
    os.environ["ADVENTORATOR_SQLITE_STATIC_POOL"] = "1"

# Ensure the DB module uses our chosen DATABASE_URL (TOML has higher precedence than env)
# so we must override the module-level constant before any engine is created.
import Adventorator.db as _db

_db.DATABASE_URL = os.environ["DATABASE_URL"]
_db._engine = None
_db._sessionmaker = None
_db._schema_initialized = False

# Import models so all ORM tables are registered on Base.metadata before create_all
from Adventorator import models as _models  # noqa: F401,E402
from Adventorator.db import Base, get_engine, get_sessionmaker  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _app_engine_lifecycle() -> AsyncIterator[None]:
    """Create tables on the app engine and dispose it after the test session.

    This prevents sporadic ResourceWarnings about unclosed sqlite connections
    from engines created by the application code during tests.
    """
    # Allow DB-less unit tests to opt out
    if os.environ.get("ADVENTORATOR_TEST_SKIP_DB") == "1":
        yield None
        return
    engine = get_engine()
    async with engine.begin() as conn:
        # For file-backed SQLite, enable WAL for fewer write locks
        if conn.dialect.name == "sqlite":
            try:
                await conn.execute(sa.text("PRAGMA journal_mode=WAL"))
                await conn.execute(sa.text("PRAGMA synchronous=NORMAL"))
            except Exception:
                # PRAGMA may not apply for in-memory DBs; ignore
                pass
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield None
    finally:
        await engine.dispose()
    gc.collect()


# Ensure a clean slate before each test. Since some helpers commit using
# session_scope(), we must clear committed rows across the shared DB.
# In strict mode (default), we drop and recreate the schema each test to
# guarantee isolation on SQLite. Disable by setting ADVENTORATOR_TEST_STRICT_RESET=0.
@pytest.fixture(autouse=True)
async def _reset_db_per_test() -> AsyncIterator[None]:
    # Allow DB-less unit tests to opt out
    if os.environ.get("ADVENTORATOR_TEST_SKIP_DB") == "1":
        yield None
        return
    engine = get_engine()
    strict_reset = os.environ.get("ADVENTORATOR_TEST_STRICT_RESET", "1") != "0"
    async with engine.begin() as conn:
        is_sqlite = conn.dialect.name == "sqlite"
        if strict_reset:
            # Recreate full schema to avoid any uniqueness residue across tests
            if is_sqlite:
                await conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            if is_sqlite:
                await conn.execute(sa.text("PRAGMA foreign_keys=ON"))
        else:
            # Lightweight delete for speed
            if is_sqlite:
                await conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
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
    # Defensive: hard reset schema to guarantee isolation for this test
    engine = get_engine()
    async with engine.begin() as conn:
        is_sqlite = conn.dialect.name == "sqlite"
        if is_sqlite:
            await conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        if is_sqlite:
            await conn.execute(sa.text("PRAGMA foreign_keys=ON"))
    sm = get_sessionmaker()
    async with sm() as s:
        try:
            yield s
        finally:
            # Ensure clean rollback and explicit close to release aiosqlite connection
            await s.rollback()
            await s.close()
