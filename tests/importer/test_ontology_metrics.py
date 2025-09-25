"""Tests for ontology metrics (STORY-CDA-IMPORT-002D)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from Adventorator.importer import OntologyPhase


class TestOntologyMetrics:
    """Test metrics emission for ontology ingestion."""

    @patch("Adventorator.importer.inc_counter")
    def test_parsed_metrics(self, mock_inc_counter: MagicMock):
        """Test that parsing metrics are emitted correctly."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            ontology_dir = package_root / "ontology"
            ontology_dir.mkdir()

            # Create ontology with 2 tags and 1 affordance
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
                        "tag_id": "target.door",
                        "category": "target",
                        "slug": "door",
                        "display_name": "Door",
                        "synonyms": ["door", "gate"],
                        "audience": ["player", "gm"],
                        "gating": {
                            "ruleset_version": "v2.7",
                            "requires_feature": None
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
                        }
                    }
                ]
            }

            ontology_file = ontology_dir / "test.json"
            ontology_file.write_text(json.dumps(ontology_data, indent=2))

            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            # Verify metrics were called
            mock_inc_counter.assert_any_call(
                "importer.tags.parsed", 
                value=2, 
                package_id="test-package-001"
            )
            mock_inc_counter.assert_any_call(
                "importer.affordances.parsed", 
                value=1, 
                package_id="test-package-001"
            )

    @patch("Adventorator.importer.inc_counter")
    def test_idempotent_skip_metrics(self, mock_inc_counter: MagicMock):
        """Test that idempotent skip metrics are emitted correctly."""
        phase = OntologyPhase(features_importer_enabled=True)

        # Create duplicate tags
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
        ]

        affordances = []

        tag_skips, affordance_skips = phase.check_for_duplicates_and_conflicts(
            tags, affordances, "test-package-001"
        )

        assert tag_skips == 1
        assert affordance_skips == 0

        # Verify idempotent skip metric was called
        mock_inc_counter.assert_any_call(
            "importer.tags.skipped_idempotent", 
            value=1, 
            package_id="test-package-001"
        )

    @patch("Adventorator.importer.inc_counter")
    def test_registration_metrics(self, mock_inc_counter: MagicMock):
        """Test that registration metrics are emitted correctly."""
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

        # Verify registration metrics were called
        mock_inc_counter.assert_any_call(
            "importer.tags.registered", 
            value=1, 
            package_id="test-package-001"
        )
        mock_inc_counter.assert_any_call(
            "importer.affordances.registered", 
            value=1, 
            package_id="test-package-001"
        )

    @patch("Adventorator.importer.inc_counter")
    def test_no_ontology_metrics(self, mock_inc_counter: MagicMock):
        """Test that zero metrics are emitted when no ontology exists."""
        phase = OntologyPhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = {"package_id": "test-package-001", "version": "1.0.0"}

            tags, affordances = phase.parse_and_validate_ontology(package_root, manifest)

            assert len(tags) == 0
            assert len(affordances) == 0

            # Verify zero metrics were called
            mock_inc_counter.assert_any_call(
                "importer.tags.parsed", 
                value=0, 
                package_id="test-package-001"
            )
            mock_inc_counter.assert_any_call(
                "importer.affordances.parsed", 
                value=0, 
                package_id="test-package-001"
            )