"""Tests for manifest validation and hashing (STORY-CDA-IMPORT-002A)."""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from Adventorator.manifest_validation import (
    ManifestValidationError,
    compute_manifest_hash,
    validate_content_hashes,
    validate_manifest,
    validate_manifest_schema,
)


class TestManifestValidation:
    """Test manifest validation functionality."""

    def test_validate_manifest_schema_happy_path(self):
        """Test that happy-path fixture validates against schema."""
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # Should not raise an exception
        validate_manifest_schema(manifest)

    def test_validate_manifest_schema_missing_required_field(self):
        """Test that missing required fields are caught."""
        incomplete_manifest = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            # Missing schema_version and other required fields
        }

        # This test may pass if jsonschema is not available
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            pytest.skip("jsonschema not available")

        with pytest.raises(ManifestValidationError, match="schema validation failed"):
            validate_manifest_schema(incomplete_manifest)

    def test_validate_content_hashes_happy_path(self):
        """Test content hash validation with matching hashes."""
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")
        package_root = manifest_path.parent

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        errors = validate_content_hashes(manifest, package_root)
        assert errors == [], f"Expected no hash errors, got: {errors}"

    def test_validate_content_hashes_tampered_fixture(self):
        """Test content hash validation detects mismatched hashes."""
        manifest_path = Path("tests/fixtures/import/manifest/tampered/package.manifest.json")
        package_root = manifest_path.parent

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        errors = validate_content_hashes(manifest, package_root)
        # Should detect hash mismatch for entities/npc.json
        assert len(errors) > 0, "Expected hash validation errors for tampered fixture"
        has_npc_error = any("entities/npc.json" in err for err in errors)
        assert has_npc_error, f"Expected npc hash error: {errors}"

    def test_validate_content_hashes_missing_file(self):
        """Test content hash validation detects missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)
            missing_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
            manifest = {"content_index": {"missing.txt": missing_hash}}

            errors = validate_content_hashes(manifest, package_root)
            assert len(errors) == 1
            assert "Missing file: missing.txt" in errors[0]

    def test_validate_content_hashes_path_traversal_prevention(self):
        """Test that path traversal attacks are prevented."""
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)

            # Create a file outside the package directory
            outside_file = Path(tmpdir).parent / "secret.txt"
            outside_file.write_text("secret data")

            # Attempt path traversal
            manifest = {"content_index": {"../secret.txt": "some_hash"}}

            errors = validate_content_hashes(manifest, package_root)
            assert len(errors) == 1
            assert "Security violation" in errors[0]
            assert "../secret.txt" in errors[0]
            assert "attempts to access files outside package directory" in errors[0]

    def test_validate_content_hashes_complex_path_traversal_prevention(self):
        """Test that complex path traversal attacks are prevented."""
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)

            # Test various path traversal attempts
            traversal_attempts = [
                "../../etc/passwd",
                "../../../root/.ssh/id_rsa",
                "subdir/../../../sensitive.txt",
                "legitimate/../../breakout.txt",
            ]

            manifest = {"content_index": {path: "dummy_hash" for path in traversal_attempts}}

            errors = validate_content_hashes(manifest, package_root)

            # All traversal attempts should be caught
            assert len(errors) == len(traversal_attempts)
            for error in errors:
                assert "Security violation" in error
                assert "attempts to access files outside package directory" in error

    def test_validate_content_hashes_legitimate_subdirectories_allowed(self):
        """Test that legitimate subdirectories within package are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)

            # Create legitimate subdirectories and files
            subdir = package_root / "entities"
            subdir.mkdir()
            test_file = subdir / "test.json"
            test_content = b'{"test": "content"}'
            test_file.write_bytes(test_content)

            expected_hash = hashlib.sha256(test_content).hexdigest()

            manifest = {"content_index": {"entities/test.json": expected_hash}}

            errors = validate_content_hashes(manifest, package_root)
            assert len(errors) == 0, f"Legitimate subdirectory access failed: {errors}"

    def test_compute_manifest_hash_deterministic(self):
        """Test that manifest hashing is deterministic."""
        manifest = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            "schema_version": 1,
            "content_index": {"file.txt": "abc123"},
            "ruleset_version": "1.0.0",
        }

        hash1 = compute_manifest_hash(manifest)
        hash2 = compute_manifest_hash(manifest)

        assert hash1 == hash2, "Manifest hash should be deterministic"
        assert len(hash1) == 64, "Hash should be 64-character hex string"

    def test_compute_manifest_hash_canonical_ordering(self):
        """Test that manifest hashing uses canonical key ordering."""
        # Same manifest with keys in different order
        manifest1 = {
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
            "schema_version": 1,
            "content_index": {"file.txt": "abc123"},
        }

        manifest2 = {
            "schema_version": 1,
            "content_index": {"file.txt": "abc123"},
            "package_id": "01JAR9WYH41R8TFM6Z0X5E7QKJ",
        }

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        assert hash1 == hash2, "Hash should be same regardless of key order"

    def test_validate_manifest_integration_happy_path(self):
        """Test full manifest validation with happy-path fixture."""
        manifest_path = Path("tests/fixtures/import/manifest/happy-path/package.manifest.json")

        manifest, manifest_hash = validate_manifest(manifest_path)

        assert isinstance(manifest, dict)
        assert manifest["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7QKJ"
        assert len(manifest_hash) == 64  # SHA-256 hex

    def test_validate_manifest_integration_tampered_fails(self):
        """Test full manifest validation fails with tampered fixture."""
        manifest_path = Path("tests/fixtures/import/manifest/tampered/package.manifest.json")

        with pytest.raises(ManifestValidationError, match="Content hash validation failed"):
            validate_manifest(manifest_path)

    def test_validate_manifest_nonexistent_file(self):
        """Test validation fails gracefully for missing manifest."""
        nonexistent_path = Path("/tmp/nonexistent-manifest.json")

        with pytest.raises(ManifestValidationError, match="Failed to load manifest"):
            validate_manifest(nonexistent_path)


class TestManifestHashingEdgeCases:
    """Test edge cases for manifest hashing."""

    def test_unicode_normalization(self):
        """Test that Unicode strings are normalized consistently."""
        # Two different Unicode representations of the same text
        manifest1 = {"title": "café"}  # é as single character
        manifest2 = {"title": "cafe\u0301"}  # e + combining acute accent

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        # Should produce same hash after NFC normalization
        assert hash1 == hash2, "Unicode normalization should make hashes equal"

    def test_null_field_elision(self):
        """Test that null fields are omitted from hashing."""
        manifest1 = {"field": "value"}
        manifest2 = {"field": "value", "null_field": None}

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        assert hash1 == hash2, "Null fields should be elided"

    def test_empty_manifest(self):
        """Test hashing of empty manifest."""
        empty_manifest = {}
        hash_result = compute_manifest_hash(empty_manifest)

        assert len(hash_result) == 64
        assert hash_result == compute_manifest_hash({}), "Empty manifest hash should be consistent"
