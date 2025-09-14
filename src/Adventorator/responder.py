import httpx
import orjson
import structlog
from fastapi import Response

from Adventorator.config import Settings

__all__ = [
    "orjson_response",
    "respond_pong",
    "respond_deferred",
    "followup_message",
]


def orjson_response(data: dict) -> Response:
    return Response(content=orjson.dumps(data), media_type="application/json")


def respond_pong() -> Response:
    return orjson_response({"type": 1})


def respond_deferred() -> Response:
    return orjson_response({"type": 5})


async def followup_message(
    application_id: str,
    token: str,
    content: str,
    ephemeral: bool = False,
    *,
    settings: Settings,
    webhook_base_url: str | None = None,
):
    """
    Send a follow-up message via webhook.
    Uses discord_webhook_url_override from settings if present.
    """
    log = structlog.get_logger()
    # Per-request override (highest precedence) > process settings override > Discord API
    base_url = (
        (webhook_base_url or "").strip() or settings.discord_webhook_url_override or "https://discord.com/api/v10"
    )
    url = f"{base_url.rstrip('/')}/webhooks/{application_id}/{token}"

    flags = 64 if ephemeral else 0
    payload = {"content": content, "flags": flags}
    log.info(
        "discord.followup.send",
        target_url=url,
        ephemeral=ephemeral,
        content_len=len(content or ""),
    )

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(
                url, content=orjson.dumps(payload), headers={"Content-Type": "application/json"}
            )
            r.raise_for_status()
            log.info("discord.followup.sent", http_status_code=r.status_code)
        except httpx.RequestError as e:
            log.error("discord.followup.network_error", target_url=str(e.request.url), error=str(e))
            if not settings.discord_webhook_url_override:
                raise
        except httpx.HTTPStatusError as e:
            log.error(
                "discord.followup.http_error",
                http_status_code=e.response.status_code,
                text_preview=(e.response.text or "")[:200],
            )
            if not settings.discord_webhook_url_override:
                raise