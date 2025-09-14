# src/Adventorator/commands/roll.py
from pydantic import Field

from Adventorator.commanding import Invocation, Option, slash_command


class RollOpts(Option):
    expr: str = Field(default="1d20", description="Dice expression")
    advantage: bool = Field(default=False, description="Roll with advantage")
    disadvantage: bool = Field(default=False, description="Roll with disadvantage")

@slash_command(
    name="roll",
    description="Roll dice (e.g., 2d6+3).",
    option_model=RollOpts,
    # you could include Discord-only metadata here too
)
async def roll(inv: Invocation, opts: RollOpts):
    # Prefer injected ruleset; fallback to default if not provided (tests/CLI)
    if inv.ruleset is None:
        from Adventorator.rules.engine import Dnd5eRuleset

        rs = Dnd5eRuleset()
    else:
        rs = inv.ruleset
    res = rs.roll_dice(
        opts.expr or "1d20",
        advantage=opts.advantage,
        disadvantage=opts.disadvantage,
    )
    suffix = "(adv)" if opts.advantage else "(dis)" if opts.disadvantage else ""
    text = f"🎲 `{opts.expr}` → rolls {res.rolls} {suffix} = **{res.total}**"
    await inv.responder.send(text)
