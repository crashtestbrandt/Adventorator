# repos.py

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import models
from Adventorator.metrics import inc_counter
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


async def healthcheck(s: AsyncSession) -> None:
    """Lightweight DB check to confirm connectivity and basic query works."""
    await s.execute(select(models.Campaign).limit(1))


# -----------------------------
# Encounters & Combatants (Phase 10)
# -----------------------------


async def create_encounter(s: AsyncSession, *, scene_id: int) -> models.Encounter:
    enc = models.Encounter(scene_id=scene_id)
    s.add(enc)
    await _flush_retry(s)
    return enc


async def get_encounter_by_id(s: AsyncSession, *, encounter_id: int) -> models.Encounter | None:
    q = await s.execute(
        select(models.Encounter).where(models.Encounter.id == encounter_id)
    )
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


async def set_combatant_initiative(
    s: AsyncSession, *, combatant_id: int, initiative: int
) -> None:
    q = await s.execute(select(models.Combatant).where(models.Combatant.id == combatant_id))
    cb = q.scalar_one_or_none()
    if not cb:
        return
    cb.initiative = int(initiative)
    await _flush_retry(s)


async def list_combatants(
    s: AsyncSession, *, encounter_id: int
) -> list[models.Combatant]:
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
        status="pending",
        expires_at=expires_at,
        dedup_hash=dedup_hash,
    )
    s.add(pa)
    try:
        await _flush_retry(s)
    except IntegrityError:
        # Likely unique (scene_id, user_id, dedup_hash) conflict; fetch existing
        await s.rollback()
        if dedup_hash:
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
        # If no dedup hash or not found, re-raise
        raise
    inc_counter("pending.create")
    inc_counter("pending.created")
    return pa


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
    pa = q.scalar_one_or_none()
    if pa is not None:
        inc_counter("pending.fetch.latest")
    return pa


async def mark_pending_action_status(
    s: AsyncSession, pending_id: int, status: str
) -> None:
    q = await s.execute(
        select(models.PendingAction).where(models.PendingAction.id == pending_id)
    )
    pa = q.scalar_one_or_none()
    if pa:
        pa.status = status
        await _flush_retry(s)
    inc_counter(f"pending.status.{status}")
    # Aliases for plan parity
    if status == "confirmed":
        inc_counter("pending.confirmed")
    if status == "canceled":
        inc_counter("pending.canceled")


async def expire_stale_pending_actions(s: AsyncSession) -> int:
    """Mark expired pending actions as 'expired'. Returns count marked.

    This is a best-effort helper; a periodic task/CLI can call it.
    """
    from datetime import datetime, timezone
    # SQLite lacks server-side now(); do expiration in Python on fetched rows
    stmt = select(models.PendingAction).where(
        models.PendingAction.status == "pending"
    )
    q = await s.execute(stmt)
    count = 0
    now = datetime.now(timezone.utc)
    for pa in q.scalars().all():
        if pa.expires_at is not None and pa.expires_at <= now:
            pa.status = "expired"
            count += 1
    if count:
        await _flush_retry(s)
        inc_counter("pending.expired", count)
    return count


# -----------------------------
# Events (Phase 9)
# -----------------------------


async def append_event(
    s: AsyncSession,
    *,
    scene_id: int,
    actor_id: str | None,
    type: str,
    payload: dict,
    request_id: str | None = None,
) -> models.Event:
    """Append an event to the ledger. Always insert-only.

    Emits metrics events.append.ok/error and returns the created Event.
    """
    # Normalize actor reference to a display string (prefer character name when possible)
    actor_norm: str | None = actor_id
    try:
        # Resolve campaign_id from scene for normalization context
        q = await s.execute(select(models.Scene).where(models.Scene.id == scene_id))
        sc = q.scalar_one_or_none()
        if sc is not None and getattr(sc, "campaign_id", None) is not None:
            actor_norm = await normalize_actor_ref(
                s, campaign_id=int(sc.campaign_id), ident=actor_id
            )
    except Exception:
        # Best-effort only; fall back to provided actor_id on any error
        actor_norm = actor_id

    ev = models.Event(
        scene_id=scene_id,
        actor_id=actor_norm,
        type=type,
        payload=payload,
        request_id=request_id,
    )
    s.add(ev)
    await _flush_retry(s)
    inc_counter("events.append.ok")
    return ev


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
