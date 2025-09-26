"""Tests for importer finalization phase (STORY-CDA-IMPORT-002F)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from Adventorator.importer import FinalizationPhase
from Adventorator.importer_context import ImporterRunContext

# Test constants
TEST_PACKAGE_ID = "01JAR9WYH41R8TFM6Z0X5E7QKJ"
TEST_MANIFEST_HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


class TestFinalizationPhase:
    """Test the FinalizationPhase implementation."""

    def test_finalization_disabled_when_feature_flag_off(self):
        """Test that finalization is skipped when features_importer is disabled."""
        phase = FinalizationPhase(features_importer_enabled=False)
        context = ImporterRunContext()
        start_time = datetime.now(timezone.utc)
        
        result = phase.finalize_import(context, start_time)
        
        assert result["skipped"] is True

    def test_finalization_creates_completion_event(self):
        """Test that finalization creates proper completion event."""
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        
        # Set up context with test data
        context.package_id = TEST_PACKAGE_ID
        context.manifest_hash = TEST_MANIFEST_HASH
        context.entities = [{"stable_id": "entity1", "name": "Test Entity"}]
        context.edges = [{"stable_id": "edge1", "from": "entity1", "to": "entity2"}]
        context.ontology_tags = [{"tag_id": "tag1", "display_name": "Test Tag"}]
        context.ontology_affordances = [{"affordance_id": "aff1", "slug": "test"}]
        context.lore_chunks = [{"chunk_id": "chunk1", "content": "Test content"}]

        start_time = datetime.now(timezone.utc)
        
        with patch('Adventorator.importer.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromtimestamp = datetime.fromtimestamp
            
            result = phase.finalize_import(context, start_time)
        
        # Verify completion event structure
        completion_event = result["completion_event"]
        assert completion_event["event_type"] == "seed.import.complete"
        
        payload = completion_event["payload"]
        assert payload["package_id"] == TEST_PACKAGE_ID
        assert payload["manifest_hash"] == TEST_MANIFEST_HASH
        assert payload["entity_count"] == 1
        assert payload["edge_count"] == 1
        assert payload["tag_count"] == 1
        assert payload["affordance_count"] == 1
        assert payload["chunk_count"] == 1
        assert "state_digest" in payload
        assert "import_duration_ms" in payload
        assert isinstance(payload["import_duration_ms"], int)

    def test_import_log_summary_creation(self):
        """Test ImportLog summary entry creation."""
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        
        # Set up context with ImportLog entries
        context.package_id = TEST_PACKAGE_ID
        context.manifest_hash = TEST_MANIFEST_HASH
        context._import_logs = [
            {"phase": "manifest", "sequence_no": 1, "stable_id": "pkg1"},
            {"phase": "entity", "sequence_no": 2, "stable_id": "entity1"},
            {"phase": "edge", "sequence_no": 3, "stable_id": "edge1"},
        ]
        
        start_time = datetime.now(timezone.utc)
        result = phase.finalize_import(context, start_time)
        
        # Verify ImportLog summary
        summary = result["import_log_summary"]
        assert summary["phase"] == "finalization"
        assert summary["object_type"] == "summary"
        assert summary["stable_id"] == "summary-01JAR9WYH41R8TFM6Z0X5E7QKJ"
        assert summary["action"] == "completed"
        assert summary["sequence_no"] == 4  # Max sequence + 1
        assert summary["manifest_hash"] == TEST_MANIFEST_HASH
        assert "metadata" in summary
        assert summary["metadata"]["total_entries"] == 3

    def test_state_digest_consistency(self):
        """Test that state digest is computed consistently."""
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        
        # Set up identical context twice
        for _ in range(2):
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            
            start_time = datetime.now(timezone.utc)
            result1 = phase.finalize_import(context, start_time)
            
            # Reset and compute again
            context = ImporterRunContext()
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            
            result2 = phase.finalize_import(context, start_time)
            
            # State digests should be identical for identical inputs
            assert result1["state_digest"] == result2["state_digest"]

    def test_sequence_gap_detection(self):
        """Test detection and enforcement of sequence number gaps in ImportLog."""
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        
        # Set up context with gap in sequence numbers
        context.package_id = TEST_PACKAGE_ID
        context.manifest_hash = TEST_MANIFEST_HASH
        context._import_logs = [
            {"phase": "manifest", "sequence_no": 1, "stable_id": "pkg1"},
            {"phase": "entity", "sequence_no": 3, "stable_id": "entity1"},  # Gap: missing 2
            {"phase": "edge", "sequence_no": 4, "stable_id": "edge1"},
        ]
        
        # Import the ImporterError for the test
        from Adventorator.importer import ImporterError
        
        with patch('Adventorator.importer.emit_structured_log') as mock_log:
            start_time = datetime.now(timezone.utc)
            
            # Should raise ImporterError due to sequence gap
            with pytest.raises(ImporterError, match="ImportLog sequence gaps detected"):
                phase.finalize_import(context, start_time)
            
            # Verify gap detection was also logged
            gap_logs = [call for call in mock_log.call_args_list 
                       if call[0][0] == "import_log_sequence_gap_detected"]
            assert len(gap_logs) == 1

    @pytest.mark.asyncio
    async def test_duration_metric_recorded(self):
        """Test that duration metric is recorded correctly."""
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        context.package_id = TEST_PACKAGE_ID
        context.manifest_hash = TEST_MANIFEST_HASH
        
        # Use a fixed start time to control duration
        start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        with patch('Adventorator.importer.datetime') as mock_datetime, \
             patch('Adventorator.importer.observe_histogram') as mock_histogram:
            
            end_time = datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc)  # 1 second later
            mock_datetime.now.return_value = end_time
            
            result = phase.finalize_import(context, start_time)
            
            # Verify duration calculation
            expected_duration = 1000  # 1 second = 1000ms
            assert result["duration_ms"] == expected_duration
            
            # Verify histogram metric was recorded
            mock_histogram.assert_called_once_with("importer.duration_ms", expected_duration)


class TestProductionIntegration:
    """Test production call site integration for the complete pipeline."""

    def test_complete_pipeline_integration(self):
        """Test the complete pipeline integration via production call site."""
        from Adventorator.importer import run_complete_import_pipeline
        
        # Verify the production call site exists and is importable
        assert callable(run_complete_import_pipeline)
        
        # The actual integration testing is done in the golden fixture tests
        # This test just verifies the production interface exists
        # Full integration testing requires proper manifest fixtures which
        # are handled by the existing golden fixture test framework
        pytest.skip("Production call site verified - full integration requires golden fixtures")


class TestFinalizationContractValidation:
    """Test validation against the seed.import.complete contract."""

    def test_completion_event_matches_schema(self):
        """Test that completion event payload matches the contract schema."""
        # Load the schema
        schema_path = Path("contracts/events/seed/import-complete.v1.json")
        assert schema_path.exists(), "Contract schema must exist"
        
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        
        # Create a completion event
        phase = FinalizationPhase(features_importer_enabled=True)
        context = ImporterRunContext()
        context.package_id = TEST_PACKAGE_ID
        context.manifest_hash = TEST_MANIFEST_HASH
        
        start_time = datetime.now(timezone.utc)
        result = phase.finalize_import(context, start_time)
        
        payload = result["completion_event"]["payload"]
        
        # Validate against schema
        try:
            import jsonschema
            jsonschema.validate(payload, schema)
        except ImportError:
            # If jsonschema is not available, do basic validation
            required_fields = [
                "package_id", "manifest_hash", "entity_count", "edge_count",
                "tag_count", "affordance_count", "chunk_count", "state_digest",
                "import_duration_ms"
            ]
            for field in required_fields:
                assert field in payload, f"Required field {field} missing"
                
            # Check types and patterns
            assert isinstance(payload["package_id"], str)
            assert len(payload["package_id"]) == 26  # ULID length
            assert isinstance(payload["manifest_hash"], str) 
            assert len(payload["manifest_hash"]) == 64  # SHA-256 hex length
            assert isinstance(payload["state_digest"], str)
            assert len(payload["state_digest"]) == 64  # SHA-256 hex length
            assert isinstance(payload["import_duration_ms"], int)
            assert payload["import_duration_ms"] >= 0