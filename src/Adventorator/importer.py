"""Campaign package importer implementing STORY-CDA-IMPORT-002A.

This module provides the manifest validation phase of the import pipeline:
- Manifest schema validation
- Content hash verification  
- Deterministic manifest hashing
- Synthetic seed.manifest.validated event emission
- ImportLog provenance recording

Implements requirements from ADR-0011, ADR-0006, ADR-0007, and ARCH-CDA-001.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Adventorator.manifest_validation import ManifestValidationError, validate_manifest


class ImporterError(Exception):
    """Base exception for importer errors."""
    pass


class ManifestPhase:
    """Handles manifest validation and registration phase of package import."""
    
    def __init__(self, features_importer_enabled: bool = False):
        """Initialize manifest phase.
        
        Args:
            features_importer_enabled: Whether importer feature flag is enabled
        """
        self.features_importer_enabled = features_importer_enabled
    
    def validate_and_register(self, manifest_path: Path, package_root: Path | None = None) -> dict[str, Any]:
        """Validate manifest and prepare for registration.
        
        Args:
            manifest_path: Path to package.manifest.json file
            package_root: Root directory for content validation (defaults to manifest_path parent)
            
        Returns:
            Dictionary containing validated manifest data and metadata
            
        Raises:
            ImporterError: If feature flag is disabled or validation fails
        """
        if not self.features_importer_enabled:
            raise ImporterError("Importer feature flag is disabled (features.importer=false)")
        
        try:
            manifest, manifest_hash = validate_manifest(manifest_path, package_root)
        except ManifestValidationError as exc:
            raise ImporterError(f"Manifest validation failed: {exc}") from exc
        
        # Prepare event payload for seed.manifest.validated
        event_payload = {
            "package_id": manifest["package_id"],
            "manifest_hash": manifest_hash,
            "schema_version": manifest["schema_version"], 
            "ruleset_version": manifest["ruleset_version"]
        }
        
        # Prepare ImportLog entry
        import_log_entry = {
            "phase": "manifest",
            "object_type": "package",
            "stable_id": manifest["package_id"],
            "file_hash": manifest_hash,
            "action": "validated",
            "timestamp": datetime.now(timezone.utc)
        }
        
        return {
            "manifest": manifest,
            "manifest_hash": manifest_hash,
            "event_payload": event_payload,
            "import_log_entry": import_log_entry
        }
    
    def emit_seed_event(self, event_payload: dict[str, Any]) -> dict[str, Any]:
        """Emit synthetic seed.manifest.validated event.
        
        Args:
            event_payload: Event payload from validate_and_register
            
        Returns:
            Event envelope dict (placeholder - actual event emission TBD)
        """
        # Placeholder for actual event emission - would integrate with event ledger
        event_envelope = {
            "event_type": "seed.manifest.validated",
            "payload": event_payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "replay_ordinal": None,  # Would be assigned by event ledger
            "idempotency_key": None  # Would be computed by event ledger
        }
        
        return event_envelope


def create_manifest_phase(features_importer: bool = False) -> ManifestPhase:
    """Factory function to create manifest phase with feature flag.
    
    Args:
        features_importer: Value of features.importer feature flag
        
    Returns:
        Configured ManifestPhase instance
    """
    return ManifestPhase(features_importer_enabled=features_importer)


def validate_event_payload_schema(payload: dict[str, Any]) -> None:
    """Validate seed.manifest.validated event payload against schema.
    
    Args:
        payload: Event payload to validate
        
    Raises:
        ImporterError: If payload doesn't match schema
    """
    try:
        import jsonschema
    except ImportError:
        # Skip validation if jsonschema not available
        return
    
    schema_path = Path("contracts/events/seed/manifest-validated.v1.json")
    if not schema_path.exists():
        raise ImporterError(f"Event schema not found at {schema_path}")
    
    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ImporterError(f"Failed to load event schema: {exc}") from exc
    
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        raise ImporterError(f"Event payload validation failed: {exc.message}") from exc