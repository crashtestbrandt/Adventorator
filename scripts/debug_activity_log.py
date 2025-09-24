#!/usr/bin/env python
"""Quick inspection helper for recent transcripts and linked activity logs.

Usage examples:

  PYTHONPATH=./src python scripts/debug_activity_log.py --limit 10
  PYTHONPATH=./src python scripts/debug_activity_log.py --scene 1 --limit 5
  PYTHONPATH=./src python scripts/debug_activity_log.py --activity --limit 20

Requires database + migrations applied. Uses async SQLAlchemy session_scope.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import select

from Adventorator import models
from Adventorator.config import load_settings
from Adventorator.db import session_scope


def human_row(obj: Any) -> dict[str, Any]:
    if isinstance(obj, models.Transcript):
        return {
            "type": "transcript",
            "id": obj.id,
            "scene_id": obj.scene_id,
            "author": obj.author,
            "activity_log_id": obj.activity_log_id,
            "status": obj.status,
            "created_at": obj.created_at.isoformat(),
            "content": (obj.content[:80] + "...") if len(obj.content) > 80 else obj.content,
        }
    if isinstance(obj, models.ActivityLog):
        return {
            "type": "activity_log",
            "id": obj.id,
            "scene_id": obj.scene_id,
            "event_type": obj.event_type,
            "actor_ref": obj.actor_ref,
            "summary": obj.summary,
            "correlation_id": obj.correlation_id,
            "request_id": obj.request_id,
            "created_at": obj.created_at.isoformat(),
        }
    return {"repr": repr(obj)}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect recent transcripts/activity logs")
    parser.add_argument("--scene", type=int, default=None, help="Filter by scene id")
    parser.add_argument("--limit", type=int, default=15, help="Max rows per entity to show")
    parser.add_argument(
        "--activity", action="store_true", help="Show activity logs in addition to transcripts"
    )
    args = parser.parse_args()

    settings = load_settings()
    print(f"DB URL: {settings.database_url}")

    async with session_scope() as s:
        # Transcripts
        stmt = select(models.Transcript)
        if args.scene is not None:
            stmt = stmt.where(models.Transcript.scene_id == args.scene)
        stmt = stmt.order_by(models.Transcript.created_at.desc()).limit(args.limit)
        q = await s.execute(stmt)
        transcripts = list(q.scalars().all())
        print(f"Transcripts (newest -> oldest, limit {args.limit}):")
        for t in transcripts:
            print(human_row(t))

        if args.activity:
            astmt = select(models.ActivityLog)
            if args.scene is not None:
                astmt = astmt.where(models.ActivityLog.scene_id == args.scene)
            astmt = astmt.order_by(models.ActivityLog.created_at.desc()).limit(args.limit)
            aq = await s.execute(astmt)
            logs = list(aq.scalars().all())
            print(f"\nActivity Logs (newest -> oldest, limit {args.limit}):")
            for a in logs:
                print(human_row(a))

        # Quick join insight: show transcripts with a linked activity_log_id
        linked = [t for t in transcripts if t.activity_log_id is not None]
        if linked:
            print(f"\nLinked transcripts (count={len(linked)}):")
            for t in linked:
                print({"tx_id": t.id, "activity_log_id": t.activity_log_id, "author": t.author})
        else:
            print("\nNo transcripts in this slice have activity_log_id set.")

if __name__ == "__main__":
    asyncio.run(main())
