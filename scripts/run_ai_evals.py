#!/usr/bin/env python3
"""Static validation for AI evaluation definitions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

FRONT_MATTER_RE = "---\n"
REQUIRED_CASE_KEYS = {"id", "inputs", "expected_keywords"}


def parse_front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(FRONT_MATTER_RE):
        return {}
    _, rest = text.split(FRONT_MATTER_RE, 1)
    meta_block, _, _ = rest.partition(FRONT_MATTER_RE)
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        parts = line.split(":", 1)
        key, value = parts
        key = key.strip()
        if not key:
            continue
        meta[key.lower()] = value.strip()
    return meta


def validate_eval_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path}: invalid JSON - {exc}"]

    name = data.get("name")
    prompt_path = data.get("prompt")
    cases = data.get("cases")

    if not isinstance(name, str) or not name.strip():
        errors.append(f"{path}: 'name' must be a non-empty string")
    if not isinstance(prompt_path, str) or not prompt_path.strip():
        errors.append(f"{path}: 'prompt' must reference a prompt file")
    else:
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            errors.append(f"{path}: referenced prompt '{prompt_path}' does not exist")
        else:
            meta = parse_front_matter(prompt_file)
            if not meta:
                errors.append(f"{path}: prompt '{prompt_path}' missing required front matter")
            elif "id" not in meta or "version" not in meta:
                errors.append(
                    f"{path}: prompt '{prompt_path}' front matter missing 'id' or 'version'"
                )
    if not isinstance(cases, list) or not cases:
        errors.append(f"{path}: 'cases' must be a non-empty list")
    else:
        for idx, case in enumerate(cases):
            prefix = f"{path} case[{idx}]"
            if not isinstance(case, dict):
                errors.append(f"{prefix}: must be an object with keys {sorted(REQUIRED_CASE_KEYS)}")
                continue
            missing = [k for k in REQUIRED_CASE_KEYS if k not in case]
            if missing:
                errors.append(f"{prefix}: missing keys {missing}")
            expected_keywords = case.get("expected_keywords")
            if not isinstance(expected_keywords, list) or not all(
                isinstance(item, str) and item.strip() for item in expected_keywords
            ):
                errors.append(f"{prefix}: 'expected_keywords' must be a list of strings")
    return errors


def main() -> int:
    eval_dir = Path("prompts/evals")
    if not eval_dir.exists():
        print("No AI evaluation definitions found; skipping.")
        return 0

    eval_files = sorted(eval_dir.glob("*.json"))
    if not eval_files:
        print("No AI evaluation definitions found; skipping.")
        return 0

    errors: list[str] = []
    for path in eval_files:
        errors.extend(validate_eval_file(path))

    if errors:
        print("AI evaluation validation failed:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print("AI evaluation definitions validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
