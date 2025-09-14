# src/Adventorator/commands/check.py
from pydantic import Field

from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.rules.checks import CheckInput


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
    if inv.ruleset is None:
        from Adventorator.rules.engine import Dnd5eRuleset

        rs = Dnd5eRuleset()
    else:
        rs = inv.ruleset
    out = rs.perform_check(ci)
    verdict = "✅ success" if out.success else "❌ fail"
    text = (
        f"🧪 **{ability}** check vs DC {opts.dc}\n"
        f"• d20: {out.d20} → pick {out.pick}\n"
        f"• mod: {out.mod:+}\n"
        f"= **{out.total}** → {verdict}"
    )
    await inv.responder.send(text)
