#!/usr/bin/env python3
"""End-to-end import driver: update manifest hashes, preflight DB, run import.

Usage:
  python scripts/import_package.py --package-root campaigns/sample-campaign --campaign-id 1 \
      [--no-embeddings] [--no-importer] [--skip-preflight] [--no-hash-update]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.tools.package_utils import update_content_index  # type: ignore
from Adventorator.importer import run_full_import_with_database, ImporterError  # type: ignore


def main() -> int:
    ap = argparse.ArgumentParser(description="Import a package end-to-end")
    ap.add_argument("--package-root", type=Path, required=True)
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--skip-preflight", action="store_true")
    ap.add_argument("--no-hash-update", action="store_true")
    ap.add_argument("--no-importer", action="store_true")
    ap.add_argument("--no-embeddings", action="store_true")
    args = ap.parse_args()

    pkg = args.package_root
    manifest = pkg / "package.manifest.json"
    if not manifest.exists():
        print(f"Error: manifest not found: {manifest}")
        return 2

    if not args.no_hash_update:
        changes = update_content_index(manifest, pkg)
        print("content_index updated:")
        print(f"  added={len(changes.added)} updated={len(changes.updated)} removed={len(changes.removed)}")

    if not args.skip_preflight:
        # Invoke preflight script via subprocess to avoid import path issues
        import os
        import subprocess

        preflight_path = Path(__file__).parent / "preflight_import.py"
        env = os.environ.copy()
        # Preserve PYTHONPATH for src
        env.setdefault("PYTHONPATH", str(Path(__file__).parent.parent / "src"))
        code = subprocess.call([sys.executable, str(preflight_path)], env=env)
        if code != 0:
            print("Preflight failed; aborting import")
            return code

    features_importer = not args.no_importer
    features_importer_embeddings = not args.no_embeddings
    try:
        result = asyncio.run(
            run_full_import_with_database(
                package_root=pkg,
                campaign_id=args.campaign_id,
                features_importer=features_importer,
                features_importer_embeddings=features_importer_embeddings,
            )
        )
    except ImporterError as exc:
        print(f"ImporterError: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1

    summary = {
        "hash_chain_tip": result.get("hash_chain_tip"),
        "event_count": result.get("database_state", {}).get("event_count"),
        "import_log_count": result.get("database_state", {}).get("import_log_count"),
        "idempotent_skip": result.get("idempotent_skip", False),
        "finalization_phase": result.get("import_log_summary", {}).get("phase"),
    }
    print("=== Import Summary ===")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
