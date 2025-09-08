# src/Adventorator/commands/check.py
from pydantic import Field

from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.rules.checks import CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG


class CheckOpts(Option):
    ability: str = Field(default="DEX", description="Ability (e.g., STR, DEX)")
    score: int = Field(default=10, description="Ability score (e.g., 10)")
    proficient: bool = Field(default=False, description="Proficient in this check")
    expertise: bool = Field(default=False, description="Expertise applies (double prof)")
    prof_bonus: int = Field(default=2, description="Proficiency bonus")
    dc: int = Field(default=15, description="Difficulty Class")
    advantage: bool = Field(default=False, description="Roll with advantage")
    disadvantage: bool = Field(default=False, description="Roll with disadvantage")


@slash_command(
    name="check",
    description="Make an ability check with options.",
    option_model=CheckOpts,
)
async def check_command(inv: Invocation, opts: CheckOpts):
    ability = (opts.ability or "DEX").upper()
    rng = DiceRNG()
    d20 = rng.roll("1d20", advantage=opts.advantage, disadvantage=opts.disadvantage)

    ci = CheckInput(
        ability=ability,
        score=int(opts.score),
        proficient=bool(opts.proficient),
        expertise=bool(opts.expertise),
        proficiency_bonus=int(opts.prof_bonus),
        dc=int(opts.dc),
        advantage=bool(opts.advantage),
        disadvantage=bool(opts.disadvantage),
    )

    d20_rolls = d20.rolls[:2] if len(d20.rolls) >= 2 else [d20.rolls[0]]
    out = compute_check(ci, d20_rolls)
    verdict = "✅ success" if out.success else "❌ fail"
    text = (
        f"🧪 **{ability}** check vs DC {opts.dc}\n"
        f"• d20: {out.d20} → pick {out.pick}\n"
        f"• mod: {out.mod:+}\n"
        f"= **{out.total}** → {verdict}"
    )
    await inv.responder.send(text)
