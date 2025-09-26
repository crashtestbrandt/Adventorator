"""Tests for entity parsing phase (STORY-CDA-IMPORT-002B)."""

import json
import tempfile
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None

from Adventorator.importer import (
    EntityCollisionError,
    EntityPhase,
    EntityValidationError,
    ImporterError,
    create_entity_phase,
)


class TestEntityPhase:
    """Test entity parsing phase."""

    def test_create_entity_phase_feature_flag_enabled(self):
        """Test creating entity phase with feature flag enabled."""
        phase = create_entity_phase(features_importer=True)
        assert phase.features_importer_enabled is True

    def test_create_entity_phase_feature_flag_disabled(self):
        """Test creating entity phase with feature flag disabled."""
        phase = create_entity_phase(features_importer=False)
        assert phase.features_importer_enabled is False

    def test_parse_entities_feature_flag_disabled(self):
        """Test that parsing fails when feature flag is disabled."""
        phase = EntityPhase(features_importer_enabled=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            try:
                phase.parse_and_validate_entities(package_root, manifest)
                raise AssertionError("Should have raised ImporterError")
            except ImporterError as e:
                assert "Importer feature flag is disabled" in str(e)

    def test_parse_entities_no_entities_directory(self):
        """Test parsing when entities directory doesn't exist."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            entities = phase.parse_and_validate_entities(package_root, manifest)
            assert entities == []

    def test_parse_entities_valid_entity(self):
        """Test parsing a valid entity file."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create a valid entity file
            entity_data = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada the Archivist",
                "tags": ["librarian"],
                "affordances": ["greet"],
                "traits": ["curious"],
                "props": {"role": "knowledge_keeper"},
            }

            entity_file = entities_dir / "npc.json"
            with open(entity_file, "w", encoding="utf-8") as f:
                json.dump(entity_data, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}
            entities = phase.parse_and_validate_entities(package_root, manifest)

            assert len(entities) == 1
            entity = entities[0]

            # Check entity data
            assert entity["stable_id"] == entity_data["stable_id"]
            assert entity["kind"] == entity_data["kind"]
            assert entity["name"] == entity_data["name"]
            assert entity["tags"] == entity_data["tags"]
            assert entity["affordances"] == entity_data["affordances"]

            # Check provenance
            assert "provenance" in entity
            prov = entity["provenance"]
            assert prov["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"
            assert prov["source_path"] == "entities/npc.json"
            assert len(prov["file_hash"]) == 64  # SHA-256 hex length

    def test_parse_entities_missing_required_field(self):
        """Test parsing entity with missing required field."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create entity missing required field
            entity_data = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada the Archivist",
                # Missing "tags" and "affordances"
            }

            entity_file = entities_dir / "invalid.json"
            with open(entity_file, "w", encoding="utf-8") as f:
                json.dump(entity_data, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            try:
                phase.parse_and_validate_entities(package_root, manifest)
                raise AssertionError("Should have raised EntityValidationError")
            except EntityValidationError as e:
                assert "'tags' is a required property" in str(e)

    def test_parse_entities_collision_different_hash(self):
        """Test collision detection with different file hashes."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create two entities with same stable_id but different content
            stable_id = "01JA6Z7F8NPC00000000000000"

            entity1 = {
                "stable_id": stable_id,
                "kind": "npc",
                "name": "Ada",
                "tags": ["librarian"],
                "affordances": ["greet"],
            }

            entity2 = {
                "stable_id": stable_id,
                "kind": "npc",
                "name": "Ada the Great",  # Different name
                "tags": ["librarian"],
                "affordances": ["greet"],
            }

            with open(entities_dir / "entity1.json", "w", encoding="utf-8") as f:
                json.dump(entity1, f)
            with open(entities_dir / "entity2.json", "w", encoding="utf-8") as f:
                json.dump(entity2, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            try:
                phase.parse_and_validate_entities(package_root, manifest)
                raise AssertionError("Should have raised EntityCollisionError")
            except EntityCollisionError as e:
                assert "Stable ID collision detected" in str(e)

    def test_create_seed_events(self):
        """Test creation of seed.entity_created events."""
        phase = EntityPhase(features_importer_enabled=True)

        entities = [
            {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada",
                "tags": ["librarian"],
                "affordances": ["greet"],
                "traits": ["curious"],
                "props": {"role": "keeper"},
                "provenance": {
                    "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
                    "source_path": "entities/ada.json",
                    "file_hash": "abc123",
                },
            }
        ]

        events = phase.create_seed_events(entities)

        assert len(events) == 1
        event = events[0]

        # Check event payload structure
        assert event["stable_id"] == "01JA6Z7F8NPC00000000000000"
        assert event["kind"] == "npc"
        assert event["name"] == "Ada"
        assert event["tags"] == ["librarian"]
        assert event["affordances"] == ["greet"]
        assert event["traits"] == ["curious"]
        assert event["props"] == {"role": "keeper"}
        assert event["provenance"]["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"

    def test_compute_file_hash(self):
        """Test file hash computation."""
        phase = EntityPhase(features_importer_enabled=True)

        content = '{"test": "data"}'
        hash1 = phase._compute_file_hash(content)
        hash2 = phase._compute_file_hash(content)

        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

        # Different content should produce different hash
        different_content = '{"test": "other"}'
        hash3 = phase._compute_file_hash(different_content)
        assert hash1 != hash3


# Simple test runner if pytest not available
if __name__ == "__main__":
    test_class = TestEntityPhase()
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
