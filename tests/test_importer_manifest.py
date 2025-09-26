"""Tests for importer manifest phase (STORY-CDA-IMPORT-002A)."""

from pathlib import Path

import pytest

from Adventorator import models
from Adventorator.db import session_scope
from Adventorator.importer import (
    ImporterError,
    ManifestPhase,
    create_manifest_phase,
    validate_event_payload_schema,
)


class TestManifestPhase:
    """Test manifest validation phase."""

    def test_create_manifest_phase_feature_flag_enabled(self):
        """Test creating manifest phase with feature flag enabled."""
        phase = create_manifest_phase(features_importer=True)
        assert phase.features_importer_enabled is True

    def test_create_manifest_phase_feature_flag_disabled(self):
        """Test creating manifest phase with feature flag disabled."""
        phase = create_manifest_phase(features_importer=False)
        assert phase.features_importer_enabled is False

    def test_validate_and_register_feature_flag_disabled(self):
        """Test that validation fails when feature flag is disabled."""
        phase = ManifestPhase(features_importer_enabled=False)
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")

        with pytest.raises(ImporterError, match="Importer feature flag is disabled"):
            phase.validate_and_register(manifest_path)

    def test_validate_and_register_happy_path(self):
        """Test successful manifest validation and registration."""
        phase = ManifestPhase(features_importer_enabled=True)
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")

        result = phase.validate_and_register(manifest_path)

        # Check structure
        assert "manifest" in result
        assert "manifest_hash" in result
        assert "event_payload" in result
        assert "import_log_entry" in result

        # Check manifest data
        manifest = result["manifest"]
        assert manifest["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"
        assert manifest["schema_version"] == 1

        # Check manifest hash
        manifest_hash = result["manifest_hash"]
        assert len(manifest_hash) == 64  # SHA-256 hex

        # Check event payload
        event_payload = result["event_payload"]
        assert event_payload["package_id"] == manifest["package_id"]
        assert event_payload["manifest_hash"] == manifest_hash
        assert event_payload["schema_version"] == manifest["schema_version"]
        assert event_payload["ruleset_version"] == manifest["ruleset_version"]

        # Check import log entry
        log_entry = result["import_log_entry"]
        assert log_entry["phase"] == "manifest"
        assert log_entry["object_type"] == "package"
        assert log_entry["stable_id"] == manifest["package_id"]
        assert log_entry["file_hash"] == manifest_hash
        assert log_entry["action"] == "validated"
        assert "timestamp" in log_entry

    def test_validate_and_register_tampered_fails(self):
        """Test that tampered manifest validation fails."""
        phase = ManifestPhase(features_importer_enabled=True)
        manifest_path = Path("tests/fixtures/import/manifest/tampered/package.manifest.json")

        with pytest.raises(ImporterError, match="Manifest validation failed"):
            phase.validate_and_register(manifest_path)

    @pytest.mark.asyncio
    async def test_emit_seed_event(self):
        """Test synthetic event emission persists to the ledger."""
        phase = ManifestPhase(features_importer_enabled=True)

        event_payload = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "schema_version": 1,
            "ruleset_version": "1.2.3",
        }

        campaign_id = 9001
        async with session_scope() as session:
            session.add(models.Campaign(id=campaign_id, name="Test Campaign"))
            await session.flush()
            event = await phase.emit_seed_event(session, campaign_id, event_payload)

        assert event.type == "seed.manifest.validated"
        assert event.payload == event_payload
        assert event.campaign_id == campaign_id
        assert event.replay_ordinal >= 0
        assert len(event.idempotency_key) == 16

    def test_nonexistent_manifest_file(self):
        """Test handling of nonexistent manifest file."""
        phase = ManifestPhase(features_importer_enabled=True)
        nonexistent_path = Path("/tmp/nonexistent-manifest.json")

        with pytest.raises(ImporterError, match="Manifest validation failed"):
            phase.validate_and_register(nonexistent_path)


class TestEventPayloadValidation:
    """Test event payload schema validation."""

    def test_validate_event_payload_schema_valid(self):
        """Test validation of valid event payload."""
        payload = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "schema_version": 1,
            "ruleset_version": "1.2.3",
        }

        # Should not raise an exception (may skip if jsonschema not available)
        validate_event_payload_schema(payload)

    def test_validate_event_payload_schema_missing_field(self):
        """Test validation fails for missing required field."""
        payload = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            # Missing other required fields
        }

        # This test may pass if jsonschema is not available
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            pytest.skip("jsonschema not available")

        with pytest.raises(ImporterError, match="Event payload validation failed"):
            validate_event_payload_schema(payload)

    def test_validate_event_payload_schema_invalid_package_id(self):
        """Test validation fails for invalid ULID format."""
        payload = {
            "package_id": "not-a-valid-ulid",
            "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "schema_version": 1,
            "ruleset_version": "1.2.3",
        }

        # This test may pass if jsonschema is not available
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            pytest.skip("jsonschema not available")

        with pytest.raises(ImporterError, match="Event payload validation failed"):
            validate_event_payload_schema(payload)


class TestIntegrationFlow:
    """Test complete manifest phase integration."""

    @pytest.mark.asyncio
    async def test_complete_manifest_validation_flow(self):
        """Test complete flow from validation to event emission."""
        phase = ManifestPhase(features_importer_enabled=True)
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")

        # Step 1: Validate and register
        result = phase.validate_and_register(manifest_path)

        # Step 2: Validate event payload schema
        validate_event_payload_schema(result["event_payload"])

        # Step 3: Emit synthetic event
        campaign_id = 9002
        async with session_scope() as session:
            session.add(models.Campaign(id=campaign_id, name="Validation Flow"))
            await session.flush()
            event = await phase.emit_seed_event(session, campaign_id, result["event_payload"])

        # Verify complete flow
        assert event.type == "seed.manifest.validated"
        assert event.payload["package_id"] == result["manifest"]["package_id"]
        assert event.payload["manifest_hash"] == result["manifest_hash"]

    def test_deterministic_replay_same_manifest(self):
        """Test that same manifest produces same hash for replay determinism."""
        phase = ManifestPhase(features_importer_enabled=True)
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")

        # Run validation twice
        result1 = phase.validate_and_register(manifest_path)
        result2 = phase.validate_and_register(manifest_path)

        # Should produce identical results for replay determinism
        assert result1["manifest_hash"] == result2["manifest_hash"]
        assert result1["event_payload"] == result2["event_payload"]
        # Note: timestamps will differ, which is expected
