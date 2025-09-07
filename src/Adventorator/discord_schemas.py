# discord_schemas.py

from typing import Any, Literal

from pydantic import BaseModel


class User(BaseModel):
    id: str
    username: str
    discriminator: str | None = None
    avatar: str | None = None
    global_name: str | None = None


class Member(BaseModel):
    user: User
    nick: str | None = None
    roles: list[str] = []
    joined_at: str | None = None
    permissions: str | None = None


class Channel(BaseModel):
    id: str
    guild_id: str | None = None
    name: str | None = None
    type: int | None = None


class Guild(BaseModel):
    id: str
    locale: str | None = None
    features: list[str] = []


class InteractionData(BaseModel):
    id: str | None = None
    name: str | None = None
    type: int | None = None
    options: list[dict[str, Any]] | None = None


class Interaction(BaseModel):
    id: str
    type: int
    token: str
    application_id: str
    data: InteractionData | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    member: Member | None = None
    guild: Guild | None = None
    channel: Channel | None = None


class DeferResponse(BaseModel):
    type: Literal[5]  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE


class PongResponse(BaseModel):
    type: Literal[1]  # PONG for pings (type 1)
