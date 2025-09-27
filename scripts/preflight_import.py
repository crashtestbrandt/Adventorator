#!/usr/bin/env python3
"""Preflight checks before running the DB-backed importer.

Checks:
- Database connectivity (async engine)
- Presence of required tables (campaigns, events, import_logs)
- Optionally runs `make alembic-up` if import_logs is missing
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import subprocess
from pathlib import Path
import sys

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text  # type: ignore
from Adventorator.db import get_engine  # type: ignore


REQUIRED_TABLES = ("campaigns", "events", "import_logs")


async def check_tables() -> dict[str, bool]:
    engine = get_engine()
    ok: dict[str, bool] = {}
    async with engine.connect() as conn:
        for tbl in REQUIRED_TABLES:
            # Works on Postgres, and SQLite will respond to this PRAGMA-like select via sqlite_master
            try:
                if engine.url.get_backend_name().startswith("postgres"):
                    res = await conn.execute(
                        text("SELECT to_regclass(:tname)"), {"tname": f"public.{tbl}"}
                    )
                    ok[tbl] = res.scalar() is not None
                else:
                    res = await conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                        {"t": tbl},
                    )
                    ok[tbl] = res.first() is not None
            except Exception:
                ok[tbl] = False
    return ok


def run_make_alembic_up() -> int:
    # Run via make to honor repo conventions
    cmd = ["make", "alembic-up"]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.call(cmd, env=os.environ.copy())


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight checks for DB-backed import")
    ap.add_argument("--auto-migrate", action="store_true", help="Run make alembic-up if needed")
    args = ap.parse_args()

    try:
        tbls = asyncio.run(check_tables())
    except Exception as exc:
        print("Database connection failed:", exc)
        return 1

    missing = [t for t, present in tbls.items() if not present]
    print("Preflight table check:")
    for t in REQUIRED_TABLES:
        print(f"  - {t}: {'OK' if tbls.get(t) else 'MISSING'}")

    if missing and args.auto_migrate:
        code = run_make_alembic_up()
        if code != 0:
            print("Migration failed; please inspect output")
            return code
        # Re-check
        tbls = asyncio.run(check_tables())
        missing = [t for t, present in tbls.items() if not present]
        print("After migration:")
        for t in REQUIRED_TABLES:
            print(f"  - {t}: {'OK' if tbls.get(t) else 'MISSING'}")

    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
