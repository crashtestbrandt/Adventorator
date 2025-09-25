"""Tests for ontology event schema validation (STORY-CDA-IMPORT-002D)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from Adventorator.importer import OntologyPhase


class TestOntologyEventValidation:
    """Test that emitted seed events comply with their JSON schemas."""

    def test_tag_registered_event_schema_compliance(self):
        """Test that tag registered events match their schema."""
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
                    "description": "Direct offensive action.",
                    "canonical_affordance": "affordance.attack.allowed"
                },
                "provenance": {
                    "package_id": "test-package-001",
                    "source_path": "ontology/combat.json",
                    "file_hash": "1234567890abcdef" * 4  # 64-char hex
                }
            }
        ]
        
        manifest = {"package_id": "test-package-001", "version": "1.0.0"}
        
        # Capture emitted event payloads
        emitted_payloads = []
        
        def capture_emit(event_name, **kwargs):
            if event_name == "seed_event_emitted":
                emitted_payloads.append(kwargs.get("event_payload"))
        
        with patch("Adventorator.importer.emit_structured_log", side_effect=capture_emit):
            phase.emit_seed_events(tags, [], manifest)
        
        assert len(emitted_payloads) == 1
        payload = emitted_payloads[0]
        
        # Validate required fields are present
        required_fields = [
            "tag_id", "category", "version", "slug", "display_name", 
            "synonyms", "audience", "gating", "provenance"
        ]
        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"
        
        # Validate field types and constraints
        assert isinstance(payload["tag_id"], str)
        assert payload["tag_id"] == "action.attack"
        assert isinstance(payload["category"], str)
        assert payload["category"] in ["action", "target", "modifier", "trait"]
        assert isinstance(payload["synonyms"], list)
        assert all(isinstance(syn, str) for syn in payload["synonyms"])
        assert isinstance(payload["audience"], list)
        assert all(aud in ["player", "gm", "system"] for aud in payload["audience"])
        
        # Validate provenance structure
        provenance = payload["provenance"]
        assert isinstance(provenance, dict)
        assert "package_id" in provenance
        assert "source_path" in provenance
        assert "file_hash" in provenance
        assert len(provenance["file_hash"]) == 64  # SHA-256 hex string

    def test_affordance_registered_event_schema_compliance(self):
        """Test that affordance registered events match their schema."""
        phase = OntologyPhase(features_importer_enabled=True)
        
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
                },
                "metadata": {
                    "effect": "Allows melee attack rolls",
                    "improbability_drive": {
                        "intent_frame": "attack",
                        "confidence": 97
                    }
                },
                "provenance": {
                    "package_id": "test-package-001",
                    "source_path": "ontology/combat.json",
                    "file_hash": "abcdef1234567890" * 4  # 64-char hex
                }
            }
        ]
        
        manifest = {"package_id": "test-package-001", "version": "1.0.0"}
        
        # Capture emitted event payloads
        emitted_payloads = []
        
        def capture_emit(event_name, **kwargs):
            if event_name == "seed_event_emitted":
                emitted_payloads.append(kwargs.get("event_payload"))
        
        with patch("Adventorator.importer.emit_structured_log", side_effect=capture_emit):
            phase.emit_seed_events([], affordances, manifest)
        
        assert len(emitted_payloads) == 1
        payload = emitted_payloads[0]
        
        # Validate required fields are present
        required_fields = [
            "affordance_id", "category", "version", "slug", 
            "applies_to", "gating", "provenance"
        ]
        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"
        
        # Validate field types and constraints
        assert isinstance(payload["affordance_id"], str)
        assert payload["affordance_id"].startswith("affordance.")
        assert isinstance(payload["category"], str)
        assert payload["category"] in ["combat", "environment", "social", "magic", "exploration"]
        assert isinstance(payload["applies_to"], list)
        assert all(isinstance(ref, str) for ref in payload["applies_to"])
        
        # Validate gating structure
        gating = payload["gating"]
        assert isinstance(gating, dict)
        assert "audience" in gating
        assert gating["audience"] in ["player", "gm", "system"]
        assert "ruleset_version" in gating
        
        # Validate provenance structure
        provenance = payload["provenance"]
        assert isinstance(provenance, dict)
        assert len(provenance["file_hash"]) == 64  # SHA-256 hex string

    def validate_against_json_schema(self):
        """Test validation against actual JSON schema files (if jsonschema available)."""
        try:
            import jsonschema
        except ImportError:
            # Skip if jsonschema not available
            return
            
        phase = OntologyPhase(features_importer_enabled=True)
        
        # Load schemas
        tag_schema_path = Path("contracts/events/seed/tag-registered.v1.json")
        affordance_schema_path = Path("contracts/events/seed/affordance-registered.v1.json")
        
        if not (tag_schema_path.exists() and affordance_schema_path.exists()):
            return  # Skip if schema files not found
            
        with open(tag_schema_path) as f:
            tag_schema = json.load(f)
        with open(affordance_schema_path) as f:
            affordance_schema = json.load(f)
            
        # Test data
        tags = [{
            "tag_id": "action.test",
            "category": "action", 
            "slug": "test",
            "display_name": "Test",
            "synonyms": ["test"],
            "audience": ["player"],
            "gating": {"ruleset_version": "v2.7", "requires_feature": None},
            "provenance": {
                "package_id": "test-001",
                "source_path": "ontology/test.json", 
                "file_hash": "a" * 64
            }
        }]
        
        affordances = [{
            "affordance_id": "affordance.test.allowed",
            "category": "combat",
            "slug": "test-allowed", 
            "applies_to": ["tag:action.test"],
            "gating": {"audience": "player", "ruleset_version": "v2.7", "requires_feature": None},
            "provenance": {
                "package_id": "test-001",
                "source_path": "ontology/test.json",
                "file_hash": "b" * 64
            }
        }]
        
        manifest = {"package_id": "test-001", "version": "1.0.0"}
        
        # Capture and validate events
        emitted_payloads = []
        def capture_emit(event_name, **kwargs):
            if event_name == "seed_event_emitted":
                emitted_payloads.append(kwargs.get("event_payload"))
        
        with patch("Adventorator.importer.emit_structured_log", side_effect=capture_emit):
            phase.emit_seed_events(tags, affordances, manifest)
        
        # Validate tag event against schema
        tag_payload = emitted_payloads[0] 
        jsonschema.validate(tag_payload, tag_schema)
        
        # Validate affordance event against schema
        affordance_payload = emitted_payloads[1]
        jsonschema.validate(affordance_payload, affordance_schema)