"""Pydantic contracts and conversion helpers for the action validation pipeline."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from Adventorator.executor import ToolCallChain, ToolStep
from Adventorator.planner_schemas import PlannerOutput
from Adventorator.schemas import LLMOutput, LLMProposal


class IntentFrame(BaseModel):
    action: str
    actor: str
    object_ref: str | None = None
    target_ref: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    tags: set[str] = Field(default_factory=set)
    guidance: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AskReport(BaseModel):
    intent: IntentFrame
    candidates: list[IntentFrame] = Field(default_factory=list)
    policy_flags: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class PlanStep(BaseModel):
    op: str
    args: dict[str, Any] = Field(default_factory=dict)
    guards: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Plan(BaseModel):
    feasible: bool
    plan_id: str
    steps: list[PlanStep] = Field(default_factory=list)
    failed_predicates: list[dict[str, Any]] = Field(default_factory=list)
    repairs: list[str] = Field(default_factory=list)
    alternatives: list[IntentFrame] = Field(default_factory=list)
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class ExecutionRequest(BaseModel):
    plan_id: str
    steps: list[PlanStep] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ExecutionResult(BaseModel):
    ok: bool
    events: list[dict[str, Any]] = Field(default_factory=list)
    state_delta: dict[str, Any] = Field(default_factory=dict)
    narration_cues: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


_PLANNER_CONFIDENCE_PREFIX = "__legacy_confidence__="
_NARRATION_CONTEXT_KEY = "__legacy_narration__"
_TOOLCHAIN_CONTEXT_KEY = "__legacy_toolchain__"


def _join_command(command: str, subcommand: str | None) -> str:
    if subcommand:
        return f"{command}.{subcommand}"
    return command


def _split_command(op: str) -> tuple[str, str | None]:
    if "." in op:
        command, sub = op.split(".", 1)
        return command, sub
    return op, None


def _encode_confidence(confidence: float | None) -> list[str]:
    if confidence is None:
        return []
    return [f"{_PLANNER_CONFIDENCE_PREFIX}{confidence}"]


def _decode_confidence(guards: Iterable[str]) -> tuple[float | None, list[str]]:
    remaining: list[str] = []
    confidence: float | None = None
    for guard in guards:
        if guard.startswith(_PLANNER_CONFIDENCE_PREFIX):
            try:
                confidence = float(guard[len(_PLANNER_CONFIDENCE_PREFIX) :])
            except ValueError:
                remaining.append(guard)
        else:
            remaining.append(guard)
    return confidence, remaining


def planner_output_to_plan(output: PlannerOutput, *, plan_id: str | None = None) -> Plan:
    """Wrap an existing planner result in a single-step :class:`Plan`."""

    op = _join_command(output.command, output.subcommand)
    guards = _encode_confidence(output.confidence)
    step = PlanStep(op=op, args=dict(output.args), guards=guards)
    return Plan(
        feasible=True,
        plan_id=plan_id or f"legacy-planner::{op}",
        steps=[step],
        rationale=output.rationale or "",
    )


def plan_to_planner_output(plan: Plan) -> PlannerOutput:
    """Convert a single-step :class:`Plan` back to :class:`PlannerOutput`."""

    if not plan.steps:
        raise ValueError("Plan contains no steps")
    if len(plan.steps) != 1:
        raise ValueError("Only single-step plans can be converted to PlannerOutput")
    step = plan.steps[0]
    command, subcommand = _split_command(step.op)
    confidence, _ = _decode_confidence(step.guards)
    rationale = plan.rationale or None
    return PlannerOutput(
        command=command,
        subcommand=subcommand,
        args=dict(step.args),
        confidence=confidence,
        rationale=rationale,
    )


def plan_step_from_llm_proposal(proposal: LLMProposal) -> PlanStep:
    """Convert an orchestrator LLM proposal into a :class:`PlanStep`."""

    payload = proposal.model_dump()
    action = payload.pop("action")
    reason = payload.pop("reason")
    args = {k: v for k, v in payload.items() if v is not None}
    args["reason"] = reason
    return PlanStep(op=action, args=args)


def llm_proposal_from_plan_step(step: PlanStep) -> LLMProposal:
    """Reconstruct an :class:`LLMProposal` from a :class:`PlanStep`."""

    op = step.op
    if op == "check":
        op = "ability_check"
    args = dict(step.args)
    reason = args.get("reason", "")
    base = {
        "action": op,
        "reason": reason,
        "ability": args.get("ability"),
        "suggested_dc": args.get("suggested_dc") or args.get("dc"),
        "attacker": args.get("attacker"),
        "target": args.get("target"),
        "attack_bonus": args.get("attack_bonus"),
        "target_ac": args.get("target_ac"),
        "damage": args.get("damage"),
        "advantage": args.get("advantage"),
        "disadvantage": args.get("disadvantage"),
        "condition": args.get("condition"),
        "duration": args.get("duration"),
    }
    return LLMProposal(**base)


def execution_request_from_llm_output(
    output: LLMOutput,
    *,
    plan_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> ExecutionRequest:
    """Build an :class:`ExecutionRequest` from an :class:`LLMOutput`."""

    step = plan_step_from_llm_proposal(output.proposal)
    ctx = dict(context or {})
    ctx.setdefault(_NARRATION_CONTEXT_KEY, output.narration)
    plan_identifier = plan_id or f"legacy-orchestrator::{step.op}"
    return ExecutionRequest(plan_id=plan_identifier, steps=[step], context=ctx)


def llm_output_from_execution_request(request: ExecutionRequest) -> LLMOutput:
    """Recover an :class:`LLMOutput` from an :class:`ExecutionRequest`."""

    if not request.steps:
        raise ValueError("ExecutionRequest contains no steps")
    step = request.steps[0]
    proposal = llm_proposal_from_plan_step(step)
    narration = request.context.get(_NARRATION_CONTEXT_KEY, "")
    return LLMOutput(proposal=proposal, narration=narration)


def _plan_step_from_tool_step(step: ToolStep) -> PlanStep:
    return PlanStep(op=step.tool, args=dict(step.args))


def _tool_step_from_plan_step(step: PlanStep, *, metadata: dict[str, Any] | None = None) -> ToolStep:
    meta = metadata or {}
    tool = step.op
    if tool == "ability_check":
        tool = "check"
    args = dict(step.args)
    if tool == "check" and "suggested_dc" in args and "dc" not in args:
        args = dict(args)
        args["dc"] = args.pop("suggested_dc")
    return ToolStep(
        tool=tool,
        args=args,
        requires_confirmation=bool(meta.get("requires_confirmation", False)),
        visibility=str(meta.get("visibility", "ephemeral")),
    )


def execution_request_from_tool_call_chain(
    chain: ToolCallChain,
    *,
    plan_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> ExecutionRequest:
    """Convert a legacy :class:`ToolCallChain` to an :class:`ExecutionRequest`."""

    ctx = dict(context or {})
    ctx[_TOOLCHAIN_CONTEXT_KEY] = {
        "request_id": chain.request_id,
        "scene_id": chain.scene_id,
        "actor_id": chain.actor_id,
        "steps": [
            {
                "requires_confirmation": step.requires_confirmation,
                "visibility": step.visibility,
            }
            for step in chain.steps
        ],
    }
    steps = [_plan_step_from_tool_step(step) for step in chain.steps]
    plan_identifier = plan_id or chain.request_id
    return ExecutionRequest(plan_id=plan_identifier, steps=steps, context=ctx)


def tool_call_chain_from_execution_request(request: ExecutionRequest) -> ToolCallChain:
    """Convert an :class:`ExecutionRequest` back into a :class:`ToolCallChain`."""

    meta = request.context.get(_TOOLCHAIN_CONTEXT_KEY, {})
    request_id = str(meta.get("request_id", request.plan_id))
    scene_id = int(meta.get("scene_id", 0))
    actor_id = meta.get("actor_id")
    step_meta = list(meta.get("steps", []))
    steps: list[ToolStep] = []
    for idx, step in enumerate(request.steps):
        metadata = step_meta[idx] if idx < len(step_meta) else {}
        steps.append(_tool_step_from_plan_step(step, metadata=metadata))
    return ToolCallChain(request_id=request_id, scene_id=scene_id, steps=steps, actor_id=actor_id)
