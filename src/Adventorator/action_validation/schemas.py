"""Pydantic models and interop helpers for the action validation pipeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from Adventorator.executor import ToolCallChain, ToolStep
from Adventorator.planner_schemas import PlannerOutput


class IntentFrame(BaseModel):
    action: str
    actor: str
    object_ref: str | None = None
    target_ref: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    tags: set[str] = Field(default_factory=set)
    guidance: dict[str, Any] = Field(default_factory=dict)

    model_config = dict(extra="forbid", frozen=True)


class AskReport(BaseModel):
    intent: IntentFrame
    candidates: list[IntentFrame] = Field(default_factory=list)
    policy_flags: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""

    model_config = dict(extra="forbid", frozen=True)


class PlanStep(BaseModel):
    op: str
    args: dict[str, Any] = Field(default_factory=dict)
    guards: list[str] = Field(default_factory=list)

    model_config = dict(extra="forbid", frozen=True)


class Plan(BaseModel):
    feasible: bool
    plan_id: str
    steps: list[PlanStep] = Field(default_factory=list)
    failed_predicates: list[dict[str, Any]] = Field(default_factory=list)
    repairs: list[str] = Field(default_factory=list)
    alternatives: list[IntentFrame] = Field(default_factory=list)
    rationale: str = ""

    model_config = dict(extra="forbid", frozen=True)


class ExecutionRequest(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = dict(extra="forbid", frozen=True)


class ExecutionResult(BaseModel):
    ok: bool
    events: list[dict[str, Any]] = Field(default_factory=list)
    state_delta: dict[str, Any] = Field(default_factory=dict)
    narration_cues: list[str] = Field(default_factory=list)

    model_config = dict(extra="forbid", frozen=True)


# -----------------
# Conversion helpers
# -----------------


def _normalize_command_name(command: str, subcommand: str | None) -> str:
    base = command.strip()
    if subcommand:
        return f"{base}.{subcommand.strip()}"
    return base


def _split_command_name(op: str) -> tuple[str, str | None]:
    if "." in op:
        top, _, sub = op.partition(".")
        top = top.strip()
        sub = sub.strip()
        if not sub:
            sub = None  # type: ignore[assignment]
        return top, sub  # type: ignore[return-value]
    return op.strip(), None


def _stable_plan_id(seed: Iterable[tuple[str, Any]]) -> str:
    payload = json.dumps(sorted((k, v) for k, v in seed), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def plan_from_planner_output(out: PlannerOutput, *, plan_id: str | None = None) -> Plan:
    op = _normalize_command_name(out.command, out.subcommand)
    step = PlanStep(op=op, args=dict(out.args))
    computed_id = _stable_plan_id(
        (
            ("command", out.command),
            ("subcommand", out.subcommand),
            ("args", out.args),
        )
    )
    if plan_id is None:
        plan_id_non_none: str = computed_id
    else:
        plan_id_non_none = plan_id
    return Plan(feasible=True, plan_id=plan_id_non_none, steps=[step])


def planner_output_from_plan(plan: Plan) -> PlannerOutput:
    if not plan.steps:
        raise ValueError("Plan has no steps to convert")
    first = plan.steps[0]
    command, subcommand = _split_command_name(first.op)
    return PlannerOutput(command=command, subcommand=subcommand, args=dict(first.args))


def execution_request_from_tool_chain(chain: ToolCallChain, *, plan_id: str) -> ExecutionRequest:
    steps = [
        PlanStep(
            op=step.tool,
            args=dict(step.args),
            guards=[],
        )
        for step in chain.steps
    ]
    context = {
        "request_id": chain.request_id,
        "scene_id": chain.scene_id,
    }
    if chain.actor_id is not None:
        context["actor_id"] = chain.actor_id
    return ExecutionRequest(plan_id=plan_id, steps=steps, context=context)


def tool_chain_from_execution_request(req: ExecutionRequest) -> ToolCallChain:
    request_id = str(req.context.get("request_id", req.plan_id))
    scene_id = int(req.context.get("scene_id", 0))
    actor_id = req.context.get("actor_id")
    steps = [
        ToolStep(tool=step.op, args=dict(step.args), requires_confirmation=True)
        for step in req.steps
    ]
    return ToolCallChain(request_id=request_id, scene_id=scene_id, steps=steps, actor_id=actor_id)
