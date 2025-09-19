#!/usr/bin/env python3
"""Verify observability playbook documents key performance budgets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOC_PATH = Path("docs/implementation/observability-and-flags.md")
SECTION_REQUIREMENTS = {
    "Planner Budgets": ["planner.latency.ms", "p95"],
    "Orchestrator Budgets": ["orchestrator.latency.ms", "p95"],
    "Executor Budgets": ["executor.preview.duration_ms", "p95"],
    "Encounter Observability Budget": ["encounter.round.duration_ms", "p95"],
}


def extract_section(text: str, header: str) -> str | None:
    pattern = re.compile(rf"^## {re.escape(header)}\n(.*?)(\n## |\Z)", re.DOTALL | re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)


def main() -> int:
    try:
        text = DOC_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Missing observability playbook: {DOC_PATH}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for header, tokens in SECTION_REQUIREMENTS.items():
        section = extract_section(text, header)
        if section is None:
            errors.append(f"Section '{header}' is missing from {DOC_PATH}")
            continue
        for token in tokens:
            if token not in section:
                errors.append(f"Section '{header}' missing required token '{token}'")

    if errors:
        print("Performance budget check failed:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print(
        "Performance budgets documented for planner, orchestrator, executor, and encounter flows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
