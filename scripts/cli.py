#!/usr/bin/env python3
"""
Interactive CLI harness to exercise Adventorator commands without Discord.

Supports:
- roll <expr> [--adv] [--dis]
- check --ability STR|DEX|... --score 10 --proficient 0|1 --expertise 0|1 --pb 2 --dc 15 [--adv] [--dis]
- narrate "your message here"  # runs LLM JSON flow + rules orchestrator
- history [N]                  # show recent transcripts for the default scene
- help / ? / quit / exit

Run with PYTHONPATH pointing at src, e.g.:
  PYTHONPATH=./src python3 scripts/cli_harness.py

It uses a default campaign/scene (guild_id=1, channel_id=1) to keep things simple.
"""
from __future__ import annotations

import asyncio
import shlex
import sys
from typing import Optional

from Adventorator.config import load_settings
from Adventorator.logging import setup_logging
from Adventorator.rules.dice import DiceRNG
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.db import session_scope
from Adventorator import repos
from Adventorator.llm import LLMClient
from Adventorator.orchestrator import run_orchestrator

DEFAULT_GUILD_ID = 1
DEFAULT_CHANNEL_ID = 1


def _print_help():
    print(
        """
Commands:
  roll <expr> [--adv] [--dis]
  check --ability <STR|DEX|CON|INT|WIS|CHA> --score <int> --proficient <0|1> --expertise <0|1> --pb <int> --dc <int> [--adv] [--dis]
  narrate "<message>"
  history [N]
  help | ?
  quit | exit
        """.strip()
    )


async def _ensure_default_scene():
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, DEFAULT_GUILD_ID, name="CLI")
        scene = await repos.ensure_scene(s, campaign.id, DEFAULT_CHANNEL_ID)
        return campaign, scene


def _parse_flags(parts: list[str]) -> tuple[bool, bool, list[str]]:
    adv = "--adv" in parts
    dis = "--dis" in parts
    rest = [p for p in parts if p not in ("--adv", "--dis")]
    return adv, dis, rest


def _to_bool(v: str) -> bool:
    return v.lower() in {"1", "true", "t", "yes", "y"}


def cmd_roll(parts: list[str], rng: DiceRNG):
    adv, dis, rest = _parse_flags(parts)
    expr = rest[0] if rest else "1d20"
    res = rng.roll(expr, advantage=adv, disadvantage=dis)
    tag = " (adv)" if adv else " (dis)" if dis else ""
    print(f"🎲 {expr} → rolls {res.rolls}{tag} = {res.total}")


def cmd_check(parts: list[str], rng: DiceRNG):
    # very small flag parser
    args = {k: None for k in ["--ability", "--score", "--proficient", "--expertise", "--pb", "--dc"]}
    adv = dis = False
    i = 0
    while i < len(parts):
        p = parts[i]
        if p in ("--adv", "--dis"):
            adv = adv or p == "--adv"
            dis = dis or p == "--dis"
            i += 1
            continue
        if p in args and i + 1 < len(parts):
            args[p] = parts[i + 1]
            i += 2
        else:
            i += 1

    ability = (args["--ability"] or "DEX").upper()
    score = int(args["--score"] or 10)
    prof = _to_bool(str(args["--proficient"] or "0"))
    exp = _to_bool(str(args["--expertise"] or "0"))
    pb = int(args["--pb"] or 2)
    dc = int(args["--dc"] or 15)

    res_roll = rng.roll("1d20", advantage=adv, disadvantage=dis)
    d20s = res_roll.rolls[:2] if len(res_roll.rolls) >= 2 else [res_roll.rolls[0]]
    ci = CheckInput(
        ability=ability,
        score=score,
        proficient=prof,
        expertise=exp,
        proficiency_bonus=pb,
        dc=dc,
        advantage=adv,
        disadvantage=dis,
    )
    out = compute_check(ci, d20_rolls=d20s)
    verdict = "✅ success" if out.success else "❌ fail"
    print(
        f"🧪 {ability} vs DC {dc}\n"
        f"• d20: {out.d20} → pick {out.pick}\n"
        f"• mod: {out.mod:+}\n"
        f"= {out.total} → {verdict}"
    )


async def cmd_narrate(message: str, llm: Optional[LLMClient]):
    if not llm:
        print("❌ LLM narrator is disabled. Enable [features].llm=true in config.toml.")
        return
    campaign, scene = await _ensure_default_scene()
    # Write player's message first so it's in context
    async with session_scope() as s:
        await repos.write_transcript(s, campaign.id, scene.id, DEFAULT_CHANNEL_ID, "player", message, "cli")
    res = await run_orchestrator(scene_id=scene.id, player_msg=message, llm_client=llm)
    if res.rejected:
        print(f"🛑 {res.reason or 'proposal rejected'}")
        return
    print("🧪 Mechanics\n" + res.mechanics)
    print("\n📖 Narration\n" + res.narration)
    # Log bot narration
    async with session_scope() as s:
        await repos.write_transcript(s, campaign.id, scene.id, DEFAULT_CHANNEL_ID, "bot", res.narration, "cli", meta={"mechanics": res.mechanics})


async def cmd_history(n: int = 10):
    _, scene = await _ensure_default_scene()
    async with session_scope() as s:
        txs = await repos.get_recent_transcripts(s, scene.id, limit=n)
    for t in txs:
        print(f"[{t.author}] {t.content}")


def main():
    setup_logging()
    settings = load_settings()
    rng = DiceRNG()
    llm: Optional[LLMClient] = LLMClient(settings) if settings.features_llm else None

    print("Adventorator CLI — type 'help' for commands. Ctrl+C to exit.")
    try:
        while True:
            try:
                line = input("adv> ").strip()
            except EOFError:
                break
            if not line:
                continue
            parts = shlex.split(line)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit"):
                break
            if cmd in ("help", "?"):
                _print_help()
                continue
            if cmd == "roll":
                cmd_roll(args, rng)
                continue
            if cmd == "check":
                cmd_check(args, rng)
                continue
            if cmd == "narrate":
                if not args:
                    print("Usage: narrate \"your message\"")
                    continue
                asyncio.run(cmd_narrate(" ".join(args), llm))
                continue
            if cmd == "history":
                n = int(args[0]) if args else 10
                asyncio.run(cmd_history(n))
                continue

            print("Unknown command. Type 'help'.")
    finally:
        if llm:
            try:
                asyncio.run(llm.close())
            except Exception:
                pass


if __name__ == "__main__":
    # Ensure src/ is importable if run directly without PYTHONPATH; best-effort only.
    if "Adventorator" not in sys.modules:
        # User should set PYTHONPATH=./src, but we won’t hard-fail here.
        pass
    main()
