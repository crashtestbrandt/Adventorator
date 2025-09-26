"""Tests for entity import metrics (STORY-CDA-IMPORT-002B)."""

import json
import tempfile
from pathlib import Path

from Adventorator.importer import EntityCollisionError, EntityPhase
from Adventorator.metrics import get_counter, reset_counters


class TestEntityMetrics:
    """Test entity import metrics and observability."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_counters()

    def test_entities_created_metric(self):
        """Test that importer.entities.created metric is incremented correctly."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create multiple entities
            entities_data = [
                {
                    "stable_id": "01JA6Z7F8NPC00000000000001",
                    "kind": "npc",
                    "name": "Alice",
                    "tags": ["mage"],
                    "affordances": ["cast_spell"],
                },
                {
                    "stable_id": "01JA6Z7F8C0000000000000001",
                    "kind": "location",
                    "name": "Tower",
                    "tags": ["building"],
                    "affordances": ["enter"],
                },
            ]

            for i, entity_data in enumerate(entities_data):
                entity_file = entities_dir / f"entity_{i}.json"
                with open(entity_file, "w", encoding="utf-8") as f:
                    json.dump(entity_data, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            # Parse entities
            entities = phase.parse_and_validate_entities(package_root, manifest)

            # Verify metric incremented correctly
            assert len(entities) == 2
            assert get_counter("importer.entities.created") == 2

    def test_entities_skipped_idempotent_metric(self):
        """Test that importer.entities.skipped_idempotent metric is incremented for duplicates."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create identical entities (same stable_id and content)
            entity_data = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada",
                "tags": ["librarian"],
                "affordances": ["greet"],
            }

            # Write same entity to multiple files
            for i in range(3):
                entity_file = entities_dir / f"entity_{i}.json"
                with open(entity_file, "w", encoding="utf-8") as f:
                    json.dump(entity_data, f, separators=(",", ":"))  # Consistent formatting

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            # Parse entities
            entities = phase.parse_and_validate_entities(package_root, manifest)

            # Verify only one entity returned and metrics correct
            assert len(entities) == 1
            assert get_counter("importer.entities.created") == 1
            assert get_counter("importer.entities.skipped_idempotent") == 2  # 2 duplicates skipped

    def test_collision_metric(self):
        """Test that importer.collision metric is incremented for hash mismatches."""
        phase = EntityPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            # Create entities with same stable_id but different content
            entity1 = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada",
                "tags": ["librarian"],
                "affordances": ["greet"],
            }

            entity2 = {
                "stable_id": "01JA6Z7F8NPC00000000000000",
                "kind": "npc",
                "name": "Ada the Great",  # Different content
                "tags": ["librarian"],
                "affordances": ["greet"],
            }

            with open(entities_dir / "entity1.json", "w", encoding="utf-8") as f:
                json.dump(entity1, f)
            with open(entities_dir / "entity2.json", "w", encoding="utf-8") as f:
                json.dump(entity2, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}

            # Should raise collision error and increment metric
            try:
                phase.parse_and_validate_entities(package_root, manifest)
                raise AssertionError("Should have raised EntityCollisionError")
            except EntityCollisionError:
                pass

            # Verify collision metric incremented
            assert get_counter("importer.collision") == 1
            assert get_counter("importer.entities.created") == 0  # No entities created

    def test_multiple_phases_metrics_accumulate(self):
        """Test that metrics accumulate across multiple parsing phases."""
        phase = EntityPhase(features_importer_enabled=True)

        # First phase: parse 2 entities
        with tempfile.TemporaryDirectory() as temp_dir1:
            package_root = Path(temp_dir1)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            for i in range(2):
                entity_data = {
                    "stable_id": f"01JA6Z7F8NPC0000000000000{i}",
                    "kind": "npc",
                    "name": f"Entity {i}",
                    "tags": ["test"],
                    "affordances": ["greet"],
                }
                entity_file = entities_dir / f"entity_{i}.json"
                with open(entity_file, "w", encoding="utf-8") as f:
                    json.dump(entity_data, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}
            phase.parse_and_validate_entities(package_root, manifest)

        # Verify first phase metrics
        assert get_counter("importer.entities.created") == 2

        # Second phase: parse 1 entity
        with tempfile.TemporaryDirectory() as temp_dir2:
            package_root = Path(temp_dir2)
            entities_dir = package_root / "entities"
            entities_dir.mkdir()

            entity_data = {
                "stable_id": "01JA6Z7F8ITM00000000000000",
                "kind": "item",
                "name": "Magic Sword",
                "tags": ["weapon"],
                "affordances": ["wield"],
            }
            entity_file = entities_dir / "sword.json"
            with open(entity_file, "w", encoding="utf-8") as f:
                json.dump(entity_data, f)

            manifest = {"package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ"}
            phase.parse_and_validate_entities(package_root, manifest)

        # Verify metrics accumulated
        assert get_counter("importer.entities.created") == 3  # 2 + 1


if __name__ == "__main__":
    test_class = TestEntityMetrics()
    test_methods = [method for method in dir(test_class) if method.startswith("test_")]

    passed = 0
    failed = 0

    for method_name in test_methods:
        try:
            test_class.setup_method()  # Reset metrics
            method = getattr(test_class, method_name)
            method()
            print(f"✓ {method_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {method_name}: {e}")
            failed += 1

    print(f"\nMetrics Tests: {passed} passed, {failed} failed")
