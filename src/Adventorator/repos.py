# repos.py

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import models
from Adventorator.events import envelope as event_envelope
from Adventorator.metrics import inc_counter
from Adventorator.schemas import CharacterSheet

_MAX_ACTIVITY_SUMMARY_LEN = 160
_MAX_ACTIVITY_PAYLOAD_BYTES = 4096


def _clamp_summary(summary: str, *, max_length: int = _MAX_ACTIVITY_SUMMARY_LEN) -> str:
    text = (summary or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        canonical = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        return {"error": "unserializable"}
    encoded = json.dumps(canonical, ensure_ascii=False).encode("utf-8")
    if len(encoded) <= _MAX_ACTIVITY_PAYLOAD_BYTES:
        return canonical
    return {"truncated": True}


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


async def get_character_by_id(
    s: AsyncSession, *, campaign_id: int, character_id: int
) -> models.Character | None:
    q = await s.execute(
        select(models.Character).where(
            models.Character.campaign_id == campaign_id,
            models.Character.id == character_id,
        )
    )
    return q.scalar_one_or_none()


async def normalize_actor_ref(
    s: AsyncSession, *, campaign_id: int, ident: str | int | None
) -> str | None:
    """Normalize actor identifier to a display string (character name when possible).

    - If ident is int-like, try to resolve character by id in the campaign.
    - If ident is a non-empty string, return as-is.
    - Otherwise, return None.
    """
    if ident is None:
        return None
    # Try int-like first
    char_id: int | None = None
    if isinstance(ident, int):
        char_id = ident
    elif isinstance(ident, str):
        try:
            char_id = int(ident)
        except Exception:
            # Not an int-like string; assume it's already a name/ref
            return ident if ident.strip() else None
    if char_id is not None:
        try:
            ch = await get_character_by_id(s, campaign_id=campaign_id, character_id=char_id)
            if ch is not None and getattr(ch, "name", None):
                return str(ch.name)
        except Exception:
            pass
        # Fallback to the numeric id string
        return str(char_id)
    return None


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
    activity_log_id: int | None = None,
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
        activity_log_id=activity_log_id,
    )
    s.add(t)
    await _flush_retry(s)
    if activity_log_id is not None:
        inc_counter("activity_log.linked_to_transcript")
    return t


async def create_activity_log(
    s: AsyncSession,
    *,
    campaign_id: int,
    scene_id: int | None,
    actor_ref: str | None,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> models.ActivityLog:
    obj = models.ActivityLog(
        campaign_id=campaign_id,
        scene_id=scene_id,
        actor_ref=actor_ref,
        event_type=event_type,
        summary=_clamp_summary(summary),
        payload=_sanitize_payload(payload),
        correlation_id=correlation_id,
        request_id=request_id,
    )
    s.add(obj)
    await _flush_retry(s)
    inc_counter("activity_log.created")
    return obj


async def update_transcript_status(s: AsyncSession, transcript_id: int, status: str) -> None:
    q = await s.execute(select(models.Transcript).where(models.Transcript.id == transcript_id))
    t = q.scalar_one_or_none()
    if t:
        t.status = status
        await _flush_retry(s)


async def link_transcript_activity_log(
    s: AsyncSession, *, transcript_id: int, activity_log_id: int | None
) -> None:
    """Set activity_log_id for an existing transcript if not already set.

    Idempotent: only updates when different. Safe to call after creating
    an ActivityLog if initial transcript write did not include linkage.
    """
    if activity_log_id is None:
        return
    # Suppress autoflush so we don't flush unrelated pending objects while checking parents.
    with s.no_autoflush:
        q = await s.execute(select(models.Transcript).where(models.Transcript.id == transcript_id))
        t = q.scalar_one_or_none()
        # Verify activity log exists before linking to avoid FK violation in environments
        # where the log may have been created in a different uncommitted session.
        act = await s.get(models.ActivityLog, activity_log_id)
    if not act:
        # Skip linking silently; caller can retry later if needed.
        return
    if t and getattr(t, "activity_log_id", None) != activity_log_id:
        t.activity_log_id = activity_log_id
        try:
            await _flush_retry(s)
        except IntegrityError:
            # Re-check existence; if truly missing, drop link to prevent cascading failures.
            with s.no_autoflush:
                act2 = await s.get(models.ActivityLog, activity_log_id)
            if act2 is None and t.activity_log_id == activity_log_id:
                t.activity_log_id = None
            else:
                raise


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
                await asyncio.sleep(delay * (2**i))
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


async def healthcheck(s: AsyncSession) -> None:
    """Lightweight DB check to confirm connectivity and basic query works."""
    await s.execute(select(models.Campaign).limit(1))


async def get_latest_event_id_for_scene(s: AsyncSession, *, scene_id: int) -> int | None:
    """Return the most recent Event.id for a scene, or None if none exist.

    This is used to key renderer cache by the last event applied to the scene.
    """
    stmt = (
        select(models.Event.id)
        .where(models.Event.scene_id == scene_id)
        .order_by(models.Event.id.desc())
        .limit(1)
    )
    q = await s.execute(stmt)
    row = q.first()
    if not row:
        return None
    return int(row[0])


# -----------------------------
# Encounters & Combatants (Phase 10)
# -----------------------------


async def create_encounter(s: AsyncSession, *, scene_id: int) -> models.Encounter:
    enc = models.Encounter(scene_id=scene_id)
    s.add(enc)
    await _flush_retry(s)
    return enc


async def get_encounter_by_id(s: AsyncSession, *, encounter_id: int) -> models.Encounter | None:
    q = await s.execute(select(models.Encounter).where(models.Encounter.id == encounter_id))
    return q.scalar_one_or_none()


async def get_active_or_setup_encounter_for_scene(
    s: AsyncSession, *, scene_id: int
) -> models.Encounter | None:
    q = await s.execute(
        select(models.Encounter)
        .where(
            models.Encounter.scene_id == scene_id,
            models.Encounter.status.in_(
                [models.EncounterStatus.setup, models.EncounterStatus.active]
            ),
        )
        .order_by(models.Encounter.id.desc())
        .limit(1)
    )
    return q.scalar_one_or_none()


async def update_encounter_state(
    s: AsyncSession,
    *,
    encounter_id: int,
    status: str | None = None,
    round: int | None = None,
    active_idx: int | None = None,
) -> None:
    q = await s.execute(select(models.Encounter).where(models.Encounter.id == encounter_id))
    enc = q.scalar_one_or_none()
    if not enc:
        return
    if status is not None:
        try:
            enc.status = models.EncounterStatus(status)
        except Exception:
            enc.status = models.EncounterStatus.setup
    if round is not None:
        enc.round = int(round)
    if active_idx is not None:
        enc.active_idx = int(active_idx)
    await _flush_retry(s)


async def add_combatant(
    s: AsyncSession,
    *,
    encounter_id: int,
    name: str,
    character_id: int | None = None,
    hp: int = 0,
    token_id: str | None = None,
) -> models.Combatant:
    # Determine next order_idx for stability
    q = await s.execute(
        select(models.Combatant).where(models.Combatant.encounter_id == encounter_id)
    )
    existing = list(q.scalars().all())
    next_idx = (max([c.order_idx for c in existing], default=-1) + 1) if existing else 0
    cb = models.Combatant(
        encounter_id=encounter_id,
        character_id=character_id,
        name=name,
        initiative=None,
        hp=hp,
        conditions={},
        token_id=token_id,
        order_idx=next_idx,
    )
    s.add(cb)
    await _flush_retry(s)
    return cb


async def set_combatant_initiative(s: AsyncSession, *, combatant_id: int, initiative: int) -> None:
    q = await s.execute(select(models.Combatant).where(models.Combatant.id == combatant_id))
    cb = q.scalar_one_or_none()
    if not cb:
        return
    cb.initiative = int(initiative)
    await _flush_retry(s)


async def list_combatants(s: AsyncSession, *, encounter_id: int) -> list[models.Combatant]:
    q = await s.execute(
        select(models.Combatant).where(models.Combatant.encounter_id == encounter_id)
    )
    return list(q.scalars().all())


def sort_initiative_order(combatants: list[models.Combatant]) -> list[models.Combatant]:
    # initiative desc (None last), then order_idx asc for stability
    def _key(c: models.Combatant):
        init = c.initiative
        init_sort = -init if isinstance(init, int) else float("inf")
        return (init_sort, c.order_idx)

    cbs = [c for c in combatants]
    cbs.sort(key=_key)
    return cbs


# -----------------------------
# Pending Actions (Phase 8)
# -----------------------------


async def create_pending_action(
    s: AsyncSession,
    *,
    campaign_id: int,
    scene_id: int,
    channel_id: int,
    user_id: str,
    request_id: str,
    chain: dict,
    mechanics: str,
    narration: str,
    player_tx_id: int | None,
    bot_tx_id: int | None,
    activity_log_id: int | None = None,
    ttl_seconds: int | None = 300,
) -> models.PendingAction:
    expires_at = None
    if ttl_seconds and ttl_seconds > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    # Compute a normalized dedup hash from the chain JSON
    try:
        normalized = json.dumps(chain, sort_keys=True, separators=(",", ":"))
        dedup_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    except Exception:
        dedup_hash = None
    # Idempotency: if a pending with same (scene_id, user_id, dedup_hash)
    # exists, return it
    if dedup_hash:
        stmt = (
            select(models.PendingAction)
            .where(
                models.PendingAction.scene_id == scene_id,
                models.PendingAction.user_id == user_id,
                models.PendingAction.dedup_hash == dedup_hash,
                models.PendingAction.status == "pending",
            )
            .order_by(models.PendingAction.created_at.desc())
            .limit(1)
        )
        q = await s.execute(stmt)
        existing = q.scalar_one_or_none()
        if existing:
            inc_counter("pending.create.duplicate")
            inc_counter("pending.created")
            return existing
    pa = models.PendingAction(
        campaign_id=campaign_id,
        scene_id=scene_id,
        channel_id=channel_id,
        user_id=user_id,
        request_id=request_id,
        chain=chain,
        mechanics=mechanics,
        narration=narration,
        player_tx_id=player_tx_id,
        bot_tx_id=bot_tx_id,
        activity_log_id=activity_log_id,
        status="pending",
        expires_at=expires_at,
        dedup_hash=dedup_hash,
    )
    s.add(pa)
    retry_for_fk = False
    try:
        # Diagnostic: verify parent FK rows exist before first flush
        try:
            # Suppress autoflush while verifying parents; we don't want pending_actions
            # flushed implicitly due to these selects.
            with s.no_autoflush:
                camp_exists = await s.execute(
                    select(models.Campaign.id).where(models.Campaign.id == campaign_id)
                )
                scene_exists = await s.execute(
                    select(models.Scene.id).where(models.Scene.id == scene_id)
                )
                act_exists = None
                if activity_log_id is not None:
                    act_exists = await s.execute(
                        select(models.ActivityLog.id).where(
                            models.ActivityLog.id == activity_log_id
                        )
                    )
                    if not act_exists.scalar_one_or_none():
                        # Activity log not found (possibly created in another uncommitted session);
                        # drop reference to avoid FK failure.
                        pa.activity_log_id = None
                        activity_log_id = None
            structlog.get_logger("pending").debug(
                "pending.pre_flush.fk_check",
                campaign_id=campaign_id,
                scene_id=scene_id,
                activity_log_id=activity_log_id,
                campaign_present=bool(camp_exists.scalar_one_or_none()),
                scene_present=bool(scene_exists.scalar_one_or_none()),
                activity_present=(
                    bool(act_exists.scalar_one_or_none()) if act_exists is not None else None
                ),
            )
        except Exception:
            structlog.get_logger("pending").warning(
                "pending.pre_flush.fk_check_failed", exc_info=True
            )
        await _flush_retry(s)
    except IntegrityError as e:
        msg = str(e).lower()
        await s.rollback()
        # Unique dedup path
        if dedup_hash and "unique" in msg:
            q = await s.execute(
                select(models.PendingAction)
                .where(
                    models.PendingAction.scene_id == scene_id,
                    models.PendingAction.user_id == user_id,
                    models.PendingAction.dedup_hash == dedup_hash,
                    models.PendingAction.status == "pending",
                )
                .order_by(models.PendingAction.created_at.desc())
                .limit(1)
            )
            existing = q.scalar_one_or_none()
            if existing:
                inc_counter("pending.create.duplicate")
                inc_counter("pending.created")
                return existing
        # Foreign key anomaly retry (observed intermittently in test suite)
        if "foreign key" in msg and not retry_for_fk:
            retry_for_fk = True
            # Re-verify parent rows exist before retry
            with s.no_autoflush:
                camp_exists = await s.execute(
                    select(models.Campaign.id).where(models.Campaign.id == campaign_id)
                )
                scene_exists = await s.execute(
                    select(models.Scene.id).where(models.Scene.id == scene_id)
                )
            if camp_exists.scalar_one_or_none() and scene_exists.scalar_one_or_none():
                # Re-add (state cleared after rollback) and retry once
                s.add(pa)
                try:
                    await _flush_retry(s)
                except IntegrityError:
                    raise
            else:
                # Build object but delay flush to control ordering & autoflush side-effects
                pa_kwargs = dict(
                    campaign_id=campaign_id,
                    scene_id=scene_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    request_id=request_id,
                    chain=chain,
                    mechanics=mechanics,
                    narration=narration,
                    player_tx_id=player_tx_id,
                    bot_tx_id=bot_tx_id,
                    activity_log_id=activity_log_id,
                    status="pending",
                    expires_at=expires_at,
                    dedup_hash=dedup_hash,
                )

                # Optional lightweight parent presence check in no_autoflush scope
                try:
                    with s.no_autoflush:
                        camp_ok = await s.get(models.Campaign, campaign_id) is not None
                        scene_ok = await s.get(models.Scene, scene_id) is not None
                        if not (camp_ok and scene_ok):  # parent truly missing: fast-fail
                            raise IntegrityError("parent missing", params=None, orig=None)  # type: ignore[arg-type]
                except IntegrityError:
                    raise
                except Exception:
                    # Non-fatal: proceed (diagnostics could be added here if desired)
                    pass

                def _new_pa():
                    return models.PendingAction(**pa_kwargs)

                pa = _new_pa()
                s.add(pa)
                try:
                    await _flush_retry(s)
                except IntegrityError as e:
                    msg = str(e).lower()
                    await s.rollback()
                    # Handle unique (dedup) race: fetch existing and return
                    if dedup_hash and "unique" in msg:
                        q = await s.execute(
                            select(models.PendingAction)
                            .where(
                                models.PendingAction.scene_id == scene_id,
                                models.PendingAction.user_id == user_id,
                                models.PendingAction.dedup_hash == dedup_hash,
                                models.PendingAction.status == "pending",
                            )
                            .order_by(models.PendingAction.created_at.desc())
                            .limit(1)
                        )
                        existing = q.scalar_one_or_none()
                        if existing:
                            inc_counter("pending.create.duplicate")
                            inc_counter("pending.created")
                            return existing
                    # Retry once on FK anomaly if parents still present
                    if "foreign key" in msg:
                        with s.no_autoflush:
                            camp_ok = await s.get(models.Campaign, campaign_id) is not None
                            scene_ok = await s.get(models.Scene, scene_id) is not None
                            act_ok = (
                                activity_log_id is None
                                or await s.get(models.ActivityLog, activity_log_id) is not None
                            )
                        if camp_ok and scene_ok and act_ok:
                            pa = _new_pa()
                            s.add(pa)
                            await _flush_retry(s)
                        else:
                            raise
                    else:
                        raise
                inc_counter("pending.create")
                inc_counter("pending.created")
                return pa
        # If we reach here the FK retry path did not succeed; re-raise
        raise
    # Success fallthrough
    inc_counter("pending.create")
    inc_counter("pending.created")
    return pa


async def append_event(
    s: AsyncSession,
    *,
    scene_id: int,
    actor_id: str | int | None,
    type: str,
    payload: dict[str, Any] | None,
    request_id: str | None = None,
) -> models.Event:
    # Global lock to avoid overlapping flush() on a shared AsyncSession in highly
    # concurrent append scenarios (test_event_concurrency_race). This preserves
    # deterministic ordinal sequencing while allowing callers to fire tasks.
    # Narrow scope: only guards the flush critical section.
    global _EVENT_APPEND_LOCK
    if "_EVENT_APPEND_LOCK" not in globals():  # lazy init to avoid import cycles
        _EVENT_APPEND_LOCK = asyncio.Lock()  # type: ignore
    # Normalize actor id (character name when numeric id maps to character)
    scene = await s.get(models.Scene, scene_id)
    if scene is None:
        raise ValueError(f"Scene {scene_id} does not exist")
    campaign_id = scene.campaign_id
    actor_norm = await normalize_actor_ref(
        s,
        campaign_id=campaign_id,
        ident=actor_id,
    )
    if actor_norm is None and actor_id is not None:
        actor_norm = str(actor_id)
    payload_dict = payload or {}
    async with _EVENT_APPEND_LOCK:  # type: ignore
        # Determine ordinal & linkage inside lock to prevent race producing gaps
        last_event = await s.execute(
            select(models.Event)
            .where(models.Event.campaign_id == campaign_id)
            .order_by(models.Event.replay_ordinal.desc())
            .limit(1)
        )
        last_event_row = last_event.scalar_one_or_none()
        if last_event_row is None:
            replay_ordinal = 0
            prev_hash = event_envelope.GENESIS_PREV_EVENT_HASH
        else:
            replay_ordinal = last_event_row.replay_ordinal + 1
            prev_hash = bytes(last_event_row.payload_hash)
        execution_request_id = request_id or (
            f"evt-{scene_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        payload_hash = event_envelope.compute_payload_hash(payload_dict)
        idempotency_key = event_envelope.compute_idempotency_key(
            campaign_id=campaign_id,
            event_type=type,
            execution_request_id=execution_request_id,
            plan_id=None,
            payload=payload_dict,
            replay_ordinal=replay_ordinal,
        )
        ev = models.Event(
            campaign_id=campaign_id,
            scene_id=scene_id,
            replay_ordinal=replay_ordinal,
            actor_id=actor_norm,
            type=type,
            event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
            world_time=replay_ordinal,
            prev_event_hash=prev_hash,
            payload_hash=payload_hash,
            idempotency_key=idempotency_key,
            plan_id=None,
            execution_request_id=execution_request_id,
            approved_by=None,
            payload=payload_dict,
            migrator_applied_from=None,
        )
        s.add(ev)
        await _flush_retry(s)
    inc_counter("events.append.ok")  # legacy naming kept
    inc_counter("events.applied")  # HR-004 new canonical counter
    # Structured log for observability (HR-003): include identifiers & hash prefixes
    try:  # Best-effort: logging must not break persistence path
        from Adventorator.action_validation.logging_utils import (
            log_event as _log_event,
        )  # lazy import

        _log_event(
            "events",
            "appended",
            campaign_id=campaign_id,
            scene_id=scene_id,
            event_id=getattr(ev, "id", None),
            replay_ordinal=replay_ordinal,
            type=type,
            request_id=execution_request_id,
            payload_hash=payload_hash.hex()[:16],
            idempo_key=idempotency_key.hex()[:16],
        )
    except Exception:
        pass
    return ev


# -----------------------------
# Pending Actions Helper Queries
# -----------------------------


async def get_latest_pending_for_user(
    s: AsyncSession, *, scene_id: int, user_id: str
) -> models.PendingAction | None:
    stmt = (
        select(models.PendingAction)
        .where(
            models.PendingAction.scene_id == scene_id,
            models.PendingAction.user_id == user_id,
            models.PendingAction.status == "pending",
        )
        .order_by(models.PendingAction.created_at.desc())
        .limit(1)
    )
    q = await s.execute(stmt)
    return q.scalar_one_or_none()


async def confirm_pending_action(
    s: AsyncSession, *, pending_action_id: int, bot_tx_id: int | None
) -> models.PendingAction | None:
    q = await s.execute(
        select(models.PendingAction).where(models.PendingAction.id == pending_action_id)
    )
    pa = q.scalar_one_or_none()
    if not pa:
        return None
    if pa.status != "pending":
        return pa
    pa.status = "confirmed"
    if bot_tx_id is not None:
        pa.bot_tx_id = bot_tx_id
    # Optional attribute present in newer migration; guard for older instances
    if hasattr(pa, "confirmed_at"):
        pa.confirmed_at = datetime.now(timezone.utc)
    await _flush_retry(s)
    inc_counter("pending.confirmed")
    return pa


async def cancel_pending_action(
    s: AsyncSession, *, pending_action_id: int
) -> models.PendingAction | None:
    q = await s.execute(
        select(models.PendingAction).where(models.PendingAction.id == pending_action_id)
    )
    pa = q.scalar_one_or_none()
    if not pa:
        return None
    if pa.status != "pending":
        return pa
    pa.status = "cancelled"
    if hasattr(pa, "cancelled_at"):
        pa.cancelled_at = datetime.now(timezone.utc)
    await _flush_retry(s)
    inc_counter("pending.cancelled")
    return pa


async def mark_pending_action_status(
    s: AsyncSession, pending_action_id: int, status: str
) -> models.PendingAction | None:
    q = await s.execute(
        select(models.PendingAction).where(models.PendingAction.id == pending_action_id)
    )
    pa = q.scalar_one_or_none()
    if not pa:
        return None
    # Normalize legacy/caller variants
    normalized = status.lower().strip()
    if normalized == "canceled":  # normalize American spelling used inconsistently
        normalized = "cancelled"
    valid = {"pending", "confirmed", "cancelled", "error"}
    if normalized not in valid:
        normalized = "error"
    pa.status = normalized
    if normalized == "confirmed" and hasattr(pa, "confirmed_at"):
        pa.confirmed_at = datetime.now(timezone.utc)
    elif normalized == "cancelled" and hasattr(pa, "cancelled_at"):
        pa.cancelled_at = datetime.now(timezone.utc)
    await _flush_retry(s)
    return pa


async def expire_stale_pending_actions(s: AsyncSession) -> int:
    """Mark pending actions whose expires_at is in the past as expired.

    Returns number marked. Uses a lightweight select then per-row update to
    keep SQLAlchemy state consistent (rather than bulk UPDATE which would bypass ORM).
    """
    now = datetime.now(timezone.utc)
    q = await s.execute(
        select(models.PendingAction).where(
            models.PendingAction.status == "pending",
            models.PendingAction.expires_at.is_not(None),
            models.PendingAction.expires_at < now,
        )
    )
    rows = list(q.scalars().all())
    count = 0
    for pa in rows:
        pa.status = "expired"
        count += 1
    if count:
        await _flush_retry(s)
    return count


async def list_events(
    s: AsyncSession, *, scene_id: int, since_id: int | None = None, limit: int = 500
) -> list[models.Event]:
    stmt = select(models.Event).where(models.Event.scene_id == scene_id)
    if since_id is not None:
        stmt = stmt.where(models.Event.id > since_id)
    stmt = stmt.order_by(models.Event.id.asc()).limit(limit)
    q = await s.execute(stmt)
    return list(q.scalars().all())


def fold_hp_view(events: list[models.Event]) -> dict[str, int]:
    """Very small example fold: derive HP deltas per actor.

    Convention: event.type == "apply_damage" with payload {"target": actor_id, "amount": int}
    returns a dict of actor_id -> net HP change (negative numbers for damage).
    """
    hp: dict[str, int] = {}
    for ev in events:
        if ev.type == "apply_damage":
            target = str(ev.payload.get("target"))
            amt = int(ev.payload.get("amount", 0))
            if target:
                hp[target] = hp.get(target, 0) - amt
        elif ev.type == "heal":
            target = str(ev.payload.get("target"))
            amt = int(ev.payload.get("amount", 0))
            if target:
                hp[target] = hp.get(target, 0) + amt
    return hp


def fold_conditions_view(events: list[models.Event]) -> dict[str, dict[str, dict[str, int | None]]]:
    """Fold conditions per target: {target: {condition: {"stacks": int, "duration": int|None}}}.

    Supported events:
    - condition.applied {target, condition, duration?}
    - condition.removed {target, condition}
    - heal/apply_damage do not affect conditions.
    Duration semantics are simple:
    last write wins; stacks increment on applied,
    decrement on removed.
    """
    out: dict[str, dict[str, dict[str, int | None]]] = {}
    for ev in events:
        et = ev.type
        if et == "condition.applied":
            target = str(ev.payload.get("target"))
            cond = str(ev.payload.get("condition"))
            dur = ev.payload.get("duration")
            try:
                dur_i = int(dur) if dur is not None else None
            except Exception:
                dur_i = None
            if not target or not cond:
                continue
            tgt = out.setdefault(target, {})
            slot = tgt.setdefault(cond, {"stacks": 0, "duration": None})
            prev = slot.get("stacks")
            prev_int = prev if isinstance(prev, int) else 0
            slot["stacks"] = prev_int + 1
            slot["duration"] = dur_i if dur_i is not None else slot.get("duration", None)
        elif et == "condition.removed":
            target = str(ev.payload.get("target"))
            cond = str(ev.payload.get("condition"))
            if not target or not cond:
                continue
            tgt = out.setdefault(target, {})
            slot = tgt.setdefault(cond, {"stacks": 0, "duration": None})
            prev = slot.get("stacks")
            prev_int = prev if isinstance(prev, int) else 0
            slot["stacks"] = max(0, prev_int - 1)
            # Do not change duration on removal; stacks reaching 0 indicates inactive
        elif et == "condition.cleared":
            target = str(ev.payload.get("target"))
            cond = str(ev.payload.get("condition"))
            if not target or not cond:
                continue
            tgt = out.setdefault(target, {})
            slot = tgt.setdefault(cond, {"stacks": 0, "duration": None})
            slot["stacks"] = 0
            slot["duration"] = None
    return out


def fold_initiative_view(events: list[models.Event]) -> list[tuple[str, int]]:
    """Fold a simple initiative order from events.

    Supported events:
    - initiative.set {order: [{"id": str, "init": int}, ...]}
    - initiative.update {id, init}
    - initiative.remove {id}
    Returns a stable sorted list by descending init then id.
    """
    order: dict[str, int] = {}
    for ev in events:
        if ev.type == "initiative.set":
            try:
                arr = ev.payload.get("order") or []
                if isinstance(arr, list):
                    order.clear()
                    for ent in arr:
                        cid = str((ent or {}).get("id", ""))
                        raw_init = (ent or {}).get("init", 0)
                        if isinstance(raw_init, int):
                            init = raw_init
                        elif isinstance(raw_init, str):
                            try:
                                init = int(raw_init)
                            except Exception:
                                init = 0
                        else:
                            init = 0
                        if cid:
                            order[cid] = init
            except Exception:
                continue
        elif ev.type == "initiative.update":
            cid = str(ev.payload.get("id", ""))
            if cid:
                raw_init2 = ev.payload.get("init", 0)
                if isinstance(raw_init2, int):
                    order[cid] = raw_init2
                elif isinstance(raw_init2, str):
                    try:
                        order[cid] = int(raw_init2)
                    except Exception:
                        order[cid] = 0
                else:
                    order[cid] = 0
        elif ev.type == "initiative.remove":
            cid = str(ev.payload.get("id", ""))
            if cid and cid in order:
                try:
                    del order[cid]
                except KeyError:
                    pass
    # sort by descending init then id for stability
    return sorted(order.items(), key=lambda kv: (-kv[1], kv[0]))
