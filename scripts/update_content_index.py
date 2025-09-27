#!/usr/bin/env python3
"""Recompute and update content_index in package.manifest.json.

Usage:
  python scripts/update_content_index.py --package-root campaigns/sample-campaign
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.tools.package_utils import update_content_index  # type: ignore


def main() -> int:
    ap = argparse.ArgumentParser(description="Update manifest content_index hashes")
    ap.add_argument("--package-root", type=Path, required=True)
    args = ap.parse_args()

    manifest_path = args.package_root / "package.manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest not found: {manifest_path}")
        return 2

    result = update_content_index(manifest_path, args.package_root)
    print("content_index updated")
    print(f"  added:   {len(result.added)}")
    print(f"  updated: {len(result.updated)}")
    print(f"  removed: {len(result.removed)}")
    if result.added:
        print("  added keys:")
        for k, v in sorted(result.added.items()):
            print(f"    - {k}: {v}")
    if result.updated:
        print("  updated keys:")
        for k, (old, new) in sorted(result.updated.items()):
            print(f"    - {k}: {old} -> {new}")
    if result.removed:
        print("  removed keys:")
        for k in sorted(result.removed):
            print(f"    - {k}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
