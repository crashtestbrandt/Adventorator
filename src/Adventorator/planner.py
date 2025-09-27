"""Planner service: build tool catalog, prompt the LLM, and validate output."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import orjson
import structlog

from Adventorator.action_validation.schemas import Plan, plan_from_planner_output
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import all_commands
from Adventorator.llm import LLMClient
from Adventorator.llm_utils import extract_first_json
from Adventorator.metrics import inc_counter, register_reset_plan_cache_callback
from Adventorator.planner_prompts import SYSTEM_PLANNER
from Adventorator.planner_schemas import PlannerOutput

# --- Allowlist of commands the planner may route to (defense-in-depth) ---
_ALLOWED: set[str] = {"roll", "check", "sheet.create", "sheet.show", "do"}


def _is_allowed(name: str) -> bool:
    return name in _ALLOWED


# --- Simple in-process cache to suppress duplicate LLM calls for 30s ---
_CACHE_TTL = 30.0


@dataclass(slots=True)
class _CacheEntry:
    timestamp: float
    payload: dict[str, Any]
    schema: str = "planner_output"


_LegacyCacheEntry = tuple[float, dict[str, Any]] | tuple[float, dict[str, Any], str]
_plan_cache: dict[tuple[int, int, str], _CacheEntry | _LegacyCacheEntry] = {}


def _normalize_cache_entry(
    key: tuple[int, int, str], value: _CacheEntry | _LegacyCacheEntry
) -> _CacheEntry:
    if isinstance(value, _CacheEntry):
        return value
    # legacy tuple forms
    if len(value) == 3:
        ts, payload, schema = value  # type: ignore[misc]
        entry = _CacheEntry(ts, payload, schema)  # type: ignore[arg-type]
    elif len(value) == 2:  # type: ignore[arg-type]
        ts, payload = value  # type: ignore[misc]
        entry = _CacheEntry(ts, payload)  # type: ignore[arg-type]
    else:  # pragma: no cover - defensive
        raise ValueError("Unexpected planner cache entry")
    _plan_cache[key] = entry
    return entry


def _cache_get(guild_id: int, channel_id: int, msg: str) -> tuple[dict[str, Any], str] | None:
    """Fetch a cached planner output/plan.

    Key is (guild_id, channel_id, message). Instrumented with detailed events
    to diagnose miss conditions seen in tests where a hit was expected.
    """
    log = structlog.get_logger()
    key = (guild_id, channel_id, msg.strip())
    now = time.time()
    v = _plan_cache.get(key)
    if not v:
        inc_counter("planner.cache.miss")
        log.info(
            "planner.cache.miss",
            guild_id=guild_id,
            channel_id=channel_id,
            msg_hash=hash(msg.strip()),
            msg_preview=msg[:60],
            cache_size=len(_plan_cache),
        )
        return None
    entry = _normalize_cache_entry(key, v)
    age = now - entry.timestamp
    if age <= _CACHE_TTL:
        inc_counter("planner.cache.hit")
        log.info(
            "planner.cache.hit",
            guild_id=guild_id,
            channel_id=channel_id,
            msg_hash=hash(msg.strip()),
            age_ms=int(age * 1000),
            schema=entry.schema,
        )
        return entry.payload, entry.schema
    # Expired
    inc_counter("planner.cache.expired")
    log.info(
        "planner.cache.expired",
        guild_id=guild_id,
        channel_id=channel_id,
        msg_hash=hash(msg.strip()),
        age_ms=int(age * 1000),
        ttl_s=_CACHE_TTL,
    )
    # Remove stale entry to keep cache tidy
    try:
        del _plan_cache[key]
    except Exception:
        pass
    return None


def _cache_put(
    guild_id: int, channel_id: int, msg: str, plan_json: dict[str, Any], *, schema: str
) -> None:
    key = (guild_id, channel_id, msg.strip())
    _plan_cache[key] = _CacheEntry(time.time(), plan_json, schema)
    try:
        log = structlog.get_logger()
        log.info(
            "planner.cache.store",
            guild_id=guild_id,
            channel_id=channel_id,
            msg_hash=hash(msg.strip()),
            schema=schema,
            cache_size=len(_plan_cache),
        )
    except Exception:
        pass


def reset_plan_cache() -> None:
    """Clear the in-process planner cache.

    This is primarily used by tests to avoid cross-test interference.
    """
    _plan_cache.clear()


register_reset_plan_cache_callback(reset_plan_cache)


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
        m for m in dir(ruleset) if not m.startswith("_") and callable(getattr(ruleset, m))
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
            from Adventorator.config import load_settings
            from Adventorator.planner_tiers import (
                expand_plan,
                guards_for_steps,
                resolve_planning_level,
            )

            plan_obj = plan_from_planner_output(out)
            settings = None
            try:
                settings = load_settings()
            except Exception:  # pragma: no cover
                settings = None
            level = resolve_planning_level(settings)
            tiers_enabled = (
                getattr(settings, "features_planning_tiers", False)
                if settings is not None
                else False
            )
            log.info(
                "planner.tier.selected",
                level=level,
                tiers_enabled=tiers_enabled,
                step_count=len(plan_obj.steps),
            )
            pre_ops = [s.op for s in plan_obj.steps]
            log.debug(
                "planner.tier.pre_expand",
                level=level,
                steps=pre_ops,
                tiers_enabled=tiers_enabled,
            )
            plan_obj = expand_plan(plan_obj, level)
            post_ops = [s.op for s in plan_obj.steps]
            log.debug(
                "planner.tier.post_expand",
                level=level,
                steps=post_ops,
                changed=pre_ops != post_ops,
            )
            guards_for_steps(plan_obj.steps, tiers_enabled=tiers_enabled)
            log.debug(
                "planner.tier.guards_applied",
                tiers_enabled=tiers_enabled,
                guard_counts=[len(s.guards) for s in plan_obj.steps],
            )
            # Emit a single structured snapshot event with the full plan
            # for external tooling / CLI raw capture.
            try:
                total_guards = sum(len(s.guards) for s in plan_obj.steps)
                log.info(
                    "planner.plan_snapshot",
                    level=level,
                    tiers_enabled=tiers_enabled,
                    step_count=len(plan_obj.steps),
                    guard_total=total_guards,
                    plan=plan_obj.model_dump(),
                )
            except Exception:  # pragma: no cover - snapshot emission should never raise
                pass
            try:
                from Adventorator.action_validation.metrics import (
                    record_plan_steps,
                    record_planning_tier,
                )

                record_planning_tier(level)
                record_plan_steps(plan_obj)
            except Exception:  # pragma: no cover
                pass
            return plan_obj
        return out
    except Exception:
        log.warning("planner.validation.failed", raw_text_preview=(text or "")[:200])
        log.info(
            "planner.request.completed",
            status="validation_failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return None
