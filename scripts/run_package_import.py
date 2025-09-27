#!/usr/bin/env python3
"""
Run a full DB-backed import for a content package.

Usage:
  python scripts/run_package_import.py --package-root campaigns/sample-campaign --campaign-id 1 \
      [--no-embeddings] [--no-importer]

This uses Adventorator.importer.run_full_import_with_database to validate the
manifest, parse entities/edges/ontology/lore, and persist synthetic seed events
and ImportLog entries. It will create a minimal Campaign row when missing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.importer import run_full_import_with_database, ImporterError  # type: ignore


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a full DB-backed import for a package")
    ap.add_argument("--package-root", type=Path, required=True, help="Path to package root directory")
    ap.add_argument("--campaign-id", type=int, required=True, help="Campaign id to import into")
    ap.add_argument(
        "--no-importer",
        action="store_true",
        help="Disable importer feature flag (features.importer=false)",
    )
    ap.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Disable embeddings processing feature (features.importer_embeddings=false)",
    )
    args = ap.parse_args()

    if not args.package_root.exists():
        print(f"Error: package root not found: {args.package_root}")
        return 2

    features_importer = not args.no_importer
    features_importer_embeddings = not args.no_embeddings

    try:
        result = asyncio.run(
            run_full_import_with_database(
                package_root=args.package_root,
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

    # Print a compact summary
    summary = {
        "hash_chain_tip": result.get("hash_chain_tip"),
        "event_count": result.get("database_state", {}).get("event_count"),
        "import_log_count": result.get("database_state", {}).get("import_log_count"),
        "idempotent_skip": result.get("idempotent_skip", False),
        "finalization_phase": result.get("import_log_summary", {}).get("phase"),
    }
    print("=== Import Summary ===")
    print(json.dumps(summary, indent=2, default=str))

    # Show completion payload keys if available
    completion = result.get("completion_payload")
    if completion:
        print("\nCompletion payload keys:", ", ".join(sorted(completion.keys())))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
