from __future__ import annotations

import asyncio

from Adventorator.db import session_scope
from Adventorator import repos


async def main() -> int:
    async with session_scope() as s:
        count = await repos.expire_stale_pending_actions(s)
    print(f"expired={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
