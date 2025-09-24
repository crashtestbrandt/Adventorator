#!/usr/bin/env python
"""Extract the structured plan JSON from mixed web_cli --raw output.

Usage:
  python scripts/extract_plan_json.py < web_cli_output.txt
  web_cli_command | python scripts/extract_plan_json.py

Heuristic:
  - Scan all lines, collect substrings that look like JSON objects '{...}'.
  - Parse with orjson (fallback to json) and keep those containing key 'plan' with 'steps'.
  - Output the last matching object pretty-printed.
Exit codes:
  0 success (even if no object found; prints warning to stderr)
  1 unexpected exception.
"""
from __future__ import annotations

import json
import sys

try:
    import orjson  # type: ignore
except Exception:  # pragma: no cover
    orjson = None  # type: ignore

BUFFER = sys.stdin.read().splitlines()

# Heuristic: collect lines after the delimiter line that starts Raw Plan Payload until closing separator dashes.
collecting = False
raw_lines: list[str] = []
for line in BUFFER:
    if line.strip().startswith('--- Raw Plan Payload'):
        collecting = True
        raw_lines.clear()
        continue
    if collecting and line.strip().startswith('--------------------------------------'):
        collecting = False
        # attempt parse
        blob = '\n'.join(raw_lines)
        try:
            if orjson:
                obj = orjson.loads(blob)
            else:
                obj = json.loads(blob)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get('plan'), dict):
            steps = obj['plan'].get('steps') if isinstance(obj['plan'], dict) else None
            if isinstance(steps, list):
                best = obj  # type: ignore[name-defined]
        continue
    if collecting:
        raw_lines.append(line)

best = locals().get('best')  # type: ignore

if best is None:
    print("// No plan JSON found", file=sys.stderr)
    sys.exit(0)

if orjson:
    sys.stdout.write(orjson.dumps(best, option=orjson.OPT_INDENT_2).decode())
else:
    json.dump(best, sys.stdout, indent=2)
    sys.stdout.write("\n")
