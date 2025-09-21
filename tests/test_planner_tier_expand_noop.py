
from Adventorator.action_validation.schemas import Plan, PlanStep
from Adventorator.planner_tiers import expand_plan


def test_expand_plan_noop_multi_step(caplog):
    # Plan already multi-step; expansion at level 2 should not alter list
    p = Plan(
        feasible=True,
        plan_id="abc123456789abcd",
        steps=[
            PlanStep(op="roll.d20", args={}),
            PlanStep(op="roll.d4", args={}),
        ],
    )
    caplog.set_level("INFO")
    out = expand_plan(p, 2)
    assert out is p  # unchanged object reference when noop
    assert len(out.steps) == 2
    assert [s.op for s in out.steps] == ["roll.d20", "roll.d4"]
