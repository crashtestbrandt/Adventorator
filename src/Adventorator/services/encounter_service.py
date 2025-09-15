from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from Adventorator import repos
from Adventorator.metrics import inc_counter, observe_histogram
from Adventorator.models import EncounterStatus
from Adventorator.services.lock_service import acquire_encounter_locks

log = structlog.get_logger()


def _predict(ev_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": ev_type, "payload": payload}


async def start_encounter(
    s: AsyncSession, *, scene_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enc = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene_id)
    if enc:
        # Already exists; return idempotent response
        inc_counter("encounter.start.ok")
        return {"mechanics": f"Encounter already exists (id={enc.id})"}, [
            _predict("encounter.started", {"encounter_id": enc.id, "scene_id": scene_id})
        ]
    enc = await repos.create_encounter(s, scene_id=scene_id)
    mech = f"Encounter started (id={enc.id})"
    inc_counter("encounter.start.ok")
    return {"mechanics": mech}, [
        _predict("encounter.started", {"encounter_id": enc.id, "scene_id": scene_id})
    ]


async def add_combatant(
    s: AsyncSession,
    *,
    encounter_id: int,
    name: str,
    character_id: int | None = None,
    hp: int = 0,
    token_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enc = await repos.get_encounter_by_id(s, encounter_id=encounter_id)
    if not enc:
        inc_counter("encounter.add.error")
        return {"mechanics": "Encounter not found"}, []
    if enc.status != EncounterStatus.setup:
        inc_counter("encounter.add.error")
        return {"mechanics": "Cannot add combatants after encounter starts"}, []
    cb = await repos.add_combatant(
        s,
        encounter_id=encounter_id,
        name=name,
        character_id=character_id,
        hp=hp,
        token_id=token_id,
    )
    mech = f"Added {cb.name} (id={cb.id})"
    inc_counter("encounter.add.ok")
    return {"mechanics": mech}, [
        _predict(
            "combatant.added",
            {
                "encounter_id": encounter_id,
                "combatant_id": cb.id,
                "name": cb.name,
                "character_id": cb.character_id,
                "order_idx": cb.order_idx,
            },
        )
    ]


async def set_initiative(
    s: AsyncSession, *, encounter_id: int, combatant_id: int, initiative: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enc = await repos.get_encounter_by_id(s, encounter_id=encounter_id)
    if not enc:
        inc_counter("encounter.initiative_set.error")
        return {"mechanics": "Encounter not found"}, []
    if enc.status != EncounterStatus.setup:
        inc_counter("encounter.initiative_set.error")
        return {"mechanics": "Cannot set initiative after encounter starts"}, []
    await repos.set_combatant_initiative(s, combatant_id=combatant_id, initiative=int(initiative))
    mech = f"Initiative set for {combatant_id}: {initiative}"
    events = [
        _predict(
            "combatant.initiative_set",
            {
                "encounter_id": encounter_id,
                "combatant_id": combatant_id,
                "initiative": int(initiative),
            },
        )
    ]
    inc_counter("encounter.initiative_set.ok")
    # If all combatants now have initiative, mark active and set first turn
    cbs = await repos.list_combatants(s, encounter_id=encounter_id)
    if cbs and all(c.initiative is not None for c in cbs):
        ordered = repos.sort_initiative_order(cbs)
        await repos.update_encounter_state(
            s, encounter_id=encounter_id, status=EncounterStatus.active.value, round=1, active_idx=0
        )
        first = ordered[0]
        events.append(
            _predict(
                "encounter.advanced",
                {
                    "encounter_id": encounter_id,
                    "round": 1,
                    "active_idx": 0,
                    "active_combatant_id": first.id,
                },
            )
        )
        inc_counter("encounter.advanced")
    return {"mechanics": mech}, events


async def next_turn(
    s: AsyncSession, *, encounter_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _t0 = time.monotonic()
    enc = await repos.get_encounter_by_id(s, encounter_id=encounter_id)
    if not enc:
        inc_counter("encounter.next_turn.error")
        return {"mechanics": "Encounter not found"}, []
    if enc.status != EncounterStatus.active:
        inc_counter("encounter.next_turn.error")
        return {"mechanics": "Encounter is not active"}, []
    async with acquire_encounter_locks(s, encounter_id=encounter_id):
        # Reload inside lock to ensure fresh state
        enc2 = await repos.get_encounter_by_id(s, encounter_id=encounter_id)
        if not enc2 or enc2.status != EncounterStatus.active:
            inc_counter("encounter.next_turn.error")
            return {"mechanics": "Encounter not active"}, []
        cbs = await repos.list_combatants(s, encounter_id=encounter_id)
        ordered = repos.sort_initiative_order(cbs)
        if not ordered:
            inc_counter("encounter.next_turn.error")
            return {"mechanics": "No combatants"}, []
        n = len(ordered)
        new_idx = (enc2.active_idx + 1) % n
        new_round = enc2.round + 1 if new_idx == 0 else enc2.round
        await repos.update_encounter_state(
            s, encounter_id=encounter_id, active_idx=new_idx, round=new_round
        )
        active = ordered[new_idx]
        mech = f"Round {new_round}, Active: {active.name} (id={active.id})"
        inc_counter("encounter.next_turn.ok")
        try:
            dur_ms = int((time.monotonic() - _t0) * 1000)
            inc_counter("encounter.next_turn.duration_ms", dur_ms)
            observe_histogram("encounter.next_turn.ms", dur_ms)
        except Exception:
            pass
        return {"mechanics": mech}, [
            _predict(
                "encounter.advanced",
                {
                    "encounter_id": encounter_id,
                    "round": new_round,
                    "active_idx": new_idx,
                    "active_combatant_id": active.id,
                },
            )
        ]


async def end_encounter(
    s: AsyncSession, *, encounter_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enc = await repos.get_encounter_by_id(s, encounter_id=encounter_id)
    if not enc:
        inc_counter("encounter.end.error")
        return {"mechanics": "Encounter not found"}, []
    async with acquire_encounter_locks(s, encounter_id=encounter_id):
        await repos.update_encounter_state(
            s, encounter_id=encounter_id, status=EncounterStatus.ended.value
        )
    inc_counter("encounter.end.ok")
    return {"mechanics": "Encounter ended"}, [
        _predict("encounter.ended", {"encounter_id": encounter_id})
    ]
