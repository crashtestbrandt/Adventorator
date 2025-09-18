from Adventorator.action_validation import (
    execution_request_from_llm_output,
    execution_request_from_tool_call_chain,
    llm_output_from_execution_request,
    plan_step_from_llm_proposal,
    planner_output_to_plan,
    plan_to_planner_output,
    tool_call_chain_from_execution_request,
)
from Adventorator.executor import ToolCallChain, ToolStep
from Adventorator.planner_schemas import PlannerOutput
from Adventorator.schemas import LLMOutput, LLMProposal


def test_planner_round_trip_roll():
    original = PlannerOutput(
        command="roll",
        args={"expr": "2d6+3"},
        confidence=0.75,
        rationale="Rolling damage",
    )
    plan = planner_output_to_plan(original, plan_id="plan-roll")
    rebuilt = plan_to_planner_output(plan)
    assert rebuilt == original


def test_planner_round_trip_check():
    original = PlannerOutput(
        command="check",
        args={"ability": "DEX", "dc": 15},
        confidence=0.6,
        rationale="Dexterity check",
    )
    plan = planner_output_to_plan(original, plan_id="plan-check")
    rebuilt = plan_to_planner_output(plan)
    assert rebuilt == original


def test_orchestrator_round_trip_ability_check():
    proposal = LLMProposal(
        action="ability_check",
        ability="WIS",
        suggested_dc=13,
        reason="Assess perception",
    )
    llm_out = LLMOutput(proposal=proposal, narration="You carefully scan the hallway.")
    request = execution_request_from_llm_output(
        llm_out, plan_id="orc-check", context={"trace_id": "abc123"}
    )
    rebuilt = llm_output_from_execution_request(request)
    assert rebuilt == llm_out


def test_orchestrator_round_trip_attack():
    proposal = LLMProposal(
        action="attack",
        attacker="hero",
        target="goblin",
        attack_bonus=5,
        target_ac=12,
        damage={"dice": "1d8", "mod": 3},
        advantage=False,
        disadvantage=False,
        reason="Strike the foe",
    )
    llm_out = LLMOutput(proposal=proposal, narration="The hero lunges forward.")
    request = execution_request_from_llm_output(llm_out, plan_id="orc-attack")
    rebuilt = llm_output_from_execution_request(request)
    assert rebuilt == llm_out


def test_tool_chain_round_trip():
    chain = ToolCallChain(
        request_id="req-1",
        scene_id=42,
        actor_id="char-7",
        steps=[
            ToolStep(tool="roll", args={"expr": "1d20", "seed": 123}, visibility="public"),
            ToolStep(
                tool="attack",
                args={
                    "attacker": "hero",
                    "target": "goblin",
                    "attack_bonus": 5,
                    "target_ac": 14,
                    "damage": {"dice": "1d8", "mod": 2},
                },
                requires_confirmation=True,
            ),
        ],
    )
    request = execution_request_from_tool_call_chain(chain, plan_id="plan-chain")
    rebuilt = tool_call_chain_from_execution_request(request)
    assert rebuilt == chain


def test_plan_step_from_llm_proposal_includes_reason():
    proposal = LLMProposal(
        action="ability_check",
        ability="INT",
        suggested_dc=18,
        reason="Evaluate the arcane glyph",
    )
    step = plan_step_from_llm_proposal(proposal)
    assert step.args["reason"] == "Evaluate the arcane glyph"
