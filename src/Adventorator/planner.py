"""Planner service: build tool catalog, prompt the LLM, and validate output."""

from __future__ import annotations

import time
from typing import Any

import orjson
import structlog

from Adventorator.action_validation.schemas import Plan, plan_from_planner_output
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import all_commands
from Adventorator.llm import LLMClient
from Adventorator.llm_utils import extract_first_json
from Adventorator.planner_prompts import SYSTEM_PLANNER
from Adventorator.planner_schemas import PlannerOutput

# --- Allowlist of commands the planner may route to (defense-in-depth) ---
_ALLOWED: set[str] = {"roll", "check", "sheet.create", "sheet.show", "do", "ooc"}

def _is_allowed(name: str) -> bool:
    return name in _ALLOWED


# --- Simple in-process cache to suppress duplicate LLM calls for 30s ---
_CACHE_TTL = 30.0
_CachedPayload = tuple[float, dict[str, Any]] | tuple[float, dict[str, Any], str]
_plan_cache: dict[tuple[int, str], _CachedPayload] = {}

def _cache_get(scene_id: int, msg: str) -> tuple[dict[str, Any], str] | None:
    key = (scene_id, msg.strip())
    now = time.time()
    v = _plan_cache.get(key)
    if not v:
        return None
    if len(v) == 3:
        ts, payload, schema = v
    else:
        ts, payload = v  # type: ignore[misc]
        schema = "planner_output"
    if now - ts <= _CACHE_TTL:
        return payload, schema
    return None

def _cache_put(scene_id: int, msg: str, plan_json: dict[str, Any], *, schema: str) -> None:
    _plan_cache[(scene_id, msg.strip())] = (time.time(), plan_json, schema)


def reset_plan_cache() -> None:
    """Clear the in-process planner cache.

    This is primarily used by tests to avoid cross-test interference.
    """
    _plan_cache.clear()


def _catalog() -> list[dict[str, Any]]:
    # Ensure registry is populated (safe to call multiple times)
    cmds = all_commands()
    if not cmds:
        load_all_commands()
        cmds = all_commands()

    cat: list[dict[str, Any]] = []
    for cmd in cmds.values():
        name = cmd.name if not cmd.subcommand else f"{cmd.name}.{cmd.subcommand}"
        # Pydantic v2 schema for Option models
        try:
            schema = cmd.option_model.model_json_schema()  # type: ignore[attr-defined]
        except Exception:
            schema = {"type": "object"}
        cat.append(
            {
                "name": name,
                "description": cmd.description,
                "options_schema": schema,
            }
        )
    return cat


def build_planner_messages(user_msg: str) -> list[dict[str, Any]]:
    tools_json = orjson.dumps(_catalog()).decode("utf-8")
    # Dynamically enumerate available rules from the rules engine (Dnd5eRuleset)
    from Adventorator.rules.engine import Dnd5eRuleset
    ruleset = Dnd5eRuleset()
    # List available rules as method names (excluding dunder and private)
    rule_methods = [
        m for m in dir(ruleset)
        if not m.startswith("_") and callable(getattr(ruleset, m))
    ]
    rules_list = "\n".join(f"- {m}" for m in rule_methods)
    rules_text = f"AVAILABLE RULES:\n{rules_list}\n"
    return [
        {"role": "system", "content": SYSTEM_PLANNER + "\n" + rules_text},
        {
            "role": "user",
            "content": f"TOOLS:\n{tools_json}\n\nUSER:\n{user_msg}",
        },
    ]


async def plan(
    llm: LLMClient, user_msg: str, *, return_plan: bool = False
) -> Plan | PlannerOutput | None:
    log = structlog.get_logger()
    started = time.monotonic()
    log.info("planner.request.initiated", user_msg=user_msg)
    msgs = build_planner_messages(user_msg)
    text = await llm.generate_response(msgs)
    data = extract_first_json(text or "")
    if not data or not isinstance(data, dict):
        log.warning("planner.parse.failed", raw_text_preview=(text or "")[:200])
        log.info(
            "planner.request.completed",
            status="parse_failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return None
    try:
        out = PlannerOutput.model_validate(data)
        log.info("planner.parse.valid", plan=out.model_dump())
        log.info(
            "planner.request.completed",
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        if return_plan:
            return plan_from_planner_output(out)
        return out
    except Exception:
        log.warning("planner.validation.failed", raw_text_preview=(text or "")[:200])
        log.info(
            "planner.request.completed",
            status="validation_failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return None
