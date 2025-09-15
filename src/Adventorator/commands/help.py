from __future__ import annotations

from pydantic import Field

from Adventorator.commanding import Invocation, Option, find_command, slash_command
from Adventorator.metrics import inc_counter


class HelpOpts(Option):
	# Optional focus area; capped to keep payloads tiny and avoid abuse.
	topic: str | None = Field(
		default=None,
		description="Optional topic to focus help on (e.g., roll, check, sheet)",
		max_length=24,
	)


def _has_command(name: str, sub: str | None = None) -> bool:
	return find_command(name, sub) is not None


def _build_help_text(settings, topic: str | None) -> str:
	# Feature flags (defensive defaults when settings is None)
	features_llm = bool(getattr(settings, "features_llm", False))
	planner_enabled = bool(getattr(settings, "feature_planner_enabled", True))

	lines: list[str] = []

	# Title
	lines.append("Adventorator — Quick Start")
	lines.append("")

	# Quick-start section
	lines.append("Quick start:")
	if _has_command("sheet", "create"):
		lines.append("• Create a character: use /sheet create with the json option (<=16KB).")
	if _has_command("roll", None):
		lines.append("• Roll dice: use /roll with an expr like 1d20 or 2d6+3.")
	if _has_command("check", None):
		lines.append("• Make a check: use /check with ability (STR/DEX/...) and optional dc.")
	if _has_command("do", None):
		lines.append("• Describe an action: use /do to narrate what you attempt.")
	if _has_command("ooc", None):
		lines.append("• Speak OOC: use /ooc to talk out-of-character; it's saved to transcripts.")

	# Planner visibility depends on features
	if _has_command("plan", None):
		if features_llm and planner_enabled:
			lines.append("• Not sure? Try /plan — it interprets " +
				"a simple sentence into a safe command.")
		else:
			lines.append("• Planner (/plan) is currently disabled in this server.")

	# Next steps
	show_any = _has_command("sheet", "show") or _has_command("roll", None)
	if show_any:
		lines.append("")
		lines.append("Next steps:")
		if _has_command("sheet", "show"):
			lines.append("• View a character: /sheet show with the name option.")
		if _has_command("roll", None):
			lines.append("• Learn advantage/disadvantage: " +
				"/roll supports advantage/disadvantage flags.")
		lines.append("• Scenes and transcripts: your OOC and planner prompts may be persisted.")

	# Troubleshooting
	lines.append("")
	lines.append("Troubleshooting:")
	lines.append("• Invalid options: commands validate inputs and reply with a brief correction.")
	if _has_command("plan", None):
		if not (features_llm and planner_enabled):
			lines.append("• Planner disabled: use /roll or /check directly instead.")
		else:
			lines.append("• Planner undecided: try /roll 1d20 or /check with an ability and dc.")

	# Ephemeral hint to avoid channel spam
	lines.append("")
	lines.append("Responses are ephemeral by default to reduce channel noise.")

	return "\n".join(lines)


@slash_command(
	name="help",
	description="Show quick-start help for Adventorator.",
	option_model=HelpOpts,
)
async def help_cmd(inv: Invocation, opts: HelpOpts):
	# Minimal metric for observability
	inc_counter("help.view")

	# Build feature-aware help text; keep it concise (<2k chars for Discord)
	topic = (opts.topic or "").strip() or None
	text = _build_help_text(inv.settings, topic)
	await inv.responder.send(text, ephemeral=True)

