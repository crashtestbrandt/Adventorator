"""Tests for ontology ingestion (STORY-CDA-IMPORT-002D)."""

import json
import tempfile
from pathlib import Path

import pytest

from Adventorator.importer import OntologyPhase, OntologyValidationError


class TestOntologyIngestion:
    """Test ontology tags and affordances parsing and validation."""

    def test_parse_valid_ontology(self):
        """Test parsing of valid ontology file with tags and affordances."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create valid ontology file
            ontology_data = {
                "version": "1.0.0",
                "source": {
                    "package": "test-campaign",
                    "revision": "2025-02-21",
                    "provenance": {
                        "manifest_path": "packages/test/package.manifest.json",
                        "sha256": "1111111111111111111111111111111111111111111111111111111111111111"
                    }
                },
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike", "swing"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
                        },
                        "metadata": {
                            "description": "Direct offensive action.",
                            "canonical_affordance": "affordance.attack.allowed"
                        }
                    }
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
                            "ruleset_version": "v2.7"
                        },
                        "metadata": {
                            "effect": "Allows melee attack rolls",
                            "improbability_drive": {
                                "intent_frame": "attack",
                                "confidence": 0.97
                            }
                        }
                    }
                ]
            }

            ontology_file = ontology_dir / "test.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            assert len(tags) == 1
            assert len(affordances) == 1
            
            # Verify tag was normalized properly
            tag = tags[0]
            assert tag["tag_id"] == "action.attack"
            assert tag["category"] == "action"
            assert tag["slug"] == "attack"
            assert tag["synonyms"] == ["attack", "strike", "swing"]  # Normalized to lowercase
            
            # Verify affordance was normalized properly
            affordance = affordances[0]
            assert affordance["affordance_id"] == "affordance.attack.allowed"
            assert affordance["category"] == "combat"
            assert affordance["slug"] == "attack-allowed"

    def test_no_ontology_directory(self):
        """Test handling of packages without ontology directory."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            assert len(tags) == 0
            assert len(affordances) == 0

    def test_duplicate_identical_tags(self):
        """Test idempotent handling of duplicate identical tags."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create ontology with duplicate identical tags
            ontology_data = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
                        }
                    },
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
                        }
                    }
                ],
                "affordances": []
            }

            ontology_file = ontology_dir / "duplicate.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}
            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            # Should get 2 tags from parser (before duplicate check)
            assert len(tags) == 2
            assert len(affordances) == 0

            # Check duplicate handling
            tag_skips, affordance_skips = phase.check_for_duplicates_and_conflicts(
                tags, affordances, "test-package-001"
            )
            assert tag_skips == 1  # One duplicate should be skipped
            assert affordance_skips == 0

    def test_conflicting_tags_fail(self):
        """Test that conflicting tag definitions cause hard failure."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create ontology with conflicting tags (different synonyms)
            ontology_data = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
                        }
                    },
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike", "power attack"],  # Different synonyms
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.8",  # Different version
                            "requires_feature": None
                        }
                    }
                ],
                "affordances": []
            }

            ontology_file = ontology_dir / "conflict.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}
            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            # Should get 2 tags from parser (before conflict check)
            assert len(tags) == 2
            assert len(affordances) == 0

            # Check that conflicts cause failure
            with pytest.raises(OntologyValidationError) as exc_info:
                phase.check_for_duplicates_and_conflicts(tags, affordances, "test-package-001")
            
            assert "Conflicting tag definition" in str(exc_info.value)
            assert "action.attack" in str(exc_info.value)

    def test_deterministic_ordering(self):
        """Test that ontology processing maintains deterministic ordering."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create multiple ontology files with different filename orders
            ontology_data_1 = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.cast_spell",
                        "category": "action",
                        "slug": "cast-spell",
                        "display_name": "Cast Spell",
                        "synonyms": ["cast", "spell"],
                        "audience": ["player"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": "magic-enabled"
                        }
                    }
                ],
                "affordances": []
            }

            ontology_data_2 = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        "synonyms": ["attack", "strike"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
                        }
                    }
                ],
                "affordances": []
            }

            # Write files in non-alphabetical order
            (ontology_dir / "z_magic.json").write_text(json.dumps(ontology_data_1, indent=2))
            (ontology_dir / "a_combat.json").write_text(json.dumps(ontology_data_2, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}
            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            assert len(tags) == 2
            # Should be ordered by filename (a_combat.json before z_magic.json)
            assert tags[0]["tag_id"] == "action.attack"  # From a_combat.json
            assert tags[1]["tag_id"] == "action.cast_spell"  # From z_magic.json

    def test_seed_event_emission(self):
        """Test that seed events are emitted with proper payloads."""
        phase = OntologyPhase(features_importer_enabled=True)

        tags = [
            {
                "tag_id": "action.attack",
                "category": "action",
                "slug": "attack",
                "display_name": "Attack",
                "synonyms": ["attack", "strike"],
                "audience": ["player", "gm"],
                "gating": {
                    "ruleset_version": "v2.7",
                    "requires_feature": None
                },
                "metadata": {
                    "description": "Direct offensive action."
                }
            }
        ]

        affordances = [
            {
                "affordance_id": "affordance.attack.allowed",
                "category": "combat",
                "slug": "attack-allowed",
                "applies_to": ["tag:action.attack"],
                "gating": {
                    "audience": "player",
                    "requires_feature": None,
                    "ruleset_version": "v2.7"
                }
            }
        ]

        manifest = {"package_id": "test-package-001", "version": "1.0.0"}
        source_paths = {
            "action.attack#action": "ontology/combat.json",
            "affordance.attack.allowed#combat": "ontology/combat.json"
        }

        event_counts = phase.emit_seed_events(tags, affordances, manifest, source_paths)

        assert event_counts["tag_events"] == 1
        assert event_counts["affordance_events"] == 1

    def test_missing_required_fields(self):
        """Test validation failure for missing required fields."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create ontology with missing required field
            ontology_data = {
                "version": "1.0.0",
                "tags": [
                    {
                        "tag_id": "action.attack",
                        "category": "action",
                        "slug": "attack",
                        "display_name": "Attack",
                        # Missing synonyms, audience, gating
                    }
                ],
                "affordances": []
            }

            ontology_file = ontology_dir / "invalid.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            with pytest.raises(OntologyValidationError) as exc_info:
                phase.parse_and_validate_ontology(package_root, manifest)
            
            assert "Missing required field" in str(exc_info.value)

    def test_feature_flag_disabled(self):
        """Test that disabled importer feature flag raises error."""
        phase = OntologyPhase(features_importer_enabled=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            with pytest.raises(Exception) as exc_info:
                phase.parse_and_validate_ontology(package_root, manifest)
            
            assert "feature flag is disabled" in str(exc_info.value)