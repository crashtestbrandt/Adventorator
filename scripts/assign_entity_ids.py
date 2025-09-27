#!/usr/bin/env python3
"""Assign or normalize entity stable_id fields to valid ULIDs.

Scans entities/*.json and writes a new ULID to `stable_id` if missing or invalid.
Rewrites files in place and prints a summary. Safe to re-run (idempotent).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.tools.ulid import generate_ulid, is_ulid  # type: ignore


def process_entities(entities_dir: Path) -> dict[str, tuple[str | None, str]]:
    changes: dict[str, tuple[str | None, str]] = {}
    if not entities_dir.exists():
        return changes
    for fp in sorted(entities_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        old = data.get("stable_id") if isinstance(data, dict) else None
        if not isinstance(old, str) or not is_ulid(old):
            new_id = generate_ulid()
            if isinstance(data, dict):
                data["stable_id"] = new_id
                fp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                changes[fp.name] = (old if isinstance(old, str) else None, new_id)
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description="Assign ULIDs to entity JSON files")
    ap.add_argument("--package-root", type=Path, required=True)
    args = ap.parse_args()

    entities_dir = args.package_root / "entities"
    changes = process_entities(entities_dir)
    print("Entity ID assignment:")
    if not changes:
        print("  no changes (all valid)")
        return 0
    for name, (old, new) in changes.items():
        print(f"  - {name}: {old or '<missing>'} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
