from Adventorator.action_validation import (
    ExecutionRequest,
    Plan,
    PlanStep,
    execution_request_from_tool_chain,
    plan_from_planner_output,
    planner_output_from_plan,
    tool_chain_from_execution_request,
)
from Adventorator.executor import ToolCallChain, ToolStep
from Adventorator.planner_schemas import PlannerOutput


def test_planner_round_trip_identity():
    original = PlannerOutput(command="roll", subcommand=None, args={"expr": "1d20"})
    plan = plan_from_planner_output(original)
    assert isinstance(plan, Plan)
    assert plan.feasible is True
    assert plan.steps == [PlanStep(op="roll", args={"expr": "1d20"}, guards=[])]

    round_trip = planner_output_from_plan(plan)
    assert round_trip == original


def test_executor_round_trip_identity():
    chain = ToolCallChain(
        request_id="req-1",
        scene_id=42,
        steps=[
            ToolStep(tool="check", args={"ability": "DEX", "dc": 12}, requires_confirmation=True),
            ToolStep(tool="attack", args={"target": "goblin"}, requires_confirmation=False),
        ],
    )
    req = execution_request_from_tool_chain(chain, plan_id="plan-abc")
    assert isinstance(req, ExecutionRequest)
    assert req.context["scene_id"] == 42
    restored = tool_chain_from_execution_request(req)
    assert restored.request_id == chain.request_id
    assert restored.scene_id == chain.scene_id
    assert [step.tool for step in restored.steps] == ["check", "attack"]
    assert restored.steps[0].args == chain.steps[0].args
    assert restored.steps[0].requires_confirmation is True
    assert restored.actor_id == chain.actor_id
