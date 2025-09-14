from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from Adventorator import repos
from Adventorator.config import load_settings
from Adventorator.db import session_scope
from Adventorator.metrics import inc_counter, observe_histogram
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG
from Adventorator.services import encounter_service
from Adventorator.tool_registry import InMemoryToolRegistry, ToolSpec

log = structlog.get_logger()


@dataclass(frozen=True)
class ToolStep:
    tool: str
    args: dict[str, Any]
    requires_confirmation: bool = False
    visibility: str = "ephemeral"  # "ephemeral" | "public"


@dataclass(frozen=True)
class ToolCallChain:
    request_id: str
    scene_id: int
    steps: list[ToolStep]
    # Optional actor context (e.g., character id or user id) for event emission
    actor_id: str | None = None


@dataclass(frozen=True)
class PreviewItem:
    tool: str
    mechanics: str
    # Optional predicted events (domain-specific) produced by the handler during preview
    # Shape: [{"type": str, "payload": dict}]
    predicted_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Preview:
    items: list[PreviewItem]


class Executor:
    def __init__(self) -> None:
        self.registry = InMemoryToolRegistry()
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        # roll: just echo dice mechanics using DiceRNG
        def roll_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            expr = str(args.get("expr", "1d20"))
            rng = DiceRNG(seed=args.get("seed"))
            res = rng.roll(expr)
            return {"mechanics": f"Roll {expr} -> {res.total} ({res.rolls})"}

        self.registry.register(
            ToolSpec(
                name="roll",
                schema={"type": "object", "properties": {"expr": {"type": "string"}}},
                handler=roll_handler,
            )
        )

        # check: ability check preview
        def check_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            # Minimal inputs; sheet context not wired here yet
            ability = str(args.get("ability", "DEX"))
            score = int(args.get("score", 10))
            dc = int(args.get("dc", 10))
            prof = bool(args.get("proficient", False))
            expertise = bool(args.get("expertise", False))
            prof_bonus = int(args.get("prof_bonus", 2))
            rng = DiceRNG(seed=args.get("seed"))
            d20 = [rng.roll("1d20").rolls[0]]
            r = compute_check(
                CheckInput(
                    ability=ability,
                    score=score,
                    proficient=prof,
                    expertise=expertise,
                    proficiency_bonus=prof_bonus,
                    dc=dc,
                    advantage=False,
                    disadvantage=False,
                ),
                d20_rolls=d20,
            )
            if len(r.d20) == 3:
                d20_str = f"d20: {r.d20[0]}/{r.d20[1]} -> {r.pick}"
            else:
                d20_str = f"d20: {r.d20[0]}"
            outcome = "SUCCESS" if r.success else "FAIL"
            mech_prefix = f"Check: {ability} vs DC {dc}\n"
            mech_details = f"{d20_str} | mod: {r.mod:+d} | total: {r.total} -> {outcome}"
            mech = mech_prefix + mech_details
            return {"mechanics": mech}

        self.registry.register(
            ToolSpec(
                name="check",
                schema={
                    "type": "object",
                    "properties": {
                        "ability": {"type": "string"},
                        "score": {"type": "integer"},
                        "dc": {"type": "integer"},
                    },
                },
                handler=check_handler,
            )
        )

        # apply_damage: stub mutating tool that produces a domain event
        def apply_damage_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            target = str(args.get("target", ""))
            amount = int(args.get("amount", 0))
            mech = f"Apply {amount} damage to {target}"
            return {
                "mechanics": mech,
                "events": [
                    {"type": "apply_damage", "payload": {"target": target, "amount": amount}}
                ],
            }

        self.registry.register(
            ToolSpec(
                name="apply_damage",
                schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "amount": {"type": "integer"},
                    },
                    "required": ["target", "amount"],
                },
                handler=apply_damage_handler,
            )
        )

        # heal: mutating tool to restore HP; emits a domain event
        def heal_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            target = str(args.get("target", ""))
            amount = int(args.get("amount", 0))
            mech = f"Heal {amount} HP on {target}"
            return {
                "mechanics": mech,
                "events": [
                    {"type": "heal", "payload": {"target": target, "amount": amount}}
                ],
            }

        self.registry.register(
            ToolSpec(
                name="heal",
                schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "amount": {"type": "integer"},
                    },
                    "required": ["target", "amount"],
                },
                handler=heal_handler,
            )
        )

        # apply_condition: mutating tool to apply a named condition
        def apply_condition_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            target = str(args.get("target", ""))
            condition = str(args.get("condition", ""))
            duration = args.get("duration")
            # Duration may be None or int number of rounds
            try:
                dur_val = int(duration) if duration is not None else None
            except Exception:
                dur_val = None
            mech = f"Apply condition '{condition}' to {target}"
            payload: dict[str, Any] = {"target": target, "condition": condition}
            if dur_val is not None:
                payload["duration"] = dur_val
            return {
                "mechanics": mech,
                "events": [
                    {"type": "condition.applied", "payload": payload},
                ],
            }

        self.registry.register(
            ToolSpec(
                name="apply_condition",
                schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "condition": {"type": "string"},
                        "duration": {"type": "integer"},
                    },
                    "required": ["target", "condition"],
                },
                handler=apply_condition_handler,
            )
        )

        # remove_condition: decrement condition stacks
        def remove_condition_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            target = str(args.get("target", ""))
            condition = str(args.get("condition", ""))
            mech = f"Remove one stack of '{condition}' from {target}"
            return {
                "mechanics": mech,
                "events": [
                    {
                        "type": "condition.removed",
                        "payload": {"target": target, "condition": condition},
                    }
                ],
            }

        self.registry.register(
            ToolSpec(
                name="remove_condition",
                schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "condition": {"type": "string"},
                    },
                    "required": ["target", "condition"],
                },
                handler=remove_condition_handler,
            )
        )

        # clear_condition: zero stacks and clear duration
        def clear_condition_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            target = str(args.get("target", ""))
            condition = str(args.get("condition", ""))
            mech = f"Clear condition '{condition}' from {target}"
            return {
                "mechanics": mech,
                "events": [
                    {
                        "type": "condition.cleared",
                        "payload": {"target": target, "condition": condition},
                    }
                ],
            }

        self.registry.register(
            ToolSpec(
                name="clear_condition",
                schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "condition": {"type": "string"},
                    },
                    "required": ["target", "condition"],
                },
                handler=clear_condition_handler,
            )
        )

        # --- Encounter & Turn Engine tools (Phase 10) ---
        # Guarded by features.combat; handlers return helpful stub when disabled.
        def _combat_guard() -> bool:
            try:
                return bool(load_settings().features_combat)
            except Exception:
                return False

        async def _with_session(handler):
            async with session_scope() as s:
                return await handler(s)

        def start_encounter_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            if not _combat_guard():
                return {"mechanics": "Combat features disabled (features.combat=false)"}
            scene_id = int(args.get("scene_id", 0))
            return {"mechanics": f"Start encounter (scene_id={scene_id})"}

        self.registry.register(
            ToolSpec(
                name="start_encounter",
                schema={
                    "type": "object",
                    "properties": {"scene_id": {"type": "integer"}},
                    "required": ["scene_id"],
                },
                handler=start_encounter_handler,
            )
        )

        def add_combatant_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            if not _combat_guard():
                return {"mechanics": "Combat features disabled (features.combat=false)"}
            encounter_id = int(args.get("encounter_id", 0))
            name = str(args.get("name", ""))
            hp = int(args.get("hp", 0))
            return {"mechanics": f"Add combatant '{name}' (encounter_id={encounter_id}, hp={hp})"}

        self.registry.register(
            ToolSpec(
                name="add_combatant",
                schema={
                    "type": "object",
                    "properties": {
                        "encounter_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "character_id": {"type": "integer"},
                        "hp": {"type": "integer"},
                        "token_id": {"type": "string"},
                    },
                    "required": ["encounter_id", "name"],
                },
                handler=add_combatant_handler,
            )
        )

        def set_initiative_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            if not _combat_guard():
                return {"mechanics": "Combat features disabled (features.combat=false)"}
            encounter_id = int(args.get("encounter_id", 0))
            combatant_id = int(args.get("combatant_id", 0))
            initiative = int(args.get("initiative", 0))
            mech = (
                f"Set initiative {initiative} "
                f"(encounter_id={encounter_id}, combatant_id={combatant_id})"
            )
            return {"mechanics": mech}

        self.registry.register(
            ToolSpec(
                name="set_initiative",
                schema={
                    "type": "object",
                    "properties": {
                        "encounter_id": {"type": "integer"},
                        "combatant_id": {"type": "integer"},
                        "initiative": {"type": "integer"},
                    },
                    "required": ["encounter_id", "combatant_id", "initiative"],
                },
                handler=set_initiative_handler,
            )
        )

        def next_turn_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            if not _combat_guard():
                return {"mechanics": "Combat features disabled (features.combat=false)"}
            encounter_id = int(args.get("encounter_id", 0))
            return {"mechanics": f"Advance to next turn (encounter_id={encounter_id})"}

        self.registry.register(
            ToolSpec(
                name="next_turn",
                schema={
                    "type": "object",
                    "properties": {"encounter_id": {"type": "integer"}},
                    "required": ["encounter_id"],
                },
                handler=next_turn_handler,
            )
        )

        def end_encounter_handler(args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
            if not _combat_guard():
                return {"mechanics": "Combat features disabled (features.combat=false)"}
            encounter_id = int(args.get("encounter_id", 0))
            return {"mechanics": f"End encounter (encounter_id={encounter_id})"}

        self.registry.register(
            ToolSpec(
                name="end_encounter",
                schema={
                    "type": "object",
                    "properties": {"encounter_id": {"type": "integer"}},
                    "required": ["encounter_id"],
                },
                handler=end_encounter_handler,
            )
        )

    async def execute_chain(self, chain: ToolCallChain, dry_run: bool = True) -> Preview:
        start = time.monotonic()
        items: list[PreviewItem] = []
        for step in chain.steps:
            spec = self.registry.get(step.tool)
            if not spec:
                log.warning("executor.unknown_tool", tool=step.tool)
                items.append(PreviewItem(tool=step.tool, mechanics=f"Unknown tool: {step.tool}"))
                continue
            out = spec.handler(step.args, dry_run)
            items.append(
                PreviewItem(
                    tool=step.tool,
                    mechanics=str(out.get("mechanics", "")),
                    predicted_events=list(out.get("events", []) or []),
                )
            )
        # Per-tool counters for preview
        for it in items:
            inc_counter(f"executor.preview.tool.{it.tool}")
        inc_counter("executor.preview.ok")
        try:
            dur_ms = int((time.monotonic() - start) * 1000)
            inc_counter("executor.preview.duration_ms", dur_ms)
            observe_histogram("executor.preview.ms", dur_ms)
        except Exception:
            pass
        return Preview(items=items)

    async def apply_chain(self, chain: ToolCallChain) -> Preview:
        """Phase 8+: Apply a chain. For now, identical to preview (no mutation).

    Phase 9 scaffolding: if features.events is enabled, append events:
    - Prefer any handler-provided predicted_events (domain-specific).
    - Otherwise append a generic executor.<tool> event with mechanics text.
        """
        start = time.monotonic()
        # Preview first for consistent mechanics strings
        res = await self.execute_chain(chain, dry_run=False)
        # Perform mutations for combat tools when enabled
        try:
            settings = load_settings()
            if getattr(settings, "features_combat", False):
                async with session_scope() as s:
                    for step, item in zip(chain.steps, res.items, strict=True):
                        name = step.tool
                        evs: list[dict[str, Any]] = []
                        if name == "start_encounter":
                            mech, evs = await encounter_service.start_encounter(
                                s, scene_id=int(step.args.get("scene_id", 0))
                            )
                            item.predicted_events.extend(evs)
                            inc_counter("executor.apply.tool.start_encounter")
                        elif name == "add_combatant":
                            # Narrow optional types before passing into service to satisfy mypy
                            _cid = step.args.get("character_id")
                            character_id = int(_cid) if _cid is not None else None
                            _tid = step.args.get("token_id")
                            token_id = str(_tid) if _tid is not None else None
                            mech, evs = await encounter_service.add_combatant(
                                s,
                                encounter_id=int(step.args.get("encounter_id", 0)),
                                name=str(step.args.get("name", "")),
                                character_id=character_id,
                                hp=int(step.args.get("hp", 0)),
                                token_id=token_id,
                            )
                            item.predicted_events.extend(evs)
                            inc_counter("executor.apply.tool.add_combatant")
                        elif name == "set_initiative":
                            mech, evs = await encounter_service.set_initiative(
                                s,
                                encounter_id=int(step.args.get("encounter_id", 0)),
                                combatant_id=int(step.args.get("combatant_id", 0)),
                                initiative=int(step.args.get("initiative", 0)),
                            )
                            item.predicted_events.extend(evs)
                            inc_counter("executor.apply.tool.set_initiative")
                        elif name == "next_turn":
                            mech, evs = await encounter_service.next_turn(
                                s, encounter_id=int(step.args.get("encounter_id", 0))
                            )
                            item.predicted_events.extend(evs)
                            inc_counter("executor.apply.tool.next_turn")
                        elif name == "end_encounter":
                            mech, evs = await encounter_service.end_encounter(
                                s, encounter_id=int(step.args.get("encounter_id", 0))
                            )
                            item.predicted_events.extend(evs)
                            inc_counter("executor.apply.tool.end_encounter")
        except Exception:
            # Do not fail apply on combat service errors in this phase
            pass
        try:
            settings = load_settings()
            if getattr(settings, "features_events", False):
                # Append generic events with preview mechanics per step
                async with session_scope() as s:
                    for item in res.items:
                        # Use predicted events if provided by the handler
                        evs = item.predicted_events or []
                        if evs:
                            for ev in evs:
                                try:
                                    await repos.append_event(
                                        s,
                                        scene_id=chain.scene_id,
                                        actor_id=chain.actor_id,
                                        type=str(ev.get("type", f"executor.{item.tool}")),
                                        payload=dict(ev.get("payload", {})),
                                        request_id=chain.request_id,
                                    )
                                except Exception:
                                    inc_counter("events.append.error")
                        else:
                            # Fallback to generic mechanics event
                            payload = {"mechanics": item.mechanics}
                            try:
                                await repos.append_event(
                                    s,
                                    scene_id=chain.scene_id,
                                    actor_id=chain.actor_id,
                                    type=f"executor.{item.tool}",
                                    payload=payload,
                                    request_id=chain.request_id,
                                )
                            except Exception:
                                inc_counter("events.append.error")
        except Exception:
            # Feature flag or ledger errors should not fail apply in Phase 8
            pass
        inc_counter("executor.apply.ok")
        try:
            dur_ms = int((time.monotonic() - start) * 1000)
            inc_counter("executor.apply.duration_ms", dur_ms)
            observe_histogram("executor.apply.ms", dur_ms)
        except Exception:
            pass
        return res
