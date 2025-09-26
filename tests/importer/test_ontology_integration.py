"""Integration tests for ontology ingestion (STORY-CDA-IMPORT-002D)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from Adventorator.importer import OntologyPhase


class TestOntologyIntegration:
    """Test complete ontology ingestion workflow integration."""

    def test_complete_ontology_ingestion_workflow(self):
        """Test full workflow from parsing to event emission."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create comprehensive ontology fixture
            ontology_data = {
                "version": "1.0.0",
                "source": {
                    "package": "test-campaign",
                    "revision": "2025-02-21",
                    "provenance": {
                        "manifest_path": "packages/test/package.manifest.json",
                        "sha256": "aaaa111111111111111111111111111111111111111111111111111111111111",
                    },
                },
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike", "swing"],
                        "audience": ["player", "gm"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                        "metadata": {
                            "description": "Direct offensive action.",
                            "canonical_affordance": "affordance.attack.allowed",
                        },
                    },
                    {
                        "tag_id": "action.cast_spell",
                        "category": "action",
                        "slug": "cast-spell",
                        "display_name": "Cast Spell",
                        "synonyms": ["cast", "spell", "cast spell"],
                        "audience": ["player"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": "magic-enabled"},
                    },
                    {
                        "tag_id": "target.door",
                        "category": "target",
                        "slug": "door",
                        "display_name": "Door",
                        "synonyms": ["door", "gate"],
                        "audience": ["player", "gm"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                        "metadata": {
                            "description": "Door targets within the dungeon map.",
                            "canonical_affordance": "affordance.environment.openable",
                        },
                    },
                ],
                "affordances": [
                    {
                        "affordance_id": "affordance.attack.allowed",
                        "category": "combat",
                        "slug": "attack-allowed",
                        "applies_to": ["tag:action.attack"],
                        "gating": {
                            "audience": "player",
                            "requires_feature": None,
                            "ruleset_version": "v2.7",
                        },
                        "metadata": {
                            "effect": "Allows melee attack rolls",
                            "improbability_drive": {"intent_frame": "attack", "confidence": 97},
                        },
                    },
                    {
                        "affordance_id": "affordance.environment.openable",
                        "category": "environment",
                        "slug": "environment-openable",
                        "applies_to": ["tag:target.door"],
                        "gating": {
                            "audience": "gm",
                            "requires_feature": None,
                            "ruleset_version": "v2.7",
                        },
                    },
                ],
            }

            ontology_file = ontology_dir / "complete.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            # Step 1: Parse and validate
            tags, affordances, import_log_entries = phase.parse_and_validate_ontology(
                package_root, manifest
            )

            assert len(tags) == 3
            assert len(affordances) == 2
            assert len(import_log_entries) == 5  # 3 tags + 2 affordances

            # Verify tags are normalized
            attack_tag = next(t for t in tags if t["tag_id"] == "action.attack")
            # Normalized to lowercase
            assert attack_tag["synonyms"] == ["attack", "strike", "swing"]
            assert attack_tag["slug"] == "attack"

            spell_tag = next(t for t in tags if t["tag_id"] == "action.cast_spell")
            assert spell_tag["slug"] == "cast-spell"  # Normalized with hyphens

            # Step 2: Duplicate checking is automatic now - no separate step needed

            # Step 3: Emit seed events (no longer needs source_paths parameter)
            event_counts = phase.emit_seed_events(tags, affordances, manifest)

            assert event_counts["tag_events"] == 3
            assert event_counts["affordance_events"] == 2

    @patch("Adventorator.importer.inc_counter")
    @patch("Adventorator.importer.emit_structured_log")
    def test_complete_workflow_with_duplicates_and_metrics(
        self, mock_emit_log: MagicMock, mock_inc_counter: MagicMock
    ):
        """Test complete workflow including duplicate handling and metrics."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create two files with some duplicate content
            ontology_data_1 = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    }
                ],
                "affordances": [],
            }

            ontology_data_2 = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",  # Identical duplicate
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    },
                    {
                        "tag_id": "action.move",  # Unique tag
                        "category": "action",
                        "slug": "move",
                        "display_name": "Move",
                        "synonyms": ["move", "go", "walk"],
                        "audience": ["player", "gm"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    },
                ],
                "affordances": [],
            }

            # Write files in alphabetical order for deterministic processing
            (ontology_dir / "a_combat.json").write_text(json.dumps(ontology_data_1, indent=2))
            (ontology_dir / "b_movement.json").write_text(json.dumps(ontology_data_2, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            # Parse ontology (duplicates handled automatically)
            tags, affordances, import_log_entries = phase.parse_and_validate_ontology(
                package_root, manifest
            )

            # Should get unique tags only (duplicates automatically removed)
            assert len(tags) == 2  # attack (unique), move (unique)
            assert len(affordances) == 0
            assert len(import_log_entries) == 2  # Only unique items logged

            # Verify tags were processed correctly
            tag_ids = [tag["tag_id"] for tag in tags]
            assert "action.attack" in tag_ids
            assert "action.move" in tag_ids

            # Verify metrics were called (parsing metrics called before duplicate removal)
            mock_inc_counter.assert_any_call(
                "importer.tags.parsed",
                value=3,  # Original count before duplicate removal
                package_id="test-package-001",
            )
            mock_inc_counter.assert_any_call(
                "importer.affordances.parsed", value=0, package_id="test-package-001"
            )
            mock_inc_counter.assert_any_call(
                "importer.tags.skipped_idempotent", value=1, package_id="test-package-001"
            )

    def test_deterministic_ordering_across_files(self):
        """Test that processing multiple ontology files maintains deterministic ordering."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create files in non-alphabetical order
            file_z = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.zebra",
                        "category": "action",
                        "slug": "zebra",
                        "display_name": "Zebra Action",
                        "synonyms": ["zebra"],
                        "audience": ["player"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    }
                ],
                "affordances": [],
            }

            file_a = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.apple",
                        "category": "action",
                        "slug": "apple",
                        "display_name": "Apple Action",
                        "synonyms": ["apple"],
                        "audience": ["player"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    }
                ],
                "affordances": [],
            }

            file_m = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.middle",
                        "category": "action",
                        "slug": "middle",
                        "display_name": "Middle Action",
                        "synonyms": ["middle"],
                        "audience": ["player"],
                        "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                    }
                ],
                "affordances": [],
            }

            # Write files in reverse alphabetical order
            (ontology_dir / "z_zebra.json").write_text(json.dumps(file_z))
            (ontology_dir / "m_middle.json").write_text(json.dumps(file_m))
            (ontology_dir / "a_apple.json").write_text(json.dumps(file_a))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            # Parse twice and compare results
            tags_1, _, _ = phase.parse_and_validate_ontology(package_root, manifest)
            tags_2, _, _ = phase.parse_and_validate_ontology(package_root, manifest)

            assert len(tags_1) == 3
            assert len(tags_2) == 3

            # Should be in alphabetical filename order despite creation order
            assert tags_1[0]["tag_id"] == "action.apple"  # From a_apple.json
            assert tags_1[1]["tag_id"] == "action.middle"  # From m_middle.json
            assert tags_1[2]["tag_id"] == "action.zebra"  # From z_zebra.json

            # Both runs should produce identical ordering
            tag_ids_1 = [t["tag_id"] for t in tags_1]
            tag_ids_2 = [t["tag_id"] for t in tags_2]
            assert tag_ids_1 == tag_ids_2

    def test_seed_event_deterministic_ordering(self):
        """Test that seed events are emitted in deterministic order."""
        phase = OntologyPhase(features_importer_enabled=True)

        # Create mixed category tags
        tags = [
            {
                "tag_id": "target.zebra",
                "category": "target",
                "slug": "zebra",
                "display_name": "Zebra",
                "synonyms": ["zebra"],
                "audience": ["player"],
                "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                "provenance": {
                    "package_id": "test-package-001",
                    "source_path": "ontology/test.json",
                    "file_hash": "z" * 64,
                },
            },
            {
                "tag_id": "action.apple",
                "category": "action",
                "slug": "apple",
                "display_name": "Apple",
                "synonyms": ["apple"],
                "audience": ["player"],
                "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                "provenance": {
                    "package_id": "test-package-001",
                    "source_path": "ontology/test.json",
                    "file_hash": "a" * 64,
                },
            },
            {
                "tag_id": "target.alpha",
                "category": "target",
                "slug": "alpha",
                "display_name": "Alpha",
                "synonyms": ["alpha"],
                "audience": ["player"],
                "gating": {"ruleset_version": "v2.7", "requires_feature": None},
                "provenance": {
                    "package_id": "test-package-001",
                    "source_path": "ontology/test.json",
                    "file_hash": "a" * 64,
                },
            },
        ]

        affordances = []

        manifest = {"package_id": "test-package-001", "version": "1.0.0"}

        with patch("Adventorator.importer.emit_structured_log") as mock_emit:
            phase.emit_seed_events(tags, affordances, manifest)

            # Get all the seed event calls
            seed_calls = [
                call for call in mock_emit.call_args_list if call[0][0] == "seed_event_emitted"
            ]

            assert len(seed_calls) == 3

            # Extract tag_id from each call payload
            emitted_tag_ids = []
            for call in seed_calls:
                event_payload = call[1]["event_payload"]
                emitted_tag_ids.append(event_payload["tag_id"])

            # Should be sorted by (category, tag_id)
            expected_order = ["action.apple", "target.alpha", "target.zebra"]
            assert emitted_tag_ids == expected_order
