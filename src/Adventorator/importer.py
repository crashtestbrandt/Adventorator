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
from Adventorator.metrics import inc_counter as metrics_inc_counter, get_counter
from Adventorator.metrics import observe_histogram
from Adventorator.db import session_scope
from Adventorator import repos, models
from Adventorator.importer_context import ImporterRunContext
from sqlalchemy.ext.asyncio import AsyncSession

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


def record_idempotent_run(package_id: str, manifest_hash: str) -> None:
    """Record metrics and logs for idempotent import run.
    
    Args:
        package_id: Package identifier
        manifest_hash: Manifest hash for correlation
    """
    inc_counter("importer.idempotent", package_id=package_id)
    emit_structured_log(
        "import_idempotent_run",
        package_id=package_id,
        manifest_hash=manifest_hash,
        outcome="idempotent_skip"
    )


def record_rollback(phase: str, package_id: str, manifest_hash: str, reason: str) -> None:
    """Record metrics and logs for import rollback.
    
    Args:
        phase: Import phase where rollback occurred
        package_id: Package identifier
        manifest_hash: Manifest hash for correlation  
        reason: Reason for rollback
    """
    inc_counter("importer.rollback", package_id=package_id)
    inc_counter(f"importer.rollback.{phase}", package_id=package_id)
    emit_structured_log(
        "import_rollback", 
        package_id=package_id,
        manifest_hash=manifest_hash,
        phase=phase,
        outcome="rollback",
        reason=reason
    )


# Database Integration Functions
async def persist_import_event(
    session: AsyncSession,
    campaign_id: int,
    scene_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    actor_id: str = "importer"
) -> models.Event:
    """Persist an import-related event to the database.
    
    Args:
        session: Database session
        campaign_id: Campaign ID for the import
        scene_id: Scene ID (optional, for import events)
        event_type: Type of event (e.g., 'seed.manifest.validated')
        payload: Event payload data
        actor_id: Who triggered the event (default: 'importer')
        
    Returns:
        Created Event record
    """
    # For import events, we'll create scene-less events linked to campaign
    if scene_id is None:
        # Create a temporary execution request ID for import events
        request_id = f"import-{campaign_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        # Get the last event to determine replay_ordinal and prev_hash
        from sqlalchemy import select
        last_event = await session.execute(
            select(models.Event)
            .where(models.Event.campaign_id == campaign_id)
            .order_by(models.Event.replay_ordinal.desc())
            .limit(1)
        )
        last_event_row = last_event.scalar_one_or_none()
        
        if last_event_row is None:
            replay_ordinal = 0
            from Adventorator.events import envelope as event_envelope
            prev_hash = event_envelope.GENESIS_PREV_EVENT_HASH
        else:
            replay_ordinal = last_event_row.replay_ordinal + 1
            from Adventorator.events import envelope as event_envelope
            prev_hash = event_envelope.compute_envelope_hash(
                campaign_id=last_event_row.campaign_id,
                scene_id=last_event_row.scene_id,
                replay_ordinal=last_event_row.replay_ordinal,
                event_type=last_event_row.type,
                event_schema_version=last_event_row.event_schema_version,
                world_time=last_event_row.world_time,
                wall_time_utc=last_event_row.wall_time_utc,
                prev_event_hash=last_event_row.prev_event_hash,
                payload_hash=last_event_row.payload_hash,
                idempotency_key=last_event_row.idempotency_key,
            )
        
        payload_hash = event_envelope.compute_payload_hash(payload)
        # Exclude replay_ordinal from idempotency key per EPIC-CDA-IMPORT-002 requirements
        # Idempotency keys should be based on stable content only, not run-scoped fields
        idempotency_key = event_envelope.compute_idempotency_key(
            campaign_id=campaign_id,
            event_type=event_type,
            execution_request_id=request_id,
            plan_id=None,
            payload=payload,
            # replay_ordinal=replay_ordinal,  # Excluded per EPIC spec
        )
        
        event = models.Event(
            campaign_id=campaign_id,
            scene_id=scene_id,
            replay_ordinal=replay_ordinal,
            actor_id=actor_id,
            type=event_type,
            event_schema_version=event_envelope.GENESIS_SCHEMA_VERSION,
            world_time=replay_ordinal,
            prev_event_hash=prev_hash,
            payload_hash=payload_hash,
            idempotency_key=idempotency_key,
            execution_request_id=request_id,
            payload=payload,
        )
        
        session.add(event)
        await session.flush()  # Get the ID without committing
        return event
    else:
        # Use existing repos.append_event for scene-based events
        return await repos.append_event(
            session,
            scene_id=scene_id,
            actor_id=actor_id,
            type=event_type,
            payload=payload
        )


async def persist_import_log_entry(
    session: AsyncSession,
    campaign_id: int,
    entry: dict[str, Any]
) -> models.ImportLog:
    """Persist an ImportLog entry to the database.
    
    Args:
        session: Database session
        campaign_id: Campaign ID for the import
        entry: ImportLog entry data
        
    Returns:
        Created ImportLog record
    """
    import_log = models.ImportLog(
        campaign_id=campaign_id,
        sequence_no=entry["sequence_no"],
        phase=entry["phase"],
        object_type=entry["object_type"],
        stable_id=entry["stable_id"],
        file_hash=entry["file_hash"],
        action=entry["action"],
        manifest_hash=entry.get("manifest_hash", ""),
        timestamp=entry.get("timestamp", datetime.now(timezone.utc)),
    )
    
    session.add(import_log)
    await session.flush()  # Get the ID without committing
    return import_log


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
            # Record rollback for manifest validation failure  
            package_id = getattr(exc, 'package_id', 'unknown')
            record_rollback("manifest", package_id, "unknown", str(exc))
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
                try:
                    validate_entity_schema(entity_data)
                    self._validate_entity_schema(entity_data, rel_path)
                except EntityValidationError as exc:
                    # Record rollback for entity schema validation failure
                    record_rollback("entity", package_id, manifest.get("manifest_hash", "unknown"), str(exc))
                    raise

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
                # Record rollback for entity parsing/validation failure
                record_rollback("entity", package_id, manifest.get("manifest_hash", "unknown"), str(exc))
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
            # Record rollback metrics and logs
            record_rollback("entity", package_id, manifest.get("manifest_hash", "unknown"), str(exc))
            raise exc

        # Create ImportLog entries for each entity and assign them individually
        for i, entity in enumerate(filtered_entities):
            import_log_entry = {
                # sequence_no will be assigned by ImporterRunContext._merge_import_logs
                "phase": "entity",
                "object_type": entity["kind"],
                "stable_id": entity["stable_id"],
                "file_hash": entity["provenance"]["file_hash"],
                "action": "created",
                "manifest_hash": manifest.get("manifest_hash", "unknown"),
                "timestamp": datetime.now(timezone.utc),
            }
            # Each entity gets only its own ImportLog entry
            entity["import_log_entries"] = [import_log_entry]

        # Emit metrics with actual counts
        entity_count = len(filtered_entities)
        inc_counter("importer.entities.created", value=entity_count, package_id=package_id)
        if entities_skipped_idempotent > 0:
            inc_counter(
                "importer.entities.skipped_idempotent",
                value=entities_skipped_idempotent,
                package_id=package_id,
            )

        # Log summary
        emit_structured_log(
            "entity_parse_complete",
            package_id=package_id,
            entity_count=entity_count,
            collisions_detected=collisions_detected,
            entities_skipped_idempotent=entities_skipped_idempotent,
        )

        # Create seed events for successfully parsed entities and attach to entity records
        seed_events = self.create_seed_events(filtered_entities)
        
        # Attach event payloads to entity records for database persistence
        for i, entity in enumerate(filtered_entities):
            if i < len(seed_events):
                entity["event_payload"] = seed_events[i]

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

            suffix_template = "#{}"
            if isinstance(payload, list):
                records = payload
            elif isinstance(payload, dict):
                records = [payload]
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

                # stable_id already retrieved earlier; use existing value
                if not isinstance(stable_id, str) or not stable_id:
                    raise EdgeValidationError(f"Edge definition in {source_path} missing stable_id")

                if stable_id in seen_edges:
                    existing_hash, existing_path = seen_edges[stable_id]
                    if file_hash != existing_hash:
                        inc_counter(
                            "importer.collision",
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
                # sequence_no will be assigned by ImporterRunContext._merge_import_logs
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

        # Create seed events for successfully parsed edges and attach to edge records
        seed_events = self.create_seed_events(parsed_edges)
        
        # Attach event payloads to edge records for database persistence
        for i, edge in enumerate(parsed_edges):
            if i < len(seed_events):
                edge["event_payload"] = seed_events[i]

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
        event_type: Type of event ("manifest", "entity", "edge", or "content_chunk")

    Raises:
        ImporterError: If payload doesn't match schema
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        # Skip validation if jsonschema not available
        return

    # Apply schema validation to all event types for deterministic payload enforcement

    if event_type == "manifest":
        schema_path = Path("contracts/events/seed/manifest-validated.v1.json")
    elif event_type == "entity":
        schema_path = Path("contracts/events/seed/entity-created.v1.json")
    elif event_type == "edge":
        schema_path = Path("contracts/events/seed/edge-created.v1.json")
    elif event_type == "content_chunk":
        schema_path = Path("contracts/events/seed/content-chunk-ingested.v1.json")
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


class OntologyValidationError(Exception):
    """Raised when ontology parsing or validation fails."""

    pass


class OntologyPhase:
    """Handles ontology (tags and affordances) parsing and registration.

    Implements STORY-CDA-IMPORT-002D requirements.
    """

    def __init__(self, features_importer_enabled: bool = True):
        self.features_importer_enabled = features_importer_enabled

    def parse_and_validate_ontology(
        self,
        package_root: Path,
        manifest: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse and validate tags and affordances from ontology files.

        Returns:
            Tuple of (tags, affordances, import_log_entries) with normalized data and provenance.
        """
        if not self.features_importer_enabled:
            raise ImporterError("Importer feature flag is disabled (features.importer=false)")

        ontology_dir = package_root / "ontology"
        if not ontology_dir.exists():
            # Support existing fixture layout using plural directory name
            alt_dir = package_root / "ontologies"
            if alt_dir.exists():
                ontology_dir = alt_dir
        package_id = manifest.get("package_id", "unknown")
        manifest_hash = manifest.get("manifest_hash", "unknown")

        if not ontology_dir.exists():
            emit_structured_log(
                "ontology_parse_complete",
                package_id=package_id,
                tag_count=0,
                affordance_count=0,
                message="No ontology directory found",
            )
            # Emit zero metrics for consistency
            inc_counter("importer.tags.parsed", value=0, package_id=package_id)
            inc_counter("importer.affordances.parsed", value=0, package_id=package_id)
            return [], [], []

        tags = []
        affordances = []
        import_log_entries = []
        file_hash_cache = {}  # Cache file hashes for provenance

        # Process ontology files in deterministic order
        ontology_files: list[tuple[str, Path]] = []
        for file_path in ontology_dir.rglob("*.json"):
            rel_path = file_path.relative_to(package_root).as_posix()
            ontology_files.append((rel_path, file_path))

        ontology_files.sort()

        for rel_path, file_path in ontology_files:
            try:
                with open(file_path, encoding="utf-8") as handle:
                    content = handle.read()

                # Unicode normalization per ADR-0007
                normalized = unicodedata.normalize("NFC", content)
                payload = json.loads(normalized)

                # Compute file hash for provenance
                file_hash = self._compute_file_hash(normalized)
                file_hash_cache[rel_path] = file_hash

            except (json.JSONDecodeError, OSError) as exc:
                raise OntologyValidationError(
                    f"Failed to parse ontology file {rel_path}: {exc}"
                ) from exc

            # Extract tags and affordances from the payload
            file_tags = payload.get("tags", [])
            file_affordances = payload.get("affordances", [])

            # Validate and normalize each tag
            for tag_data in file_tags:
                normalized_tag = self._normalize_tag(tag_data, rel_path)
                self._validate_tag_schema(normalized_tag)
                # Add provenance data
                normalized_tag["provenance"] = {
                    "package_id": package_id,
                    "source_path": rel_path,
                    "file_hash": file_hash,
                }
                tags.append(normalized_tag)

            # Validate and normalize each affordance
            for affordance_data in file_affordances:
                normalized_affordance = self._normalize_affordance(affordance_data, rel_path)
                self._validate_affordance_schema(normalized_affordance)
                # Add provenance data
                normalized_affordance["provenance"] = {
                    "package_id": package_id,
                    "source_path": rel_path,
                    "file_hash": file_hash,
                }
                affordances.append(normalized_affordance)

        # Check for duplicates and conflicts automatically
        tag_skips, affordance_skips = self.check_for_duplicates_and_conflicts(
            tags, affordances, package_id
        )

        # Validate taxonomy invariants across all parsed data
        self._validate_taxonomy_invariants(tags, affordances)

        # Create ImportLog entries for unique items (after duplicate removal)
        unique_tags = self._filter_duplicates_from_list(tags)
        unique_affordances = self._filter_duplicates_from_list(affordances)

        for tag in unique_tags:
            import_log_entries.append(
                {
                    # sequence_no will be assigned by ImporterRunContext._merge_import_logs
                    "phase": "ontology",
                    "object_type": "tag",
                    "stable_id": tag["tag_id"],
                    "file_hash": tag["provenance"]["file_hash"],
                    "action": "created",
                    "manifest_hash": manifest_hash,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

        for affordance in unique_affordances:
            import_log_entries.append(
                {
                    # sequence_no will be assigned by ImporterRunContext._merge_import_logs
                    "phase": "ontology",
                    "object_type": "affordance",
                    "stable_id": affordance["affordance_id"],
                    "file_hash": affordance["provenance"]["file_hash"],
                    "action": "created",
                    "manifest_hash": manifest_hash,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

        emit_structured_log(
            "ontology_parse_complete",
            package_id=package_id,
            tag_count=len(unique_tags),
            affordance_count=len(unique_affordances),
            tag_skips=tag_skips,
            affordance_skips=affordance_skips,
        )

        # Emit metrics for parsed ontology items
        inc_counter("importer.tags.parsed", value=len(tags), package_id=package_id)
        inc_counter("importer.affordances.parsed", value=len(affordances), package_id=package_id)

        return unique_tags, unique_affordances, import_log_entries

    def _normalize_tag(self, tag_data: dict[str, Any], source_path: str) -> dict[str, Any]:
        """Normalize tag data with proper slug generation and validation."""
        # Copy to avoid mutating original
        normalized = dict(tag_data)

        # Normalize slug to lowercase with hyphens
        if "slug" in normalized:
            slug = str(normalized["slug"]).lower().replace("_", "-")
            normalized["slug"] = slug

        # Ensure required fields are present
        required_fields = [
            "tag_id",
            "category",
            "slug",
            "display_name",
            "synonyms",
            "audience",
            "gating",
        ]
        for field in required_fields:
            if field not in normalized:
                raise OntologyValidationError(
                    f"Missing required field '{field}' in tag from {source_path}"
                )

        # Normalize synonyms to lowercase
        if "synonyms" in normalized and isinstance(normalized["synonyms"], list):
            normalized["synonyms"] = [str(syn).lower() for syn in normalized["synonyms"]]

        return normalized

    def _normalize_affordance(
        self, affordance_data: dict[str, Any], source_path: str
    ) -> dict[str, Any]:
        """Normalize affordance data with proper slug generation and validation."""
        # Copy to avoid mutating original
        normalized = dict(affordance_data)

        # Normalize slug to lowercase with hyphens
        if "slug" in normalized:
            slug = str(normalized["slug"]).lower().replace("_", "-")
            normalized["slug"] = slug

        # Ensure required fields are present
        required_fields = ["affordance_id", "category", "slug", "applies_to", "gating"]
        for field in required_fields:
            if field not in normalized:
                raise OntologyValidationError(
                    f"Missing required field '{field}' in affordance from {source_path}"
                )

        return normalized

    def _validate_tag_schema(self, tag_data: dict[str, Any]) -> None:
        """Validate tag data against JSON schema if available."""
        try:
            import jsonschema  # type: ignore[import-untyped]
        except ImportError:
            return

        schema_path = Path("contracts/ontology/tag.v1.json")
        if not schema_path.exists():
            return

        try:
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        try:
            jsonschema.validate(tag_data, schema)
        except jsonschema.ValidationError as exc:
            raise OntologyValidationError(f"Tag validation failed: {exc.message}") from exc

    def _validate_affordance_schema(self, affordance_data: dict[str, Any]) -> None:
        """Validate affordance data against JSON schema if available."""
        try:
            import jsonschema  # type: ignore[import-untyped]
        except ImportError:
            return

        schema_path = Path("contracts/ontology/affordance.v1.json")
        if not schema_path.exists():
            return

        try:
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        try:
            jsonschema.validate(affordance_data, schema)
        except jsonschema.ValidationError as exc:
            raise OntologyValidationError(f"Affordance validation failed: {exc.message}") from exc

    def check_for_duplicates_and_conflicts(
        self,
        tags: list[dict[str, Any]],
        affordances: list[dict[str, Any]],
        package_id: str = "unknown",
    ) -> tuple[int, int]:
        """Check for duplicate/conflicting tags and affordances, returning skip counts.

        Implements ADR-0011 collision policy:
        - Identical hash: idempotent skip
        - Different hash: hard failure

        Returns:
            Tuple of (tag_skips, affordance_skips) for idempotent duplicates
        """
        from Adventorator.canonical_json import compute_canonical_hash

        tag_hashes: dict[str, bytes] = {}
        affordance_hashes: dict[str, bytes] = {}
        tag_skips = 0
        affordance_skips = 0

        # Check tags for duplicates/conflicts
        for tag in tags:
            key = (tag["tag_id"], tag["category"])
            # Exclude provenance from hash
            hash_data = {k: v for k, v in tag.items() if k != "provenance"}
            current_hash = compute_canonical_hash(hash_data)

            if key in tag_hashes:
                if tag_hashes[key] == current_hash:
                    # Identical duplicate - idempotent skip
                    tag_skips += 1
                    inc_counter("importer.tags.skipped_idempotent", value=1, package_id=package_id)
                    emit_structured_log(
                        "ontology_duplicate_skip",
                        type="tag",
                        tag_id=tag["tag_id"],
                        category=tag["category"],
                    )
                else:
                    # Conflicting definition - hard failure
                    raise OntologyValidationError(
                        f"Conflicting tag definition for {tag['tag_id']} "
                        f"in category {tag['category']}: "
                        f"existing hash {tag_hashes[key].hex()}, "
                        f"new hash {current_hash.hex()}"
                    )
            else:
                tag_hashes[key] = current_hash

        # Check affordances for duplicates/conflicts
        for affordance in affordances:
            key = (affordance["affordance_id"], affordance["category"])
            # Exclude provenance from hash
            hash_data = {k: v for k, v in affordance.items() if k != "provenance"}
            current_hash = compute_canonical_hash(hash_data)

            if key in affordance_hashes:
                if affordance_hashes[key] == current_hash:
                    # Identical duplicate - idempotent skip
                    affordance_skips += 1
                    inc_counter(
                        "importer.affordances.skipped_idempotent", value=1, package_id=package_id
                    )
                    emit_structured_log(
                        "ontology_duplicate_skip",
                        type="affordance",
                        affordance_id=affordance["affordance_id"],
                        category=affordance["category"],
                    )
                else:
                    # Conflicting definition - hard failure
                    raise OntologyValidationError(
                        f"Conflicting affordance definition for "
                        f"{affordance['affordance_id']} in category {affordance['category']}: "
                        f"existing hash {affordance_hashes[key].hex()}, "
                        f"new hash {current_hash.hex()}"
                    )
            else:
                affordance_hashes[key] = current_hash

        return tag_skips, affordance_skips

    def _compute_file_hash(self, content: str) -> str:
        """Compute SHA-256 hash of file content.

        Uses the same method as existing importer phases for consistency.

        Args:
            content: Normalized file content

        Returns:
            Hexadecimal SHA-256 hash string
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _filter_duplicates_from_list(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter duplicates from a list of tags or affordances, keeping first occurrence.

        Args:
            items: List of tag or affordance dictionaries

        Returns:
            List with duplicates removed (first occurrence kept)
        """
        from Adventorator.canonical_json import compute_canonical_hash

        seen_hashes = {}
        unique_items = []

        for item in items:
            # Determine the key based on item type
            if "tag_id" in item:
                key = (item["tag_id"], item["category"])
            else:
                key = (item["affordance_id"], item["category"])

            # Compute hash excluding provenance
            hash_data = {k: v for k, v in item.items() if k != "provenance"}
            item_hash = compute_canonical_hash(hash_data)

            if key not in seen_hashes or seen_hashes[key] == item_hash:
                if key not in seen_hashes:
                    unique_items.append(item)
                    seen_hashes[key] = item_hash
                # else: duplicate with same hash, skip

        return unique_items

    def _validate_taxonomy_invariants(
        self, tags: list[dict[str, Any]], affordances: list[dict[str, Any]]
    ) -> None:
        """Validate taxonomy invariants across all tags and affordances.

        Checks for category uniqueness and basic relationship consistency.

        Args:
            tags: List of normalized tag dictionaries
            affordances: List of normalized affordance dictionaries
        """
        # Check for duplicate (category, tag_id) combinations across files
        tag_keys = set()
        for tag in tags:
            key = (tag["category"], tag["tag_id"])
            if key in tag_keys:
                # This is caught by duplicate detection, but validate here for completeness
                pass  # Allow duplicate detection to handle this
            tag_keys.add(key)

        # Check for duplicate (category, affordance_id) combinations across files
        affordance_keys = set()
        for affordance in affordances:
            key = (affordance["category"], affordance["affordance_id"])
            if key in affordance_keys:
                # This is caught by duplicate detection, but validate here for completeness
                pass  # Allow duplicate detection to handle this
            affordance_keys.add(key)

        # Validate affordance references to tags
        tag_ids = {tag["tag_id"] for tag in tags}
        for affordance in affordances:
            for applies_to in affordance.get("applies_to", []):
                if applies_to.startswith("tag:"):
                    referenced_tag = applies_to[4:]  # Remove "tag:" prefix
                    if referenced_tag not in tag_ids:
                        # This is a warning rather than hard error for flexibility
                        emit_structured_log(
                            "ontology_reference_warning",
                            affordance_id=affordance["affordance_id"],
                            referenced_tag=referenced_tag,
                            message="Affordance references unknown tag",
                        )

    def emit_seed_events(
        self,
        tags: list[dict[str, Any]],
        affordances: list[dict[str, Any]],
        manifest: dict[str, Any],
    ) -> dict[str, int]:
        """Emit seed events for registered tags and affordances.

        Args:
            tags: List of tag dictionaries with provenance
            affordances: List of affordance dictionaries with provenance
            manifest: Manifest dictionary for version info

        Returns:
            Dictionary with event counts for metrics
        """
        package_id = manifest.get("package_id", "unknown")
        version = manifest.get("version", "1.0.0")

        # Sort by (category, tag_id/affordance_id) for deterministic ordering
        sorted_tags = sorted(tags, key=lambda t: (t["category"], t["tag_id"]))
        sorted_affordances = sorted(affordances, key=lambda a: (a["category"], a["affordance_id"]))

        tag_events = 0
        affordance_events = 0

        # Emit tag registration events
        for tag in sorted_tags:
            event_payload = {
                "tag_id": tag["tag_id"],
                "category": tag["category"],
                "version": version,
                "slug": tag["slug"],
                "display_name": tag["display_name"],
                "synonyms": tag["synonyms"],
                "audience": tag["audience"],
                "gating": tag["gating"],
            }

            # Add optional metadata
            if "metadata" in tag:
                event_payload["metadata"] = tag["metadata"]

            # Add provenance from tag data (now has real file hash)
            event_payload["provenance"] = tag["provenance"]

            emit_structured_log(
                "seed_event_emitted",
                event_type="seed.tag_registered",
                event_payload=event_payload,
            )
            inc_counter("importer.tags.registered", value=1, package_id=package_id)
            tag_events += 1

        # Emit affordance registration events
        for affordance in sorted_affordances:
            event_payload = {
                "affordance_id": affordance["affordance_id"],
                "category": affordance["category"],
                "version": version,
                "slug": affordance["slug"],
                "applies_to": affordance["applies_to"],
                "gating": affordance["gating"],
            }

            # Add optional metadata
            if "metadata" in affordance:
                event_payload["metadata"] = affordance["metadata"]

            # Add provenance from affordance data (now has real file hash)
            event_payload["provenance"] = affordance["provenance"]

            emit_structured_log(
                "seed_event_emitted",
                event_type="seed.affordance_registered",
                event_payload=event_payload,
            )
            inc_counter("importer.affordances.registered", value=1, package_id=package_id)
            affordance_events += 1

        return {"tag_events": tag_events, "affordance_events": affordance_events}


class LoreValidationError(ImporterError):
    """Exception raised when lore validation fails."""

    pass


class LoreCollisionError(ImporterError):
    """Exception raised when lore chunk collision is detected."""

    pass


class LorePhase:
    """Handles lore content chunking and ingestion phase of package import."""

    def __init__(
        self,
        features_importer_enabled: bool = False,
        features_importer_embeddings: bool = False,
    ):
        """Initialize lore phase.

        Args:
            features_importer_enabled: Whether importer feature flag is enabled
            features_importer_embeddings: Whether embedding metadata processing is enabled
        """
        self.features_importer_enabled = features_importer_enabled
        self.features_importer_embeddings = features_importer_embeddings

    def parse_and_validate_lore(
        self, package_root: Path, manifest: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Parse and validate all lore files in package.

        Args:
            package_root: Root directory of the package
            manifest: Validated package manifest

        Returns:
            List of parsed and validated chunk dictionaries with provenance

        Raises:
            ImporterError: If feature flag is disabled or validation fails
        """
        if not self.features_importer_enabled:
            raise ImporterError("Importer feature flag is disabled (features.importer=false)")

        from Adventorator.lore_chunker import LoreChunker, LoreChunkerError

        chunks: list[dict[str, Any]] = []
        package_id = manifest["package_id"]
        manifest_hash = manifest.get("manifest_hash", "unknown")
        content_index = manifest.get("content_index", {})

        # Find all lore files by scanning lore/ directory
        lore_dir = package_root / "lore"
        if not lore_dir.exists():
            emit_structured_log(
                "lore_parse_complete",
                package_id=package_id,
                chunk_count=0,
                message="No lore directory found",
            )
            return chunks

        # Initialize chunker with feature flags
        chunker = LoreChunker(features_importer_embeddings=self.features_importer_embeddings)

        lore_files = []
        for file_path in lore_dir.rglob("*.md"):
            rel_path = file_path.relative_to(package_root).as_posix()
            lore_files.append((rel_path, file_path))

        # Sort deterministically by path
        lore_files.sort()

        collisions_detected = 0
        chunks_skipped_idempotent = 0

        for rel_path, file_path in lore_files:
            try:
                # Parse file into chunks
                file_chunks = chunker.parse_lore_file(file_path, package_id, manifest_hash)

                for chunk in file_chunks:
                    # Update source_path to be relative to package root
                    chunk.source_path = rel_path
                    chunk.provenance["source_path"] = rel_path

                    # Verify against content index if present
                    if rel_path in content_index:
                        expected_hash = content_index[rel_path]
                        if chunk.provenance["file_hash"] != expected_hash:
                            raise LoreValidationError(
                                f"File hash mismatch for {rel_path}: "
                                f"expected {expected_hash}, got {chunk.provenance['file_hash']}"
                            )

                    # Convert to dictionary for processing
                    chunk_dict = {
                        "chunk_id": chunk.chunk_id,
                        "title": chunk.title,
                        "audience": chunk.audience,
                        "tags": chunk.tags,
                        "content": chunk.content,
                        "source_path": chunk.source_path,
                        "chunk_index": chunk.chunk_index,
                        "content_hash": chunk.content_hash,
                        "word_count": chunk.word_count,
                        "provenance": chunk.provenance,
                    }

                    # Include embedding_hint if present
                    if chunk.embedding_hint is not None:
                        chunk_dict["embedding_hint"] = chunk.embedding_hint

                    chunks.append(chunk_dict)

            except LoreChunkerError as exc:
                raise LoreValidationError(f"Failed to parse lore file {rel_path}: {exc}") from exc

        # Sort chunks deterministically by (source_path, chunk_index)
        chunks.sort(key=lambda c: (c["source_path"], c["chunk_index"]))

        # Check for chunk_id collisions and filter duplicates
        try:
            filtered_chunks, chunks_skipped_idempotent = self._check_chunk_id_collisions(chunks)
        except LoreCollisionError as exc:
            collisions_detected = 1
            inc_counter("importer.collision", value=1, package_id=package_id)
            # Record rollback metrics and logs
            record_rollback("lore", package_id, manifest_hash, str(exc))
            raise exc

        # Create ImportLog entries for each chunk and assign them individually
        for i, chunk in enumerate(filtered_chunks):
            import_log_entry = {
                # sequence_no will be assigned by ImporterRunContext._merge_import_logs
                "phase": "lore",
                "object_type": "content_chunk",
                "stable_id": chunk["chunk_id"],
                "file_hash": chunk["content_hash"],
                "action": "ingested",
                "manifest_hash": manifest_hash,
                "timestamp": datetime.now(timezone.utc),
            }
            # Each chunk gets only its own ImportLog entry
            chunk["import_log_entries"] = [import_log_entry]

        # Emit metrics with actual counts
        chunk_count = len(filtered_chunks)
        inc_counter("importer.chunks.ingested", value=chunk_count, package_id=package_id)
        if chunks_skipped_idempotent > 0:
            inc_counter(
                "importer.chunks.skipped_idempotent",
                value=chunks_skipped_idempotent,
                package_id=package_id,
            )

        # Log summary
        emit_structured_log(
            "lore_parse_complete",
            package_id=package_id,
            chunk_count=chunk_count,
            collisions_detected=collisions_detected,
            chunks_skipped_idempotent=chunks_skipped_idempotent,
        )

        # Create seed events for successfully parsed chunks and attach to chunk records
        seed_events = self.create_seed_events(filtered_chunks)
        
        # Attach event payloads to chunk records for database persistence
        for i, chunk in enumerate(filtered_chunks):
            if i < len(seed_events):
                chunk["event_payload"] = seed_events[i]

        return filtered_chunks

    def _check_chunk_id_collisions(
        self, chunks: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        """Check for chunk_id collisions and filter duplicates for idempotent replay.

        Args:
            chunks: List of parsed chunks

        Returns:
            Tuple of (filtered_chunks, skipped_count)

        Raises:
            LoreCollisionError: If collisions are detected
        """
        seen_ids: dict[str, tuple[str, str]] = {}
        filtered_chunks = []
        skipped_count = 0

        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            content_hash = chunk["content_hash"]
            source_path = chunk["source_path"]

            if chunk_id in seen_ids:
                existing_hash, existing_path = seen_ids[chunk_id]
                if content_hash != existing_hash:
                    raise LoreCollisionError(
                        f"Chunk ID collision detected for '{chunk_id}': "
                        f"different content in {existing_path} vs {source_path}"
                    )
                # Same hash = idempotent duplicate, skip it
                skipped_count += 1
            else:
                seen_ids[chunk_id] = (content_hash, source_path)
                filtered_chunks.append(chunk)

        return filtered_chunks, skipped_count

    def create_seed_events(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create seed.content_chunk_ingested events for parsed chunks.

        Args:
            chunks: List of validated chunks with provenance

        Returns:
            List of event payloads for seed.content_chunk_ingested events
        """
        events = []
        for chunk in chunks:
            # Create event payload (all fields already validated)
            event_payload = {
                "chunk_id": chunk["chunk_id"],
                "title": chunk["title"],
                "audience": chunk["audience"],
                "tags": sorted(chunk["tags"]),  # Canonical ordering
                "source_path": chunk["source_path"],
                "content_hash": chunk["content_hash"],
                "chunk_index": chunk["chunk_index"],
                "word_count": chunk["word_count"],
                "provenance": chunk["provenance"],
            }

            # Include embedding_hint if present
            if "embedding_hint" in chunk:
                event_payload["embedding_hint"] = chunk["embedding_hint"]

            # Validate event payload against schema
            validate_event_payload_schema(event_payload, event_type="content_chunk")

            events.append(event_payload)

        return events


class FinalizationPhase:
    """Handles importer finalization, completion events, and state digest computation."""

    def __init__(self, features_importer_enabled: bool = False):
        """Initialize finalization phase.
        
        Args:
            features_importer_enabled: Whether importer features are enabled.
        """
        self.features_importer_enabled = features_importer_enabled

    def finalize_import(self, context, start_time: datetime) -> dict[str, Any]:
        """Finalize import by emitting completion event and computing final state.
        
        Args:
            context: ImporterRunContext with aggregated phase outputs
            start_time: Import start timestamp for duration calculation
            
        Returns:
            Finalization result with completion event and ImportLog summary
        """
        if not self.features_importer_enabled:
            emit_structured_log("finalization_skipped", reason="features_importer_disabled")
            return {"skipped": True}

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Get counts from context
        counts = context.summary_counts()
        
        # Compute state digest
        state_digest = context.compute_state_digest()
        
        # Check if this was an idempotent re-run by looking at the current run metrics
        # We'll detect this by seeing if any skipped_idempotent counters were incremented during this run
        current_entities_skipped = get_counter("importer.entities.skipped_idempotent") 
        current_edges_skipped = get_counter("importer.edges.skipped_idempotent")
        current_tags_skipped = get_counter("importer.tags.skipped_idempotent")
        current_chunks_skipped = get_counter("importer.chunks.skipped_idempotent")
        
        # Calculate total skips for this run
        total_skips = current_entities_skipped + current_edges_skipped + current_tags_skipped + current_chunks_skipped
        
        if total_skips > 0:
            # This appears to be an idempotent re-run
            record_idempotent_run(context.package_id, context.manifest_hash)
            # Note: record_idempotent_run already increments importer.idempotent counter
        
        # Ensure required fields are present
        if context.package_id is None:
            raise ValueError("Missing required field: package_id")
        if context.manifest_hash is None:
            raise ValueError("Missing required field: manifest_hash")

        # Create completion event payload
        completion_payload = {
            "package_id": context.package_id,
            "manifest_hash": context.manifest_hash,
            "entity_count": counts["entities"],
            "edge_count": counts["edges"], 
            "tag_count": counts["tags"],
            "affordance_count": counts["affordances"],
            "chunk_count": counts["chunks"],
            "state_digest": state_digest,
            "import_duration_ms": duration_ms,
        }

        # Add warnings if any (placeholder for future warning collection)
        warnings = []
        if warnings:
            completion_payload["warnings"] = warnings

        # Emit completion event
        completion_event = self._emit_completion_event(completion_payload)
        
        # Create ImportLog summary entry
        import_log_summary = self._create_import_log_summary(
            context, state_digest, duration_ms
        )
        
        # Emit structured log with final summary
        emit_structured_log(
            "import_finalization_complete",
            package_id=context.package_id,
            manifest_hash=context.manifest_hash,
            entity_count=counts["entities"],
            edge_count=counts["edges"],
            tag_count=counts["tags"],
            affordance_count=counts["affordances"], 
            chunk_count=counts["chunks"],
            state_digest=state_digest,
            duration_ms=duration_ms,
        )
        
        # Record duration metric as histogram
        observe_histogram("importer.duration_ms", duration_ms)
        
        return {
            "completion_event": completion_event,
            "import_log_summary": import_log_summary,
            "state_digest": state_digest,
            "duration_ms": duration_ms,
        }

    def _emit_completion_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Emit seed.import.complete event.
        
        Args:
            payload: Event payload
            
        Returns:
            Event envelope dict
        """
        event_envelope = {
            "event_type": "seed.import.complete",
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "replay_ordinal": None,  # Would be assigned by event ledger
            "idempotency_key": None,  # Would be computed by event ledger
        }
        
        emit_structured_log(
            "seed_event_emitted",
            event_type="seed.import.complete",
            package_id=payload.get("package_id"),
            manifest_hash=payload.get("manifest_hash"),
        )
        
        return event_envelope

    def _create_import_log_summary(
        self, context, state_digest: str, duration_ms: int
    ) -> dict[str, Any]:
        """Create ImportLog summary entry.
        
        Args:
            context: ImporterRunContext with phase data
            state_digest: Computed state digest
            duration_ms: Import duration
            
        Returns:
            ImportLog summary entry dict
        """
        import_logs = context.import_log_entries
        
        # Find the highest sequence number across all phases
        max_sequence = 0
        if import_logs:
            max_sequence = max(
                entry.get("sequence_no", 0) 
                for entry in import_logs 
                if isinstance(entry.get("sequence_no"), int)
            )
        
        # Verify sequence contiguity and enforce "no gaps" requirement
        sequences = [
            entry.get("sequence_no") for entry in import_logs 
            if isinstance(entry.get("sequence_no"), int)
        ]
        if sequences:
            sequences.sort()
            expected_sequences = list(range(1, len(sequences) + 1))
            if sequences != expected_sequences:
                emit_structured_log(
                    "import_log_sequence_gap_detected",
                    expected=expected_sequences,
                    actual=sequences,
                    package_id=context.package_id,
                )
                # Enforce contiguity requirement - raise error for any sequence mismatch
                raise ImporterError(
                    f"ImportLog sequence gaps detected in package {context.package_id}: "
                    f"expected {expected_sequences}, actual {sequences}"
                )
        
        summary_entry = {
            "phase": "finalization",
            "object_type": "summary",
            "stable_id": f"summary-{context.package_id}",
            "file_hash": state_digest,  # Use state digest as summary hash
            "action": "completed",
            "manifest_hash": context.manifest_hash or "",
            "sequence_no": max_sequence + 1,
            "metadata": {
                "state_digest": state_digest,
                "duration_ms": duration_ms,
                "total_entries": len(import_logs),
            },
        }
        
        return summary_entry


def create_lore_phase(
    features_importer: bool = False, features_importer_embeddings: bool = False
) -> LorePhase:
    """Factory function to create lore phase with feature flags.

    Args:
        features_importer: Value of features.importer feature flag
        features_importer_embeddings: Value of features.importer_embeddings feature flag

    Returns:
        Configured LorePhase instance
    """
    return LorePhase(
        features_importer_enabled=features_importer,
        features_importer_embeddings=features_importer_embeddings,
    )


def create_finalization_phase(features_importer: bool = False) -> FinalizationPhase:
    """Factory function to create finalization phase with feature flags.

    Args:
        features_importer: Value of features.importer feature flag

    Returns:
        Configured FinalizationPhase instance
    """
    return FinalizationPhase(features_importer_enabled=features_importer)


async def run_full_import_with_database(
    package_root: Path,
    campaign_id: int,
    *,
    features_importer: bool = False,
    features_importer_embeddings: bool = False
) -> dict[str, Any]:
    """Run full package import with database integration and idempotent detection.
    
    This function integrates the importer phases with the database layer,
    ensuring that Events and ImportLog entries are actually persisted.
    Implements proper idempotent behavior by checking for existing imports.
    
    Args:
        package_root: Root directory of the package to import
        campaign_id: Campaign ID to import into
        features_importer: Whether importer is enabled
        features_importer_embeddings: Whether embeddings are enabled
        
    Returns:
        Dictionary containing import results and database state
        
    Raises:
        ImporterError: If import fails
    """
    start_time = datetime.now(timezone.utc)
    
    async with session_scope() as session:
        try:
            # Load and validate manifest first for idempotent detection
            manifest_path = package_root / "package.manifest.json"
            if not manifest_path.exists():
                raise ImporterError(f"Manifest not found: {manifest_path}")
                
            with open(manifest_path, encoding="utf-8") as f:
                manifest_data = json.load(f)
            
            package_id = manifest_data.get("package_id")
            if not package_id:
                raise ImporterError("Missing package_id in manifest")
                
            # Compute manifest hash using canonical JSON helper
            from Adventorator.manifest_validation import compute_manifest_hash
            manifest_hash = compute_manifest_hash(manifest_data)
            
            # Attach manifest hash to manifest dict for reuse
            manifest_data["manifest_hash"] = manifest_hash
            
            # Check for existing import with same manifest hash
            from sqlalchemy import select
            existing_events = await session.execute(
                select(models.Event)
                .where(models.Event.campaign_id == campaign_id)
                .where(models.Event.type == "seed.import.complete")
                .where(models.Event.payload.contains({"manifest_hash": manifest_hash}))
            )
            
            existing_import = existing_events.scalars().first()
            
            if existing_import:
                # This is an idempotent re-run - return existing results without creating new import records (but metrics/logs are still recorded for observability)
                record_idempotent_run(package_id, manifest_hash)
                
                # Get existing import summary from the completion event
                completion_payload = existing_import.payload
                existing_state_digest = completion_payload.get("state_digest", "")
                
                # Get all events for this import
                all_events_query = await session.execute(
                    select(models.Event)
                    .where(models.Event.campaign_id == campaign_id)
                    .order_by(models.Event.replay_ordinal)
                )
                events = all_events_query.scalars().all()
                
                # Get all ImportLog entries for this import
                import_logs_query = await session.execute(
                    select(models.ImportLog)
                    .where(models.ImportLog.campaign_id == campaign_id)
                    .where(models.ImportLog.manifest_hash == manifest_hash)
                )
                import_logs = import_logs_query.scalars().all()
                
                # Compute hash chain tip
                hash_chain_tip = None
                if events:
                    from Adventorator.events import envelope as event_envelope
                    last_event = events[-1]
                    hash_chain_tip = event_envelope.compute_envelope_hash(
                        campaign_id=last_event.campaign_id,
                        scene_id=last_event.scene_id,
                        replay_ordinal=last_event.replay_ordinal,
                        event_type=last_event.type,
                        event_schema_version=last_event.event_schema_version,
                        world_time=last_event.world_time,
                        wall_time_utc=last_event.wall_time_utc,
                        prev_event_hash=last_event.prev_event_hash,
                        payload_hash=last_event.payload_hash,
                        idempotency_key=last_event.idempotency_key,
                    ).hex()
                
                emit_structured_log(
                    "import_idempotent_run",
                    package_id=package_id,
                    manifest_hash=manifest_hash,
                    outcome="idempotent_skip",
                    events_count=len(events),
                    import_log_entries=len(import_logs)
                )
                
                return {
                    "state_digest": existing_state_digest,
                    "completion_payload": completion_payload,
                    "completion_event": {"payload": completion_payload},
                    "import_log_summary": {
                        "phase": "finalization",
                        "object_type": "import",
                        "stable_id": package_id,
                        "action": "completed",
                        "manifest_hash": manifest_hash
                    },
                    "database_state": {
                        "events": [
                            {
                                "id": e.id,
                                "replay_ordinal": e.replay_ordinal,
                                "type": e.type,
                                "payload": e.payload,
                                "prev_event_hash": e.prev_event_hash.hex(),
                                "payload_hash": e.payload_hash.hex(),
                                "idempotency_key": e.idempotency_key.hex(),
                            }
                            for e in events
                        ],
                        "import_logs": [
                            {
                                "id": il.id,
                                "sequence_no": il.sequence_no,
                                "phase": il.phase,
                                "object_type": il.object_type,
                                "stable_id": il.stable_id,
                                "action": il.action,
                                "file_hash": il.file_hash,
                                "manifest_hash": il.manifest_hash,
                            }
                            for il in import_logs
                        ],
                        "hash_chain_tip": hash_chain_tip,
                        "event_count": len(events),
                        "import_log_count": len(import_logs),
                    },
                    "idempotent_skip": True,
                    "duration_ms": 0  # No work done for idempotent skip
                }
                
            # Proceed with new import since no existing import was found
            # Initialize phases
            manifest_phase = ManifestPhase(features_importer_enabled=features_importer)
            entity_phase = EntityPhase(features_importer_enabled=features_importer)
            edge_phase = EdgePhase(features_importer_enabled=features_importer)
            ontology_phase = OntologyPhase(features_importer_enabled=features_importer)
            lore_phase = create_lore_phase(features_importer, features_importer_embeddings)
            finalization_phase = FinalizationPhase(features_importer_enabled=features_importer)
            
            context = ImporterRunContext()
            manifest_path = package_root / "package.manifest.json"
            
            # Manifest validation and event emission
            manifest_result = manifest_phase.validate_and_register(manifest_path, package_root)
            context.record_manifest(manifest_result)
            
            # Emit manifest validation event to database
            manifest_event = await persist_import_event(
                session, campaign_id, None,
                "seed.manifest.validated",
                manifest_result["event_payload"]
            )
            
            # Persist manifest ImportLog entry
            manifest_log_entry = manifest_result["import_log_entry"].copy()
            manifest_log_entry["sequence_no"] = context.next_sequence_number()
            await persist_import_log_entry(session, campaign_id, manifest_log_entry)
            
            # Entity ingestion
            entities_dir = package_root / "entities"
            if entities_dir.exists():
                entity_results = entity_phase.parse_and_validate_entities(package_root, manifest_result["manifest"])
                context.record_entities(entity_results)
                
                # Emit entity events and persist ImportLog entries
                for entity in entity_results:
                    if "event_payload" in entity:
                        await persist_import_event(
                            session, campaign_id, None,
                            "seed.entity_created",
                            entity["event_payload"]
                        )
                    
                    # Persist ImportLog entry for this entity
                    if "import_log_entry" in entity:
                        log_entry_copy = entity["import_log_entry"].copy()
                        log_entry_copy["sequence_no"] = context.next_sequence_number()
                        await persist_import_log_entry(session, campaign_id, log_entry_copy)
            
            # Edge ingestion  
            edges_dir = package_root / "edges"
            if edges_dir.exists():
                edge_results = edge_phase.parse_and_validate_edges(package_root, manifest_result["manifest"], entity_results)
                context.record_edges(edge_results)
                
                # Emit edge events and persist ImportLog entries
                for edge in edge_results:
                    if "event_payload" in edge:
                        await persist_import_event(
                            session, campaign_id, None,
                            "seed.edge_created",
                            edge["event_payload"]
                        )
                    
                    if "import_log_entry" in edge:
                        log_entry_copy = edge["import_log_entry"].copy()
                        log_entry_copy["sequence_no"] = context.next_sequence_number()
                        await persist_import_log_entry(session, campaign_id, log_entry_copy)
            
            # Ontology ingestion
            ontology_dir = package_root / "ontology"
            if ontology_dir.exists():
                tags, affordances, import_log_entries = ontology_phase.parse_and_validate_ontology(package_root, manifest_result["manifest"])
                context.record_ontology(tags, affordances, import_log_entries)
                
                # Persist ontology ImportLog entries
                for log_entry in import_log_entries:
                    log_entry_copy = log_entry.copy()
                    log_entry_copy["sequence_no"] = context.next_sequence_number()
                    await persist_import_log_entry(session, campaign_id, log_entry_copy)
            else:
                # Record empty ontology phase for completeness
                empty_log_entry = {
                    "sequence_no": context.next_sequence_number(),
                    "phase": "ontology",
                    "object_type": "phase_complete",
                    "stable_id": "N/A",
                    "action": "skipped_no_directory",
                    "file_hash": "N/A",
                    "manifest_hash": manifest_result.get("manifest_hash", "unknown"),
                    "timestamp": datetime.now(timezone.utc),
                }
                await persist_import_log_entry(session, campaign_id, empty_log_entry)
            
            # Lore ingestion
            lore_dir = package_root / "lore"
            if lore_dir.exists():
                lore_results = lore_phase.parse_and_validate_lore(package_root, manifest_result["manifest"])
                context.record_lore_chunks(lore_results)
                
                # Emit lore events and persist ImportLog entries
                for chunk in lore_results:
                    if "event_payload" in chunk:
                        await persist_import_event(
                            session, campaign_id, None,
                            "seed.lore_chunk_created",
                            chunk["event_payload"]
                        )
                    
                    if "import_log_entry" in chunk:
                        log_entry_copy = chunk["import_log_entry"].copy()
                        log_entry_copy["sequence_no"] = context.next_sequence_number()
                        await persist_import_log_entry(session, campaign_id, log_entry_copy)
            else:
                # Record empty lore phase for completeness
                empty_log_entry = {
                    "sequence_no": context.next_sequence_number(),
                    "phase": "lore",
                    "object_type": "phase_complete",
                    "stable_id": "N/A",
                    "action": "skipped_no_directory",
                    "file_hash": "N/A",
                    "manifest_hash": manifest_result.get("manifest_hash", "unknown"),
                    "timestamp": datetime.now(timezone.utc),
                }
                await persist_import_log_entry(session, campaign_id, empty_log_entry)
            
            # Finalization
            result = finalization_phase.finalize_import(context, start_time)
            
            # Emit completion event
            completion_event = await persist_import_event(
                session, campaign_id, None,
                "seed.import.complete",
                result["completion_event"]["payload"]
            )
            
            # Persist finalization ImportLog summary
            summary_entry = result["import_log_summary"].copy()
            summary_entry["sequence_no"] = context.next_sequence_number()
            await persist_import_log_entry(session, campaign_id, summary_entry)
            
            # Query final database state for validation
            from sqlalchemy import select, func
            
            # Get all events for this campaign
            events_query = await session.execute(
                select(models.Event)
                .where(models.Event.campaign_id == campaign_id)
                .order_by(models.Event.replay_ordinal)
            )
            events = events_query.scalars().all()
            
            # Get all ImportLog entries for this campaign
            import_logs_query = await session.execute(
                select(models.ImportLog)
                .where(models.ImportLog.campaign_id == campaign_id)
                .order_by(models.ImportLog.sequence_no)
            )
            import_logs = import_logs_query.scalars().all()
            
            # Get hash chain tip (last event hash)
            hash_chain_tip = None
            if events:
                from Adventorator.events import envelope as event_envelope
                last_event = events[-1]
                hash_chain_tip = event_envelope.compute_envelope_hash(
                    campaign_id=last_event.campaign_id,
                    scene_id=last_event.scene_id,
                    replay_ordinal=last_event.replay_ordinal,
                    event_type=last_event.type,
                    event_schema_version=last_event.event_schema_version,
                    world_time=last_event.world_time,
                    wall_time_utc=last_event.wall_time_utc,
                    prev_event_hash=last_event.prev_event_hash,
                    payload_hash=last_event.payload_hash,
                    idempotency_key=last_event.idempotency_key,
                ).hex()
            
            # Commit all changes
            await session.commit()
            
            # Return comprehensive results including database state
            return {
                **result,
                "database_state": {
                    "events": [
                        {
                            "id": e.id,
                            "replay_ordinal": e.replay_ordinal,
                            "type": e.type,
                            "payload": e.payload,
                            "prev_event_hash": e.prev_event_hash.hex(),
                            "payload_hash": e.payload_hash.hex(),
                            "idempotency_key": e.idempotency_key.hex(),
                        }
                        for e in events
                    ],
                    "import_logs": [
                        {
                            "id": il.id,
                            "sequence_no": il.sequence_no,
                            "phase": il.phase,
                            "object_type": il.object_type,
                            "stable_id": il.stable_id,
                            "action": il.action,
                            "file_hash": il.file_hash,
                            "manifest_hash": il.manifest_hash,
                        }
                        for il in import_logs
                    ],
                    "hash_chain_tip": hash_chain_tip,
                    "event_count": len(events),
                    "import_log_count": len(import_logs),
                },
                "hash_chain_tip": hash_chain_tip,
            }
            
        except Exception as e:
            await session.rollback()
            raise ImporterError(f"Database import failed: {e}") from e


def run_complete_import_pipeline(
    package_root: Path, 
    features_importer: bool = False, 
    features_importer_embeddings: bool = False
) -> dict[str, Any]:
    """Run the complete import pipeline with finalization.
    
    This provides a production call site that demonstrates how the finalization
    phase integrates with the broader importer flow.
    
    Args:
        package_root: Root directory containing package files
        features_importer: Whether importer features are enabled
        features_importer_embeddings: Whether embedding features are enabled
        
    Returns:
        Complete import result including finalization output
    """
    from datetime import datetime, timezone
    from pathlib import Path
    
    from Adventorator.importer_context import ImporterRunContext
    
    # Initialize context
    context = ImporterRunContext()
    start_time = datetime.now(timezone.utc)
    
    # Manifest phase
    manifest_phase = ManifestPhase(features_importer_enabled=features_importer)
    manifest_path = package_root / "package.manifest.json"
    manifest_result = manifest_phase.validate_and_register(manifest_path, package_root)
    
    # Add sequence number to manifest ImportLog entry
    if "import_log_entry" in manifest_result:
        manifest_result["import_log_entry"]["sequence_no"] = context.next_sequence_number()
        manifest_result["import_log_entry"]["manifest_hash"] = manifest_result["manifest_hash"]
    
    context.record_manifest(manifest_result)
    
    manifest_with_hash = dict(manifest_result["manifest"])
    manifest_with_hash["manifest_hash"] = manifest_result["manifest_hash"]
    
    # Entity phase
    entity_phase = EntityPhase(features_importer_enabled=features_importer)
    entities = entity_phase.parse_and_validate_entities(package_root, manifest_with_hash)
    
    # Fix sequence numbers for entity ImportLog entries
    for entity in entities:
        import_log_entries = entity.get("import_log_entries", [])
        for entry in import_log_entries:
            entry["sequence_no"] = context.next_sequence_number()
    
    context.record_entities(entities)
    
    # Edge phase
    edge_phase = EdgePhase(features_importer_enabled=features_importer)
    edges = edge_phase.parse_and_validate_edges(package_root, manifest_with_hash, entities)
    
    # Fix sequence numbers for edge ImportLog entries
    for edge in edges:
        import_log_entry = edge.get("import_log_entry")
        if import_log_entry:
            import_log_entry["sequence_no"] = context.next_sequence_number()
    
    context.record_edges(edges)
    
    # Ontology phase
    ontology_phase = OntologyPhase(features_importer_enabled=features_importer)
    tags, affordances, ontology_logs = ontology_phase.parse_and_validate_ontology(
        package_root, manifest_with_hash
    )
    
    # Fix sequence numbers for ontology ImportLog entries
    for entry in ontology_logs:
        entry["sequence_no"] = context.next_sequence_number()
    
    context.record_ontology(tags, affordances, ontology_logs)
    
    # Lore phase
    lore_phase = create_lore_phase(features_importer, features_importer_embeddings)
    chunks = lore_phase.parse_and_validate_lore(package_root, manifest_with_hash)
    
    # Fix sequence numbers for lore ImportLog entries
    for chunk in chunks:
        import_log_entries = chunk.get("import_log_entries", [])
        for entry in import_log_entries:
            entry["sequence_no"] = context.next_sequence_number()
    
    context.record_lore_chunks(chunks)
    
    # Finalization phase
    finalization_phase = create_finalization_phase(features_importer)
    finalization_result = finalization_phase.finalize_import(context, start_time)
    
    return {
        "manifest_result": manifest_result,
        "entities": entities,
        "edges": edges,
        "tags": tags,
        "affordances": affordances,
        "chunks": chunks,
        "finalization": finalization_result,
        "context": context,
    }


__all__ = [
    "ManifestPhase",
    "EntityPhase", 
    "EdgePhase",
    "OntologyPhase",
    "LorePhase",
    "FinalizationPhase",
    "create_lore_phase",
    "create_finalization_phase",
    "run_complete_import_pipeline",
    "ImporterError",
    "ManifestValidationError",
    "EntityValidationError",
    "EdgeValidationError", 
    "OntologyValidationError",
]
