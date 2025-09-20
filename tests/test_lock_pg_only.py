import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.asyncio
async def test_pg_advisory_lock_path(monkeypatch):
    # Look for an explicit PG test URL; skip if missing.
    pg_url = os.environ.get("ADVENTORATOR_TEST_PG_URL") or os.environ.get("DATABASE_URL")
    if not pg_url or not (
        pg_url.startswith("postgresql://") or pg_url.startswith("postgresql+asyncpg://")
    ):
        pytest.skip("Postgres URL not provided; skipping PG-only advisory lock test")

    # Normalize to async driver
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Try to connect; skip if cannot
    try:
        engine = create_async_engine(pg_url, pool_size=1, max_overflow=0, pool_pre_ping=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
    except Exception as e:
        pytest.skip(f"Cannot connect to Postgres for advisory lock test: {e}")

    # Force settings loader to think we're on PG for this call
    monkeypatch.setenv("DATABASE_URL", pg_url)

    reset_counters()
    from Adventorator.services.lock_service import acquire_encounter_locks

    # Acquire and release within the context; should take the pg+inproc path and increment counters
    async with sm() as s:
        async with acquire_encounter_locks(s, encounter_id=9999, timeout_seconds=1.5):
            # Optionally try a tiny sleep to simulate contention-free acquire
            await asyncio.sleep(0)

    # Assert PG mode counter incremented
    assert get_counter("locks.mode.pg") >= 1
    # Should have at least one success and histogram count present
    # (indirectly via counters flattening)
    assert get_counter("locks.acquire.success") >= 1
