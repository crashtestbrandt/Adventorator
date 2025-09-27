#!/usr/bin/env python3
"""Watch a package folder and auto-update content_index on changes.

Polling-based to avoid extra deps. Optionally re-runs import on changes.

Usage:
  python scripts/watch_package.py --package-root campaigns/sample-campaign --campaign-id 1 --import-on-change
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path
import sys
import time

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.tools.package_utils import enumerate_ingested_files, update_content_index  # type: ignore
from scripts.assign_entity_ids import process_entities  # type: ignore
from Adventorator.importer import run_full_import_with_database  # type: ignore


def snapshot(pkg: Path) -> dict[str, str]:
    sig: dict[str, str] = {}
    for fp in enumerate_ingested_files(pkg):
        try:
            m = hashlib.sha256(fp.read_bytes()).hexdigest()
            sig[fp.as_posix()] = m
        except Exception:
            pass
    return sig


def main() -> int:
    ap = argparse.ArgumentParser(description="Watch a package and auto-update hashes")
    ap.add_argument("--package-root", type=Path, required=True)
    ap.add_argument("--campaign-id", type=int, default=None)
    ap.add_argument("--import-on-change", action="store_true")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    pkg = args.package_root
    manifest = pkg / "package.manifest.json"
    if not manifest.exists():
        print("Manifest not found; aborting")
        return 2

    prev = snapshot(pkg)
    print("Watching for changes... Ctrl+C to stop")
    try:
        while True:
            time.sleep(args.interval)
            cur = snapshot(pkg)
            if cur != prev:
                prev = cur
                # First, ensure entities have valid ULIDs
                changes_ids = process_entities(pkg / "entities")
                if changes_ids:
                    print("assigned entity IDs:")
                    for name, (old, new) in changes_ids.items():
                        print(f"  - {name}: {old or '<missing>'} -> {new}")
                changes = update_content_index(manifest, pkg)
                print(
                    f"content_index updated: added={len(changes.added)} updated={len(changes.updated)} removed={len(changes.removed)}"
                )
                if args.import_on_change and args.campaign_id is not None:
                    result = asyncio.run(
                        run_full_import_with_database(
                            package_root=pkg, campaign_id=args.campaign_id,
                            features_importer=True, features_importer_embeddings=True,
                        )
                    )
                    skip = result.get("idempotent_skip", False)
                    print("import done (idempotent_skip=", skip, ")")
    except KeyboardInterrupt:
        print("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
