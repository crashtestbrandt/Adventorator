# src/Adventorator/responder.py

import httpx
import orjson
import structlog
from fastapi import Response

# Keep this module dependency-free of Settings to avoid import-time env errors
# (we don't actually need settings here)

__all__ = [
    "orjson_response",
    "respond_pong",
    "respond_deferred",
    "followup_message",
]


def orjson_response(data: dict) -> Response:
    return Response(content=orjson.dumps(data), media_type="application/json")


def respond_pong() -> Response:
    # Interaction callback type 1 (PONG)
    return orjson_response({"type": 1})


def respond_deferred() -> Response:
    # Interaction callback type 5 (DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE)
    return orjson_response({"type": 5})


async def followup_message(application_id: str, token: str, content: str, ephemeral: bool = False):
    """
    Send a follow-up message via webhook:
    POST https://discord.com/api/v10/webhooks/{application_id}/{token}
    """
    log = structlog.get_logger()
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}"
    flags = 64 if ephemeral else 0  # 64 = EPHEMERAL
    payload = {"content": content, "flags": flags}
    # Pre-send structured log: (avoid logging token/URL)
    try:
        log.info(
            "discord.followup.send",
            ephemeral=ephemeral,
            flags=flags,
            content_len=len(content or ""),
            content_preview=(content or "")[:120],
        )
    except Exception:
        pass
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            url, content=orjson.dumps(payload), headers={"Content-Type": "application/json"}
        )
        # Post-send structured log:
        try:
            log.info(
                "discord.followup.sent",
                http_status_code=r.status_code,
                rate_remaining=r.headers.get("X-RateLimit-Remaining"),
                    rate_reset_after=(
                        r.headers.get("X-RateLimit-Reset-After")
                        or r.headers.get("X-RateLimit-Reset")
                    ),
            )
        except Exception:
            pass
        try:
            r.raise_for_status()
        except Exception:
            try:
                log.error(
                    "discord.followup.error",
                    http_status_code=getattr(r, "status_code", None),
                    text_preview=(getattr(r, "text", "") or "")[:200],
                    exc_info=True,
                )
            except Exception:
                pass
            raise
