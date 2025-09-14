from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

from Adventorator.metrics import inc_counter
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG
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


@dataclass(frozen=True)
class PreviewItem:
    tool: str
    mechanics: str


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
            items.append(PreviewItem(tool=step.tool, mechanics=str(out.get("mechanics", ""))))
        inc_counter("executor.preview.ok")
        try:
            dur_ms = int((time.monotonic() - start) * 1000)
            inc_counter("executor.preview.duration_ms", dur_ms)
        except Exception:
            pass
        return Preview(items=items)

    async def apply_chain(self, chain: ToolCallChain) -> Preview:
        """Phase 8+: Apply a chain. For now, identical to preview (no mutation)."""
        # Placeholder: in future, will emit events / mutate state in a single path
        start = time.monotonic()
        res = await self.execute_chain(chain, dry_run=False)
        inc_counter("executor.apply.ok")
        try:
            dur_ms = int((time.monotonic() - start) * 1000)
            inc_counter("executor.apply.duration_ms", dur_ms)
        except Exception:
            pass
        return res
