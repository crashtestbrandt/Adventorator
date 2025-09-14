from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator.config import load_settings
from Adventorator.metrics import inc_counter, observe_histogram

log = structlog.get_logger()


_locks: dict[int, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _get_local_lock(encounter_id: int) -> asyncio.Lock:
    async with _locks_guard:
        lk = _locks.get(encounter_id)
        if lk is None:
            lk = asyncio.Lock()
            _locks[encounter_id] = lk
        return lk


@asynccontextmanager
async def acquire_encounter_locks(
    s: AsyncSession, *, encounter_id: int, timeout_seconds: float = 3.0
) -> AsyncIterator[None]:
    """Acquire in-process lock and Postgres advisory lock (if available).

    Always acquire the asyncio lock first to serialize within-process calls quickly.
    Then acquire the DB advisory lock as the source of truth. If the DB is not
    Postgres, skip advisory lock. Locks are released on exit.
    """
    local_lock = await _get_local_lock(encounter_id)
    settings = load_settings()
    mode = "inproc_only"
    await local_lock.acquire()
    try:
        # Try Postgres advisory lock
        if settings.database_url.startswith("postgresql") or settings.database_url.startswith(
            "postgresql+asyncpg"
        ):
            mode = "pg+inproc"
            try:
                # Use a 32-bit key space via two-int variant: (class=1001, key=encounter_id)
                # Try with a bounded wait by polling pg_try_advisory_lock
                waited_ms = 0
                step_ms = 50
                max_ms = int(timeout_seconds * 1000)
                while True:
                    q = await s.execute(
                        text("SELECT pg_try_advisory_lock(:c, :k)"),
                        {"c": 1001, "k": encounter_id},
                    )
                    ok = bool(q.scalar_one())
                    if ok:
                        break
                    if waited_ms >= max_ms:
                        inc_counter("locks.acquire.timeout")
                        observe_histogram("locks.wait_ms", waited_ms)
                        raise TimeoutError("advisory lock timeout")
                    await asyncio.sleep(step_ms / 1000)
                    waited_ms += step_ms
                inc_counter("locks.acquire.success")
                inc_counter("locks.mode.pg")
                observe_histogram("locks.wait_ms", waited_ms)
            except Exception:
                # If advisory lock cannot be acquired, release local and re-raise
                inc_counter("locks.acquire.error")
                raise
        else:
            inc_counter("locks.mode.inproc", 1)
        yield None
    finally:
        # Release advisory lock if we took it
        if mode == "pg+inproc":
            try:
                await s.execute(
                    text("SELECT pg_advisory_unlock(:c, :k)"),
                    {"c": 1001, "k": encounter_id},
                )
            except Exception:
                pass
        try:
            local_lock.release()
        except Exception:
            pass