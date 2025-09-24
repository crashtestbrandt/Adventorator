"""Manifest validation and hashing utilities implementing STORY-CDA-IMPORT-002A.

This module provides:
- JSON schema validation for package manifests 
- Content hash verification against manifest content_index
- Deterministic manifest hashing using canonical JSON
- Manifest validation errors with descriptive messages

Implements requirements from:
- ADR-0011 Package Import Provenance
- ADR-0006 Event Envelope & Hash Chain  
- ADR-0007 Canonical JSON Policy
- ARCH-CDA-001 Campaign Data Architecture
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from Adventorator.canonical_json import compute_canonical_hash


class ManifestValidationError(ValueError):
    """Raised when manifest validation fails."""
    pass


def validate_manifest_schema(manifest: dict[str, Any], schema_path: Path | None = None) -> None:
    """Validate manifest against JSON schema.
    
    Args:
        manifest: Parsed manifest dictionary
        schema_path: Path to schema file (defaults to contracts/package/manifest.v1.json)
        
    Raises:
        ManifestValidationError: If validation fails
    """
    try:
        import jsonschema
    except ImportError:
        # Skip schema validation if jsonschema is not available
        return
    
    if schema_path is None:
        schema_path = Path("contracts/package/manifest.v1.json")
    
    if not schema_path.exists():
        raise ManifestValidationError(f"Manifest schema not found at {schema_path}")
    
    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ManifestValidationError(f"Failed to load manifest schema: {exc}") from exc
    
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:
        raise ManifestValidationError(f"Manifest schema validation failed: {exc.message}") from exc


def validate_content_hashes(manifest: dict[str, Any], package_root: Path) -> list[str]:
    """Validate that content_index hashes match actual file contents.
    
    Args:
        manifest: Parsed manifest dictionary with content_index
        package_root: Root directory containing package files
        
    Returns:
        List of error messages for mismatched files (empty if all match)
    """
    errors: list[str] = []
    content_index = manifest.get("content_index", {})
    
    for file_path, expected_hash in content_index.items():
        full_path = package_root / file_path
        
        if not full_path.exists():
            errors.append(f"Missing file: {file_path}")
            continue
            
        try:
            with open(full_path, "rb") as f:
                file_content = f.read()
            actual_hash = hashlib.sha256(file_content).hexdigest()
            
            if actual_hash != expected_hash:
                errors.append(f"Hash mismatch for {file_path}: expected {expected_hash}, got {actual_hash}")
                
        except OSError as exc:
            errors.append(f"Failed to read {file_path}: {exc}")
    
    return errors


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """Compute deterministic hash of manifest using canonical JSON.
    
    Args:
        manifest: Parsed manifest dictionary
        
    Returns:
        Hex-encoded SHA-256 hash of canonical JSON representation
    """
    hash_bytes = compute_canonical_hash(manifest)
    return hash_bytes.hex()


def validate_manifest(manifest_path: Path, package_root: Path | None = None) -> tuple[dict[str, Any], str]:
    """Validate a manifest file and compute its hash.
    
    Args:
        manifest_path: Path to package.manifest.json file
        package_root: Root directory for content validation (defaults to manifest_path parent)
        
    Returns:
        Tuple of (validated_manifest_dict, manifest_hash_hex)
        
    Raises:
        ManifestValidationError: If validation fails
    """
    if package_root is None:
        package_root = manifest_path.parent
    
    # Load and parse manifest
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ManifestValidationError(f"Failed to load manifest from {manifest_path}: {exc}") from exc
    
    # Validate schema
    validate_manifest_schema(manifest)
    
    # Validate content hashes
    hash_errors = validate_content_hashes(manifest, package_root)
    if hash_errors:
        error_msg = "Content hash validation failed:\n" + "\n".join(f"  - {err}" for err in hash_errors)
        raise ManifestValidationError(error_msg)
    
    # Compute manifest hash
    manifest_hash = compute_manifest_hash(manifest)
    
    return manifest, manifest_hash