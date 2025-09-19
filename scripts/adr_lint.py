#!/usr/bin/env python3
"""Validate ADR files for required headings and status formatting."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_HEADINGS = [
    "# ",
    "## Status",
    "## Context",
    "## Decision",
    "## Rationale",
    "## Consequences",
    "## References",
]

ALLOWED_STATUSES = {
    "Proposed",
    "Accepted",
    "Deprecated",
    "Superseded",
}

STATUS_SECTION_RE = re.compile(r"^## Status\s*\n(?P<value>.+)$", re.MULTILINE)


def lint_adr(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"{path}: file not found"]

    # Ensure all required headings are present.
    for heading in REQUIRED_HEADINGS:
        if heading == "# ":
            if not text.lstrip().startswith("# "):
                errors.append(f"{path}: expected title heading starting with '# '")
            continue
        if heading not in text:
            errors.append(f"{path}: missing '{heading}' section")

    status_match = STATUS_SECTION_RE.search(text)
    if not status_match:
        errors.append(f"{path}: unable to parse '## Status' value")
    else:
        status_line = status_match.group("value").strip()
        if not any(status_line.startswith(allowed) for allowed in ALLOWED_STATUSES):
            allowed_display = ", ".join(sorted(ALLOWED_STATUSES))
            errors.append(
                f"{path}: status '{status_line}' is invalid (expected one of: {allowed_display})"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint Adventorator ADR files")
    parser.add_argument("paths", nargs="*", help="ADR files to lint")
    args = parser.parse_args()

    paths = (
        [Path(p) for p in args.paths] if args.paths else sorted(Path("docs/adr").glob("ADR-*.md"))
    )
    all_errors: list[str] = []
    for path in paths:
        all_errors.extend(lint_adr(path))

    if all_errors:
        print("ADR lint failed:", file=sys.stderr)
        for err in all_errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print("All ADR files passed lint checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
