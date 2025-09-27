#!/usr/bin/env python3
"""Scaffold a campaign data package and initialize its manifest.

Creates a directory tree, writes a minimal package.manifest.json with a new
package_id (ULID), and runs the content_index updater once.

Usage:
  python scripts/scaffold_package.py --dest campaigns/new-pack --name "Greenhollow Demo"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.tools.ulid import generate_ulid  # type: ignore
from Adventorator.tools.package_utils import save_manifest  # type: ignore


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scaffold(dest: Path, name: str | None) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    # Minimal README
    write_file(dest / "README.md", f"# {name or 'New Campaign'}\n\nScaffolded pack.\n")

    # Minimal manifest
    manifest = {
        "package_id": generate_ulid(),
        "schema_version": 1,
        "engine_contract_range": {"min": "1.2.0", "max": "1.2.0"},
        "dependencies": [],
        "content_index": {},
        "ruleset_version": "5.2.1",
        "recommended_flags": {
            "features.importer": True,
            "features.ask.enabled": True,
            "features.retrieval.enabled": True,
            "features.llm": False,
        },
    }
    save_manifest(dest / "package.manifest.json", manifest)

    # Seed folders
    (dest / "entities").mkdir(exist_ok=True)
    (dest / "edges").mkdir(exist_ok=True)
    (dest / "ontology").mkdir(exist_ok=True)
    (dest / "lore").mkdir(exist_ok=True)

    # Hello-world lore chunk to prove ingestion works
    write_file(dest / "lore" / "intro.md", "Welcome to your new adventure!\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a campaign data package")
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--name", type=str, default=None)
    args = ap.parse_args()

    scaffold(args.dest, args.name)

    # Run hash updater once
    from Adventorator.tools.package_utils import update_content_index  # type: ignore

    manifest_path = args.dest / "package.manifest.json"
    changes = update_content_index(manifest_path, args.dest)
    print("Scaffold complete.")
    print(f"package_id: {json.loads(manifest_path.read_text(encoding='utf-8'))['package_id']}")
    print(
        f"content_index initialized: added={len(changes.added)} updated={len(changes.updated)} removed={len(changes.removed)}"
    )
    print(f"Pack root: {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
