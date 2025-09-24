"""Tests for entity seed events and ordering (STORY-CDA-IMPORT-002B)."""

import json
import tempfile
from pathlib import Path

from Adventorator.importer import EntityPhase, create_entity_phase


class TestEntitySeedEvents:
    """Test seed.entity_created event generation and ordering."""

    def test_deterministic_event_ordering_across_runs(self):
        """Test that entity events maintain consistent ordering across multiple runs."""
        phase = EntityPhase(features_importer_enabled=True)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()
            
            # Create entities in non-sorted filename order
            entities_data = [
                {
                    "stable_id": "01JA6Z7F8NPC00000000000002",
                    "kind": "npc",
                    "name": "Bob the Guard",
                    "tags": ["guard"],
                    "affordances": ["talk", "patrol"]
                },
                {
                    "stable_id": "01JA6Z7F8LOC00000000000001", 
                    "kind": "location",
                    "name": "Main Gate",
                    "tags": ["entrance"],
                    "affordances": ["enter", "exit"]
                },
                {
                    "stable_id": "01JA6Z7F8NPC00000000000001",
                    "kind": "npc",
                    "name": "Alice the Mage",
                    "tags": ["mage"],
                    "affordances": ["cast_spell"]
                }
            ]
            
            # Write entities with intentionally different filename order
            filenames = ["z_bob.json", "a_gate.json", "m_alice.json"]
            for entity_data, filename in zip(entities_data, filenames):
                entity_file = entities_dir / filename
                with open(entity_file, "w", encoding="utf-8") as f:
                    json.dump(entity_data, f)
            
            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}
            
            # Run parsing twice to verify consistent ordering
            entities1 = phase.parse_and_validate_entities(package_root, manifest)
            entities2 = phase.parse_and_validate_entities(package_root, manifest)
            
            # Both runs should produce same ordering
            assert len(entities1) == len(entities2) == 3
            
            for i in range(3):
                assert entities1[i]["stable_id"] == entities2[i]["stable_id"]
                assert entities1[i]["kind"] == entities2[i]["kind"]
            
            # Expected order: location first (alphabetically), then npcs by stable_id
            assert entities1[0]["kind"] == "location"
            assert entities1[0]["stable_id"] == "01JA6Z7F8LOC00000000000001"
            
            assert entities1[1]["kind"] == "npc"
            assert entities1[1]["stable_id"] == "01JA6Z7F8NPC00000000000001"  # Alice
            
            assert entities1[2]["kind"] == "npc" 
            assert entities1[2]["stable_id"] == "01JA6Z7F8NPC00000000000002"  # Bob
            
            # Generate events and verify ordering consistency
            events1 = phase.create_seed_events(entities1)
            events2 = phase.create_seed_events(entities2)
            
            assert len(events1) == len(events2) == 3
            for i in range(3):
                assert events1[i]["stable_id"] == events2[i]["stable_id"]

    def test_seed_event_payload_structure(self):
        """Test that seed.entity_created events have correct payload structure."""
        phase = EntityPhase(features_importer_enabled=True)
        
        entities = [
            {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada the Archivist", 
                "tags": ["librarian", "scholar"],
                "affordances": ["greet", "research", "lend_book"],
                "traits": ["curious", "patient"],
                "props": {
                    "role": "head_librarian",
                    "years_service": 15,
                    "specialization": "ancient_texts"
                },
                "provenance": {
                    "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
                    "source_path": "entities/ada.json",
                    "file_hash": "7d478136a27ad013caa5a225cbc4629998bb38b29c133b5c11a87803ceb7a1e6"
                }
            }
        ]
        
        events = phase.create_seed_events(entities)
        
        assert len(events) == 1
        event = events[0]
        
        # Verify all required fields are present
        required_fields = ["stable_id", "kind", "name", "tags", "affordances", "provenance"]
        for field in required_fields:
            assert field in event, f"Missing required field: {field}"
        
        # Verify field contents
        assert event["stable_id"] == "01JA6Z7F8NPC00000000000000"
        assert event["kind"] == "npc"
        assert event["name"] == "Ada the Archivist"
        assert event["tags"] == ["librarian", "scholar"]
        assert event["affordances"] == ["greet", "research", "lend_book"]
        assert event["traits"] == ["curious", "patient"]
        assert event["props"]["role"] == "head_librarian"
        
        # Verify provenance structure
        prov = event["provenance"]
        assert prov["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"
        assert prov["source_path"] == "entities/ada.json"
        assert prov["file_hash"] == "7d478136a27ad013caa5a225cbc4629998bb38b29c133b5c11a87803ceb7a1e6"

    def test_seed_event_minimal_entity(self):
        """Test seed event generation for entity with only required fields."""
        phase = EntityPhase(features_importer_enabled=True)
        
        entities = [
            {
                "stable_id": "01JA6Z7F8ITM00000000000000",
                "kind": "item",
                "name": "Magic Sword",
                "tags": ["weapon"],
                "affordances": ["wield"],
                # No optional traits or props
                "provenance": {
                    "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
                    "source_path": "entities/sword.json",
                    "file_hash": "abc123def456"
                }
            }
        ]
        
        events = phase.create_seed_events(entities)
        
        assert len(events) == 1
        event = events[0]
        
        # Should have all required fields
        assert event["stable_id"] == "01JA6Z7F8ITM00000000000000"
        assert event["kind"] == "item"
        assert event["name"] == "Magic Sword"
        assert event["tags"] == ["weapon"]
        assert event["affordances"] == ["wield"]
        assert event["provenance"]["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"
        
        # Should not have optional fields if not provided
        assert "traits" not in event
        assert "props" not in event

    def test_idempotent_skip_metrics_scenario(self):
        """Test scenario where identical entities should be skipped with metrics."""
        phase = EntityPhase(features_importer_enabled=True)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()
            
            # Create identical entity files (same content, different filenames)
            entity_data = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada",
                "tags": ["librarian"],
                "affordances": ["greet"]
            }
            
            # Write same entity to two different files
            for filename in ["entity1.json", "entity2.json"]:
                entity_file = entities_dir / filename
                with open(entity_file, "w", encoding="utf-8") as f:
                    json.dump(entity_data, f, separators=(',', ':'))  # Consistent formatting
            
            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}
            
            # Should parse entities and correctly skip idempotent duplicates
            entities = phase.parse_and_validate_entities(package_root, manifest)
            
            # Only one entity should be returned (duplicate filtered out)
            assert len(entities) == 1
            assert entities[0]["stable_id"] == "01JA6Z7F8NPC00000000000000"
            
            # Events should be generated for only the unique entity
            events = phase.create_seed_events(entities)
            assert len(events) == 1


if __name__ == "__main__":
    test_class = TestEntitySeedEvents()
    test_methods = [method for method in dir(test_class) if method.startswith("test_")]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            method = getattr(test_class, method_name)
            method()
            print(f"✓ {method_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {method_name}: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")