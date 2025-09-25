#!/usr/bin/env python3
"""Demonstration script for entity import functionality (STORY-CDA-IMPORT-002B).

This script demonstrates the complete entity ingestion pipeline:
1. Entity file parsing and validation
2. Deterministic ordering and collision detection  
3. Provenance tracking with file hashes
4. Synthetic seed.entity_created event generation
5. Metrics and structured logging

Usage:
    python scripts/demo_entity_import.py [--package-path PATH]
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.importer import EntityPhase, EntityCollisionError, EntityValidationError


def demo_entity_import(package_path: Path):
    """Demonstrate entity import functionality."""
    print("🚀 Entity Import Demo (STORY-CDA-IMPORT-002B)")
    print("=" * 60)
    
    # Initialize entity phase
    entity_phase = EntityPhase(features_importer_enabled=True)
    print("✓ Entity phase initialized with feature flag enabled")
    
    # Mock manifest
    manifest = {
        "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
        "schema_version": 1,
        "content_index": {}
    }
    print(f"✓ Using manifest with package_id: {manifest['package_id']}")
    
    try:
        # Parse and validate entities
        print(f"\n📂 Scanning entities in: {package_path}")
        entities = entity_phase.parse_and_validate_entities(package_path, manifest)
        
        print(f"✓ Successfully parsed {len(entities)} entities")
        
        if not entities:
            print("ℹ No entities found - create some entity JSON files in entities/ directory")
            return
        
        # Display entity summary
        print(f"\n📋 Entity Summary:")
        for i, entity in enumerate(entities, 1):
            prov = entity["provenance"]
            print(f"  {i}. {entity['name']} ({entity['kind']})")
            print(f"     Stable ID: {entity['stable_id']}")
            print(f"     Source: {prov['source_path']}")
            print(f"     Hash: {prov['file_hash'][:16]}...")
            print(f"     Tags: {', '.join(entity['tags'])}")
            print(f"     Affordances: {', '.join(entity['affordances'])}")
        
        # Demonstrate deterministic ordering
        print(f"\n🔄 Deterministic Ordering:")
        print("   Entities are sorted by (kind, stable_id, source_path)")
        
        kinds = [e["kind"] for e in entities]
        stable_ids = [e["stable_id"] for e in entities]
        print(f"   Order: {list(zip(kinds, stable_ids))}")
        
        # Re-parse to verify consistent ordering
        entities2 = entity_phase.parse_and_validate_entities(package_path, manifest)
        if [e["stable_id"] for e in entities] == [e["stable_id"] for e in entities2]:
            print("   ✓ Ordering is consistent across runs")
        else:
            print("   ✗ Ordering inconsistency detected!")
        
        # Generate seed events
        print(f"\n🎯 Generating seed.entity_created events:")
        events = entity_phase.create_seed_events(entities)
        
        for i, event in enumerate(events, 1):
            print(f"  Event {i}: {event['name']} ({event['kind']})")
            print(f"    Provenance: {event['provenance']['package_id']}")
            print(f"    Fields: {len(event)} total")
        
        # Show example event payload
        if events:
            print(f"\n📝 Example Event Payload (first entity):")
            example_event = events[0]
            formatted_event = json.dumps(example_event, indent=2)
            print(formatted_event)
        
        print(f"\n✅ Demo completed successfully!")
        print(f"   Parsed: {len(entities)} entities")
        print(f"   Generated: {len(events)} seed events")
        print(f"   All events maintain deterministic ordering")
        
    except EntityCollisionError as e:
        print(f"\n💥 Collision Error: {e}")
        print("   This indicates two entities with the same stable_id but different content")
        print("   Check your entity files for duplicate stable_id values")
    
    except EntityValidationError as e:
        print(f"\n❌ Validation Error: {e}")
        print("   This indicates an entity file doesn't meet the schema requirements")
        print("   Required fields: stable_id, kind, name, tags, affordances")
    
    except Exception as e:
        print(f"\n💥 Unexpected Error: {e}")
        return 1
    
    return 0


def main():
    """Main demo function."""
    parser = argparse.ArgumentParser(description="Demo entity import functionality")
    parser.add_argument(
        "--package-path", 
        type=Path,
        default=Path("tests/fixtures/import/manifest/happy-path"),
        help="Path to package directory containing entities/ folder"
    )
    
    args = parser.parse_args()
    
    if not args.package_path.exists():
        print(f"❌ Package path does not exist: {args.package_path}")
        print("   Using default test fixtures or create your own package structure:")
        print("   package-root/")
        print("     entities/")
        print("       npc.json")
        print("       location.json")
        return 1
    
    return demo_entity_import(args.package_path)


if __name__ == "__main__":
    sys.exit(main())