"""Planner service: build tool catalog, prompt the LLM, and validate output."""

from __future__ import annotations

from typing import Any

import orjson

from Adventorator.commanding import all_commands
from Adventorator.llm import LLMClient
from Adventorator.llm_utils import extract_first_json
from Adventorator.planner_prompts import SYSTEM_PLANNER
from Adventorator.planner_schemas import PlannerOutput


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
