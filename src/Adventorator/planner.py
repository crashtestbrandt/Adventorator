"""Planner service: build tool catalog, prompt the LLM, and validate output."""

from __future__ import annotations

from typing import Any
import time

import orjson

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
_plan_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}

def _cache_get(scene_id: int, msg: str) -> dict[str, Any] | None:
    key = (scene_id, msg.strip())
    now = time.time()
    v = _plan_cache.get(key)
    if not v:
        return None
    ts, payload = v
    if now - ts <= _CACHE_TTL:
        return payload
    return None

def _cache_put(scene_id: int, msg: str, plan_json: dict[str, Any]) -> None:
    _plan_cache[(scene_id, msg.strip())] = (time.time(), plan_json)


def _catalog() -> list[dict[str, Any]]:
    cat: list[dict[str, Any]] = []
    for cmd in all_commands().values():
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
    return [
        {"role": "system", "content": SYSTEM_PLANNER},
        {
            "role": "user",
            "content": f"TOOLS:\n{tools_json}\n\nUSER:\n{user_msg}",
        },
    ]


async def plan(llm: LLMClient, user_msg: str) -> PlannerOutput | None:
    msgs = build_planner_messages(user_msg)
    text = await llm.generate_response(msgs)
    data = extract_first_json(text or "")
    if not data or not isinstance(data, dict):
        return None
    try:
        return PlannerOutput.model_validate(data)
    except Exception:
        return None
