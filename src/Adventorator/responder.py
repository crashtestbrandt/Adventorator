# src/Adventorator/responder.py

from fastapi import Response
import httpx
import orjson

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
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}"
    flags = 64 if ephemeral else 0  # 64 = EPHEMERAL
    payload = {"content": content, "flags": flags}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, content=orjson.dumps(payload), headers={"Content-Type": "application/json"})
        r.raise_for_status()
