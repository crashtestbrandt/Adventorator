#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from Adventorator.db import session_scope
from Adventorator.models import ContentNode, NodeType


async def _run(campaign_id: int, node_type: str, title: str, file_path: Path) -> None:
    text = file_path.read_text(encoding="utf-8")
    async with session_scope() as s:
        s.add(
            ContentNode(
                campaign_id=campaign_id,
                node_type=NodeType(node_type),
                title=title,
                player_text=text,
                gm_text=None,
                tags=[],
            )
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Import a Markdown file as a content node.")
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--node-type", choices=[t.value for t in NodeType], required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--file", type=Path, required=True)
    args = ap.parse_args()
    asyncio.run(_run(args.campaign_id, args.node_type, args.title, args.file))


if __name__ == "__main__":
    main()
