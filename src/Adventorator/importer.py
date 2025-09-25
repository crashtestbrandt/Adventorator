"""Campaign package importer implementing STORY-CDA-IMPORT-002A, 002B & 002C.

This module provides the manifest validation and entity ingestion phases of the import pipeline:
- Manifest schema validation & synthetic seed.manifest.validated events
- Entity file parsing, validation, and synthetic seed.entity_created events
- Content hash verification & deterministic manifest hashing
- ImportLog provenance recording per ADR-0011
- Deterministic ordering and collision detection
- Idempotent replay support
- Metrics emission for observability

Implements requirements from ADR-0011, ADR-0006, ADR-0007, and ARCH-CDA-001.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from Adventorator.manifest_validation import ManifestValidationError, validate_manifest
from Adventorator.metrics import inc_counter as metrics_inc_counter

# Set up logging
logger = logging.getLogger(__name__)


def inc_counter(metric_name: str, value: int = 1, **tags) -> None:
    """Increment a counter metric with actual metrics system.

    Args:
        metric_name: Name of the metric to increment
        value: Value to increment by (default 1)
        **tags: Additional tags for the metric (logged for context)
    """
    # Use actual metrics system
    metrics_inc_counter(metric_name, value)
    # Log tags for context since metrics system doesn't support tags yet
    if tags:
        logger.debug(f"Metric {metric_name} incremented by {value} with tags {tags}")


def emit_structured_log(event: str, **fields) -> None:
    """Emit structured log event.

    Args:
        event: Log event name
        **fields: Additional structured fields
    """
    log_data = {"event": event, **fields}
    logger.info("Structured log", extra={"structured_data": log_data})


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

    def validate_and_register(
        self, manifest_path: Path, package_root: Path | None = None
    ) -> dict[str, Any]:
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
            "ruleset_version": manifest["ruleset_version"],
        }

        # Prepare ImportLog entry
        import_log_entry = {
            "phase": "manifest",
            "object_type": "package",
            "stable_id": manifest["package_id"],
            "file_hash": manifest_hash,
            "action": "validated",
            "timestamp": datetime.now(timezone.utc),
        }

        return {
            "manifest": manifest,
            "manifest_hash": manifest_hash,
            "event_payload": event_payload,
            "import_log_entry": import_log_entry,
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
            "idempotency_key": None,  # Would be computed by event ledger
        }

        return event_envelope


class EntityValidationError(ImporterError):
    """Exception raised when entity validation fails."""

    pass


class EntityCollisionError(ImporterError):
    """Exception raised when entity stable_id collision is detected."""

    pass


class EdgeValidationError(ImporterError):
    """Exception raised when edge validation fails."""

    pass


class EdgeCollisionError(ImporterError):
    """Exception raised when edge stable_id collision is detected."""

    pass


class EntityPhase:
    """Handles entity ingestion phase of package import."""

    def __init__(self, features_importer_enabled: bool = False):
        """Initialize entity phase.

        Args:
            features_importer_enabled: Whether importer feature flag is enabled
        """
        self.features_importer_enabled = features_importer_enabled

    def parse_and_validate_entities(
        self, package_root: Path, manifest: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Parse and validate all entity files in package.

        Args:
            package_root: Root directory of the package
            manifest: Validated package manifest

        Returns:
            List of parsed and validated entity dictionaries with provenance

        Raises:
            ImporterError: If feature flag is disabled or validation fails
        """
        if not self.features_importer_enabled:
            raise ImporterError("Importer feature flag is disabled (features.importer=false)")

        entities: list[dict[str, Any]] = []
        package_id = manifest["package_id"]
        content_index = manifest.get("content_index", {})

        # Find all entity files by scanning entities/ directory
        entities_dir = package_root / "entities"
        if not entities_dir.exists():
            emit_structured_log(
                "entity_parse_complete",
                package_id=package_id,
                entity_count=0,
                message="No entities directory found",
            )
            return entities

        entity_files = []
        for file_path in entities_dir.rglob("*.json"):
            rel_path = file_path.relative_to(package_root).as_posix()
            entity_files.append((rel_path, file_path))

        # Sort deterministically by (kind, stable_id, source_path)
        # We'll parse first to get sort keys, then re-sort
        parsed_entities = []
        collisions_detected = 0
        entities_skipped_idempotent = 0

        for rel_path, file_path in entity_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Normalize text to UTF-8 NFC
                normalized_content = unicodedata.normalize("NFC", content)
                entity_data = json.loads(normalized_content)

                # Validate against JSON schema first, then basic fields
                validate_entity_schema(entity_data)
                self._validate_entity_schema(entity_data, rel_path)

                # Compute file hash
                file_hash = self._compute_file_hash(normalized_content)

                # Verify against content index if present
                if rel_path in content_index:
                    expected_hash = content_index[rel_path]
                    if file_hash != expected_hash:
                        raise EntityValidationError(
                            f"File hash mismatch for {rel_path}: "
                            f"expected {expected_hash}, got {file_hash}"
                        )

                # Add provenance data
                entity_with_provenance = {
                    **entity_data,
                    "provenance": {
                        "package_id": package_id,
                        "source_path": rel_path,
                        "file_hash": file_hash,
                    },
                }

                parsed_entities.append(entity_with_provenance)

            except (json.JSONDecodeError, OSError) as exc:
                raise EntityValidationError(
                    f"Failed to parse entity file {rel_path}: {exc}"
                ) from exc

        # Sort deterministically by (kind, stable_id, source_path)
        parsed_entities.sort(
            key=lambda e: (
                e.get("kind", ""),
                e.get("stable_id", ""),
                e["provenance"]["source_path"],
            )
        )

        # Check for stable_id collisions and filter duplicates
        try:
            filtered_entities, entities_skipped_idempotent = self._check_stable_id_collisions(
                parsed_entities
            )
        except EntityCollisionError as exc:
            collisions_detected = 1
            inc_counter("importer.collision", value=1, package_id=package_id)
            raise exc

        # Create ImportLog entries for each entity
        import_log_entries = []
        for i, entity in enumerate(filtered_entities):
            import_log_entry = {
                "sequence_no": i + 1,
                "phase": "entity",
                "object_type": entity["kind"],
                "stable_id": entity["stable_id"],
                "file_hash": entity["provenance"]["file_hash"],
                "action": "created",
                "manifest_hash": manifest.get("manifest_hash", "unknown"),
                "timestamp": datetime.now(timezone.utc),
            }
            import_log_entries.append(import_log_entry)

        # Emit metrics with actual counts
        entity_count = len(filtered_entities)
        inc_counter("importer.entities.created", value=entity_count, package_id=package_id)
        if entities_skipped_idempotent > 0:
            inc_counter(
                "importer.entities.skipped_idempotent",
                value=entities_skipped_idempotent,
                package_id=package_id,
            )

        # Store ImportLog entries (would be persisted to database in real implementation)
        for entity in filtered_entities:
            entity["import_log_entries"] = import_log_entries

        # Log summary
        emit_structured_log(
            "entity_parse_complete",
            package_id=package_id,
            entity_count=entity_count,
            collisions_detected=collisions_detected,
            entities_skipped_idempotent=entities_skipped_idempotent,
        )

        return filtered_entities

    def _validate_entity_schema(self, entity_data: dict[str, Any], source_path: str) -> None:
        """Validate entity data against schema.

        Args:
            entity_data: Parsed entity data
            source_path: Path for error reporting

        Raises:
            EntityValidationError: If validation fails
        """
        required_fields = ["stable_id", "kind", "name", "tags", "affordances"]
        for field in required_fields:
            if field not in entity_data:
                raise EntityValidationError(f"Missing required field '{field}' in {source_path}")

        # Validate stable_id format (ULID-like)
        stable_id = entity_data["stable_id"]
        if not isinstance(stable_id, str) or len(stable_id) != 26:
            raise EntityValidationError(f"Invalid stable_id format in {source_path}: {stable_id}")

        # Validate kind
        valid_kinds = ["npc", "location", "item", "organization", "creature"]
        if entity_data["kind"] not in valid_kinds:
            raise EntityValidationError(
                f"Invalid kind '{entity_data['kind']}' in {source_path}. "
                f"Must be one of: {', '.join(valid_kinds)}"
            )

        # Validate name
        if not isinstance(entity_data["name"], str) or not entity_data["name"].strip():
            raise EntityValidationError(f"Invalid name in {source_path}")

        # Validate tags and affordances are arrays
        for field in ["tags", "affordances"]:
            if not isinstance(entity_data[field], list):
                raise EntityValidationError(f"Field '{field}' must be an array in {source_path}")

    def _compute_file_hash(self, content: str) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            content: Normalized file content

        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _check_stable_id_collisions(
        self, entities: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        """Check for stable_id collisions and filter duplicates for idempotent replay.

        Args:
            entities: List of parsed entities

        Returns:
            Tuple of (filtered_entities, skipped_count)

        Raises:
            EntityCollisionError: If collisions are detected
        """
        seen_ids: dict[str, tuple[str, str]] = {}
        filtered_entities = []
        skipped_count = 0

        for entity in entities:
            stable_id = entity["stable_id"]
            file_hash = entity["provenance"]["file_hash"]
            source_path = entity["provenance"]["source_path"]

            if stable_id in seen_ids:
                existing_hash, existing_path = seen_ids[stable_id]
                if file_hash != existing_hash:
                    raise EntityCollisionError(
                        f"Stable ID collision detected for '{stable_id}': "
                        f"different content in {existing_path} vs {source_path}"
                    )
                # Same hash = idempotent duplicate, skip it
                skipped_count += 1
            else:
                seen_ids[stable_id] = (file_hash, source_path)
                filtered_entities.append(entity)

        return filtered_entities, skipped_count

    def create_seed_events(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create seed.entity_created events for parsed entities.

        Args:
            entities: List of validated entities with provenance

        Returns:
            List of event payloads for seed.entity_created events
        """
        events = []
        for entity in entities:
            # Create event payload (exclude internal fields)
            event_payload = {
                "stable_id": entity["stable_id"],
                "kind": entity["kind"],
                "name": entity["name"],
                "tags": entity["tags"],
                "affordances": entity["affordances"],
                "provenance": entity["provenance"],
            }

            # Add optional fields if present
            if "traits" in entity:
                event_payload["traits"] = entity["traits"]
            if "props" in entity:
                event_payload["props"] = entity["props"]

            # Validate event payload against schema
            validate_event_payload_schema(event_payload, event_type="entity")

            events.append(event_payload)

        return events


class EdgePhase:
    """Handles edge ingestion phase of package import."""

    def __init__(self, features_importer_enabled: bool = False):
        self.features_importer_enabled = features_importer_enabled

    def parse_and_validate_edges(
        self,
        package_root: Path,
        manifest: dict[str, Any],
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.features_importer_enabled:
            raise ImporterError("Importer feature flag is disabled (features.importer=false)")

        edges_dir = package_root / "edges"
        package_id = manifest.get("package_id", "unknown")
        content_index = manifest.get("content_index", {})

        if not edges_dir.exists():
            emit_structured_log(
                "edge_parse_complete",
                package_id=package_id,
                edge_count=0,
                message="No edges directory found",
            )
            return []

        taxonomy = load_edge_taxonomy()
        known_entities = {entity.get("stable_id") for entity in entities if entity.get("stable_id")}

        edge_files: list[tuple[str, Path]] = []
        for file_path in edges_dir.rglob("*.json"):
            rel_path = file_path.relative_to(package_root).as_posix()
            edge_files.append((rel_path, file_path))

        edge_files.sort()

        parsed_edges: list[dict[str, Any]] = []
        seen_edges: dict[str, tuple[str, str]] = {}
        skipped_idempotent = 0

        for rel_path, file_path in edge_files:
            try:
                with open(file_path, encoding="utf-8") as handle:
                    content = handle.read()

                normalized = unicodedata.normalize("NFC", content)
                payload = json.loads(normalized)
            except (json.JSONDecodeError, OSError) as exc:
                raise EdgeValidationError(f"Failed to parse edge file {rel_path}: {exc}") from exc

            if isinstance(payload, list):
                records = payload
                suffix_template = "#{}"
            elif isinstance(payload, dict):
                records = [payload]
                suffix_template = "#{}"
            else:
                raise EdgeValidationError(
                    f"Edge file {rel_path} must contain an object or array of edge definitions"
                )

            for idx, record in enumerate(records):
                if not isinstance(record, dict):
                    raise EdgeValidationError(f"Edge entry {rel_path}#{idx} must be an object")

                validate_edge_schema(record)

                stable_id = record.get("stable_id")

                edge_type = record.get("type")
                if edge_type not in taxonomy:
                    raise EdgeValidationError(
                        f"Edge {stable_id} uses unsupported edge type '{edge_type}'"
                    )

                taxonomy_entry = taxonomy[edge_type]
                required_attrs = taxonomy_entry.get("required_attributes", [])
                attributes = record.get("attributes", {})
                for attr in required_attrs:
                    if attr not in attributes:
                        raise EdgeValidationError(
                            f"Edge {stable_id} missing required attribute '{attr}' "
                            f"for type {edge_type}"
                        )

                validity_required = taxonomy_entry.get("validity_required", False)
                validity = record.get("validity")
                if validity_required and not validity:
                    raise EdgeValidationError(
                        f"Edge {stable_id} requires validity metadata per taxonomy"
                    )

                if validity:
                    start_event = validity.get("start_event_id")
                    if not isinstance(start_event, str) or not start_event:
                        raise EdgeValidationError(
                            f"Edge {stable_id} validity must include start_event_id"
                        )
                    end_event = validity.get("end_event_id")
                    if isinstance(end_event, str) and end_event < start_event:
                        raise EdgeValidationError(
                            f"Edge {stable_id} end_event_id must not precede start_event_id"
                        )

                src_ref = record.get("src_ref")
                dst_ref = record.get("dst_ref")
                missing_refs = [
                    ref for ref in (src_ref, dst_ref) if ref and ref not in known_entities
                ]
                if missing_refs:
                    missing_display = ", ".join(missing_refs)
                    raise EdgeValidationError(
                        f"Edge {stable_id} missing entity reference(s): {missing_display}"
                    )

                canonical_payload = json.dumps(
                    record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                file_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
                source_path = f"{rel_path}{suffix_template.format(idx)}"

                if source_path in content_index:
                    expected_hash = content_index[source_path]
                    if expected_hash != file_hash:
                        raise EdgeValidationError(
                            f"File hash mismatch for {source_path}: expected {expected_hash}, "
                            f"got {file_hash}"
                        )

                stable_id = record.get("stable_id")
                if not isinstance(stable_id, str) or not stable_id:
                    raise EdgeValidationError(f"Edge definition in {source_path} missing stable_id")

                if stable_id in seen_edges:
                    existing_hash, existing_path = seen_edges[stable_id]
                    if file_hash != existing_hash:
                        inc_counter(
                            "importer.edges.collision",
                            value=1,
                            package_id=package_id,
                        )
                        raise EdgeCollisionError(
                            f"Stable ID collision detected for '{stable_id}': "
                            f"different content in {existing_path} vs {source_path}"
                        )
                    skipped_idempotent += 1
                    continue

                seen_edges[stable_id] = (file_hash, source_path)

                edge_with_metadata = {
                    **record,
                    "provenance": {
                        "package_id": package_id,
                        "source_path": source_path,
                        "file_hash": file_hash,
                    },
                }
                parsed_edges.append(edge_with_metadata)

        parsed_edges.sort(
            key=lambda edge: (
                edge.get("type", ""),
                edge.get("src_ref", ""),
                edge.get("dst_ref", ""),
                edge["provenance"]["source_path"],
            )
        )

        manifest_hash = manifest.get("manifest_hash", "unknown")
        for index, edge in enumerate(parsed_edges, start=1):
            edge["import_log_entry"] = {
                "sequence_no": index,
                "phase": "edge",
                "object_type": edge["type"],
                "stable_id": edge["stable_id"],
                "file_hash": edge["provenance"]["file_hash"],
                "action": "created",
                "manifest_hash": manifest_hash,
                "timestamp": datetime.now(timezone.utc),
            }

        created_count = len(parsed_edges)
        if created_count:
            inc_counter("importer.edges.created", value=created_count, package_id=package_id)
        if skipped_idempotent:
            inc_counter(
                "importer.edges.skipped_idempotent",
                value=skipped_idempotent,
                package_id=package_id,
            )

        emit_structured_log(
            "edge_parse_complete",
            package_id=package_id,
            edge_count=created_count,
            edges_skipped_idempotent=skipped_idempotent,
        )

        return parsed_edges

    def create_seed_events(self, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for edge in edges:
            provenance = edge.get("provenance")
            if provenance is None:
                stable_id = edge.get("stable_id")
                raise ValueError(
                    f"Edge {stable_id} missing provenance metadata required for event emission"
                )

            payload: dict[str, Any] = {
                "stable_id": edge["stable_id"],
                "type": edge["type"],
                "src_ref": edge["src_ref"],
                "dst_ref": edge["dst_ref"],
                "attributes": edge.get("attributes", {}),
                "provenance": provenance,
            }

            if edge.get("validity") is not None:
                payload["validity"] = edge["validity"]

            validate_event_payload_schema(payload, event_type="edge")
            events.append(payload)

        return events


def create_entity_phase(features_importer: bool = False) -> EntityPhase:
    """Factory function to create entity phase with feature flag.

    Args:
        features_importer: Value of features.importer feature flag

    Returns:
        Configured EntityPhase instance
    """
    return EntityPhase(features_importer_enabled=features_importer)


def create_edge_phase(features_importer: bool = False) -> EdgePhase:
    """Factory function to create edge phase with feature flag.

    Args:
        features_importer: Value of features.importer feature flag

    Returns:
        Configured EdgePhase instance
    """
    return EdgePhase(features_importer_enabled=features_importer)


def create_manifest_phase(features_importer: bool = False) -> ManifestPhase:
    """Factory function to create manifest phase with feature flag.

    Args:
        features_importer: Value of features.importer feature flag

    Returns:
        Configured ManifestPhase instance
    """
    return ManifestPhase(features_importer_enabled=features_importer)


def validate_event_payload_schema(payload: dict[str, Any], event_type: str = "manifest") -> None:
    """Validate event payload against schema.

    Args:
        payload: Event payload to validate
        event_type: Type of event ("manifest" or "entity")

    Raises:
        ImporterError: If payload doesn't match schema
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        # Skip validation if jsonschema not available
        return

    if event_type == "manifest":
        schema_path = Path("contracts/events/seed/manifest-validated.v1.json")
    elif event_type == "entity":
        schema_path = Path("contracts/events/seed/entity-created.v1.json")
    elif event_type == "edge":
        schema_path = Path("contracts/events/seed/edge-created.v1.json")
    else:
        raise ImporterError(f"Unknown event type: {event_type}")

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


def validate_entity_schema(entity_data: dict[str, Any]) -> None:
    """Validate entity data against entity schema.

    Args:
        entity_data: Entity data to validate

    Raises:
        EntityValidationError: If validation fails
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        # Fallback to basic validation
        return

    schema_path = Path("contracts/entities/entity.v1.json")
    if not schema_path.exists():
        return

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    try:
        jsonschema.validate(entity_data, schema)
    except jsonschema.ValidationError as exc:
        raise EntityValidationError(f"Entity validation failed: {exc.message}") from exc


@lru_cache(maxsize=1)
def load_edge_taxonomy() -> dict[str, Any]:
    """Load the edge type taxonomy declared under contracts."""

    taxonomy_path = Path("contracts/edges/edge-type-taxonomy.json")
    if not taxonomy_path.exists():
        return {}

    try:
        with taxonomy_path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def validate_edge_schema(edge_data: dict[str, Any]) -> None:
    """Validate edge definition against edge schema."""

    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        return

    schema_path = Path("contracts/edges/edge.v1.json")
    if not schema_path.exists():
        return

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    try:
        jsonschema.validate(edge_data, schema)
    except jsonschema.ValidationError as exc:
        raise EdgeValidationError(f"Edge validation failed: {exc.message}") from exc
