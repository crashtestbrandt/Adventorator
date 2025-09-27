#!/usr/bin/env python3
"""Demo script for manifest validation (STORY-CDA-IMPORT-002A).

Usage:
    python scripts/demo_manifest_validation.py <manifest_path>
    python scripts/demo_manifest_validation.py --happy-path
    python scripts/demo_manifest_validation.py --tampered

Demonstrates:
- Manifest schema validation
- Content hash verification
- Deterministic manifest hashing
- Event payload generation
- Feature flag integration
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator import models
from Adventorator.db import session_scope
from Adventorator.importer import ImporterError, create_manifest_phase
from Adventorator.manifest_validation import ManifestValidationError


async def _emit_manifest_event(phase, campaign_id: int, payload: dict) -> models.Event:
    async with session_scope() as session:
        campaign = await session.get(models.Campaign, campaign_id)
        if campaign is None:
            session.add(models.Campaign(id=campaign_id, name=f"Demo Campaign {campaign_id}"))
            await session.flush()
        return await phase.emit_seed_event(session, campaign_id, payload)


def demo_manifest_validation(manifest_path: Path, features_importer: bool = True) -> None:
    """Demonstrate manifest validation workflow."""
    print(f"=== Manifest Validation Demo ===")
    print(f"Manifest: {manifest_path}")
    print(f"Feature flag (features.importer): {features_importer}")
    print()
    
    try:
        # Create manifest phase with feature flag
        phase = create_manifest_phase(features_importer=features_importer)
        
        # Validate and register manifest
        print("Step 1: Validating manifest...")
        result = phase.validate_and_register(manifest_path)
        
        manifest = result["manifest"]
        manifest_hash = result["manifest_hash"]
        
        print(f"✓ Manifest validation successful!")
        print(f"  Package ID: {manifest['package_id']}")
        print(f"  Schema version: {manifest['schema_version']}")
        print(f"  Ruleset version: {manifest['ruleset_version']}")
        print(f"  Content files: {len(manifest.get('content_index', {}))}")
        print(f"  Manifest hash: {manifest_hash}")
        print()
        
        # Demonstrate event emission
        print("Step 2: Emitting synthetic seed event...")
        campaign_id = 4242
        try:
            event = asyncio.run(
                _emit_manifest_event(phase, campaign_id, result["event_payload"])
            )
            print("✓ Synthetic event persisted!")
            print(f"  Event type: {event.type}")
            print(f"  Replay ordinal: {event.replay_ordinal}")
            print(f"  Payload keys: {', '.join(event.payload.keys())}")
            print()
        except Exception as exc:  # pragma: no cover - demo fallback
            print(f"⚠️ Unable to persist event (database not available?): {exc}")
            print()
        
        # Show ImportLog entry structure
        print("Step 3: ImportLog provenance entry...")
        log_entry = result["import_log_entry"]
        print(f"✓ ImportLog entry prepared!")
        print(f"  Phase: {log_entry['phase']}")
        print(f"  Object type: {log_entry['object_type']}")
        print(f"  Stable ID: {log_entry['stable_id']}")
        print(f"  File hash: {log_entry['file_hash']}")
        print(f"  Action: {log_entry['action']}")
        print()
        
        print("🎉 Complete workflow successful!")
        
    except ImporterError as exc:
        print(f"❌ Importer error: {exc}")
        return
    except ManifestValidationError as exc:
        print(f"❌ Manifest validation failed:")
        # Print multi-line errors with indentation
        for line in str(exc).split('\n'):
            print(f"   {line}")
        return
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo manifest validation workflow")
    parser.add_argument(
        "manifest_path",
        nargs="?",
        help="Path to package.manifest.json file"
    )
    parser.add_argument(
        "--happy-path",
        action="store_true",
        help="Use happy-path fixture"
    )
    parser.add_argument(
        "--tampered",
        action="store_true", 
        help="Use tampered fixture (should fail)"
    )
    parser.add_argument(
        "--no-feature-flag",
        action="store_true",
        help="Disable features.importer flag (should fail)"
    )
    
    args = parser.parse_args()
    
    # Determine manifest path
    if args.happy_path:
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")
    elif args.tampered:
        manifest_path = Path("tests/fixtures/import/manifest/tampered/package.manifest.json")
    elif args.manifest_path:
        manifest_path = Path(args.manifest_path)
    else:
        print("Error: Must specify manifest path or use --happy-path/--tampered")
        return 1
    
    if not manifest_path.exists():
        print(f"Error: Manifest file not found: {manifest_path}")
        return 1
    
    # Run demo
    features_importer = not args.no_feature_flag
    demo_manifest_validation(manifest_path, features_importer)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())