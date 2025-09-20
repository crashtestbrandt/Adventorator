import pytest

from Adventorator.action_validation import record_plan_steps, record_predicate_gate_outcome
from Adventorator.action_validation.schemas import Plan, PlanStep
from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [PlanStep(op="check", args={"ability": "DEX"})],
        [
            PlanStep(op="attack", args={"target": "goblin"}),
            PlanStep(op="apply_condition", args={"target": "goblin", "condition": "stunned"}),
        ],
    ],
)
def test_record_plan_steps_counts_steps(steps):
    reset_counters()
    plan = Plan(feasible=True, plan_id="plan-123", steps=list(steps))
    record_plan_steps(plan)
    assert get_counter("plan.steps.count") == len(steps)


def test_record_predicate_gate_outcomes():
    reset_counters()
    record_predicate_gate_outcome(ok=True)
    record_predicate_gate_outcome(ok=False)
    record_predicate_gate_outcome(ok=False)
    assert get_counter("predicate.gate.ok") == 1
    assert get_counter("predicate.gate.error") == 2
