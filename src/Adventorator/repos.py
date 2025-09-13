# repos.py

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import models
from Adventorator.schemas import CharacterSheet


async def get_or_create_campaign(
    s: AsyncSession, guild_id: int, name: str = "Default"
) -> models.Campaign:
    q = await s.execute(select(models.Campaign).where(models.Campaign.guild_id == guild_id))
    obj = q.scalar_one_or_none()
    if obj:
        return obj
    obj = models.Campaign(guild_id=guild_id, name=name)
    s.add(obj)
    await _flush_retry(s)
    return obj


async def get_or_create_player(
    s: AsyncSession, discord_user_id: int, display_name: str
) -> models.Player:
    q = await s.execute(
        select(models.Player).where(models.Player.discord_user_id == discord_user_id)
    )
    obj = q.scalar_one_or_none()
    if obj:
        return obj
    obj = models.Player(discord_user_id=discord_user_id, display_name=display_name)
    s.add(obj)
    await _flush_retry(s)
    return obj


async def upsert_character(
    s: AsyncSession, campaign_id: int, player_id: int | None, sheet: CharacterSheet
) -> models.Character:
    q = await s.execute(
        select(models.Character).where(
            models.Character.campaign_id == campaign_id,
            models.Character.name == sheet.name,
        )
    )
    obj = q.scalar_one_or_none()
    if obj:
        obj.sheet = sheet.model_dump(by_alias=True)
        await _flush_retry(s)
        return obj
    obj = models.Character(
        campaign_id=campaign_id,
        player_id=player_id,
        name=sheet.name,
        sheet=sheet.model_dump(by_alias=True),
    )
    s.add(obj)
    await _flush_retry(s)
    return obj


async def get_character(s: AsyncSession, campaign_id: int, name: str) -> models.Character | None:
    q = await s.execute(
        select(models.Character).where(
            models.Character.campaign_id == campaign_id,
            models.Character.name == name,
        )
    )
    return q.scalar_one_or_none()


async def ensure_scene(s: AsyncSession, campaign_id: int, channel_id: int) -> models.Scene:
    q = await s.execute(select(models.Scene).where(models.Scene.channel_id == channel_id))
    sc = q.scalar_one_or_none()
    if sc:
        return sc
    sc = models.Scene(campaign_id=campaign_id, channel_id=channel_id)
    s.add(sc)
    await _flush_retry(s)
    return sc


async def list_character_names(s: AsyncSession, campaign_id: int) -> list[str]:
    """Return all character names in a campaign."""
    q = await s.execute(
        select(models.Character.name).where(models.Character.campaign_id == campaign_id)
    )
    return [row[0] for row in q.all()]


async def write_transcript(
    s: AsyncSession,
    campaign_id: int,
    scene_id: int | None,
    channel_id: int | None,
    author: str,
    content: str,
    author_ref: str | None = None,
    meta: dict | None = None,
    status: str | None = None,
) -> models.Transcript:
    t = models.Transcript(
        campaign_id=campaign_id,
        scene_id=scene_id,
        channel_id=channel_id,
        author=author,
        author_ref=author_ref,
        content=content,
        meta=meta or {},
        status=status or "complete",
    )
    s.add(t)
    await _flush_retry(s)
    return t


async def update_transcript_status(s: AsyncSession, transcript_id: int, status: str) -> None:
    q = await s.execute(select(models.Transcript).where(models.Transcript.id == transcript_id))
    t = q.scalar_one_or_none()
    if t:
        t.status = status
        await _flush_retry(s)


async def update_transcript_meta(
    s: AsyncSession, transcript_id: int, meta: dict | None = None
) -> None:
    q = await s.execute(select(models.Transcript).where(models.Transcript.id == transcript_id))
    t = q.scalar_one_or_none()
    if t:
        t.meta = meta or {}
        await _flush_retry(s)


async def _flush_retry(s: AsyncSession, attempts: int = 5, delay: float = 0.2) -> None:
    """Retry session.flush() on transient SQLite 'database is locked' errors.

    Exponential backoff: delay * 2^i between attempts.
    """
    for i in range(attempts):
        try:
            await s.flush()
            return
        except OperationalError as e:  # pragma: no cover - timing dependent
            msg = str(e).lower()
            if "database is locked" in msg or "database is busy" in msg:
                if i == attempts - 1:
                    raise
                await asyncio.sleep(delay * (2 ** i))
                continue
            raise


async def get_recent_transcripts(
    s: AsyncSession, scene_id: int, limit: int = 15, user_id: str | None = None
) -> list[models.Transcript]:
    """
    Fetches the most recent transcript entries for a given scene, optionally
    filtered by user_id, in chronological order.
    """
    stmt = select(models.Transcript).where(models.Transcript.scene_id == scene_id)
    if user_id is not None:
        stmt = stmt.where(models.Transcript.author_ref == user_id)
    stmt = stmt.order_by(models.Transcript.created_at.desc()).limit(limit)
    q = await s.execute(stmt)
    results = list(q.scalars().all())
    # chronological order (oldest -> newest)
    return list(results[::-1])
