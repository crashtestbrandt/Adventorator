"""Transaction rollback tests for package importer (STORY-CDA-IMPORT-002G).

Tests validate importer failure handling by injecting failures mid-phase and
ensuring transactional rollback leaves no partial events or ImportLog rows
per ARCH-CDA-001 and ADR-0011.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from Adventorator.importer import (
    EdgePhase,
    EntityCollisionError,
    EntityPhase,
    ImporterError,
    LoreCollisionError,
    LorePhase,
    ManifestPhase,
    OntologyPhase,
)
from Adventorator.importer_context import ImporterRunContext
from Adventorator.manifest_validation import ManifestValidationError
from Adventorator.metrics import get_counter, reset_counters


class FailureInjectionHarness:
    """Utility for injecting targeted failure scenarios during import phases.
    
    TASK-CDA-IMPORT-FAIL-20A: Failure injection harness.
    Enables testing of entity collision, missing file, invalid YAML scenarios.
    """
    
    @staticmethod
    def create_collision_package(package_root: Path):
        """Create package with entity ID collision for testing."""
        (package_root / "entities").mkdir(parents=True)
        
        # Create manifest
        manifest_data = {
            "package_id": "01JCOLLISION000000000000001",
            "schema_version": 1,
            "engine_contract_range": {"min": "1.0.0", "max": "2.0.0"},
            "dependencies": [],
            "content_index": {},
            "ruleset_version": "1.0.0",
            "recommended_flags": {"features.importer.entities": True},
            "signatures": []
        }
        
        with open(package_root / "package.manifest.json", "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        # Create two entities with SAME stable_id but DIFFERENT content (collision)
        entity1_data = {
            "stable_id": "01JCOLLIDE0000000000000001",  # Same ID - 26 chars (ULID format) 
            "kind": "npc",
            "name": "Original Entity",
            "tags": ["original"],
            "affordances": [],
            "traits": [],
            "props": {"version": "original"}
        }
        
        entity2_data = {
            "stable_id": "01JCOLLIDE0000000000000001",  # Same ID, different content - 26 chars
            "kind": "npc", 
            "name": "Conflicting Entity",
            "tags": ["conflicting"],
            "affordances": [], 
            "traits": [],
            "props": {"version": "conflicting"}
        }
        
        with open(package_root / "entities" / "entity1.json", "w") as f:
            json.dump(entity1_data, f, indent=2)
            
        with open(package_root / "entities" / "entity2.json", "w") as f:
            json.dump(entity2_data, f, indent=2)

    @staticmethod
    def create_missing_dependency_package(package_root: Path):
        """Create package with missing dependency file for testing."""
        (package_root / "entities").mkdir(parents=True)
        
        # Manifest references non-existent file
        manifest_data = {
            "package_id": "01JMISSING0000000000000001",
            "schema_version": 1,
            "engine_contract_range": {"min": "1.0.0", "max": "2.0.0"},
            "dependencies": [],
            "content_index": {
                "entities/missing.json": "0000000000000000000000000000000000000000000000000000000000000000"
            },
            "ruleset_version": "1.0.0",
            "recommended_flags": {"features.importer.entities": True},
            "signatures": []
        }
        
        with open(package_root / "package.manifest.json", "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        # Note: entities/missing.json is NOT created, causing validation failure

    @staticmethod  
    def create_invalid_schema_package(package_root: Path):
        """Create package with invalid JSON schema for testing."""
        (package_root / "entities").mkdir(parents=True)
        
        # Valid manifest
        manifest_data = {
            "package_id": "01JINVALID0000000000000001",
            "schema_version": 1,
            "engine_contract_range": {"min": "1.0.0", "max": "2.0.0"},
            "dependencies": [],
            "content_index": {},
            "ruleset_version": "1.0.0",
            "recommended_flags": {"features.importer.entities": True},
            "signatures": []
        }
        
        with open(package_root / "package.manifest.json", "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        # Invalid entity (missing required fields)
        invalid_entity_data = {
            "stable_id": "01JINVALID0ENTITY00000001",
            # Missing required 'kind' field
            "name": "Invalid Entity",
            "tags": []
        }
        
        with open(package_root / "entities" / "invalid.json", "w") as f:
            json.dump(invalid_entity_data, f, indent=2)


class TestImporterRollback:
    """Test transaction rollback behavior per TASK-CDA-IMPORT-FAIL-20B."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        reset_counters()

    def test_entity_collision_rollback(self):
        """Test that entity collision during import rolls back transaction cleanly.
        
        Should assert:
        - DB state unchanged post-failure
        - ImportLog unchanged post-failure  
        - Metrics unchanged post-failure
        - Log assertions for rollback notice
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_collision_package(package_root)
            
            # Capture initial state
            initial_entities_counter = get_counter("importer.entities.ingested")
            initial_collisions_counter = get_counter("importer.entities.collisions")
            
            # Attempt import - should fail with collision
            with pytest.raises(EntityCollisionError, match="collision"):
                self._run_import_expecting_failure(package_root)
            
            # Verify rollback metrics
            post_failure_entities_counter = get_counter("importer.entities.ingested")
            post_failure_collisions_counter = get_counter("importer.entities.collisions")
            
            # No entities should be successfully ingested
            assert post_failure_entities_counter == initial_entities_counter, \
                "No entities should be ingested after collision failure"
            
            # Collision should be detected and counted
            assert post_failure_collisions_counter > initial_collisions_counter, \
                "Collision counter should increment when collision detected"
            
            # Verify rollback counter incremented
            assert get_counter("importer.rollback") > 0, \
                "Rollback counter should increment on transaction rollback"

    def test_missing_file_rollback(self):
        """Test that missing dependency file causes proper rollback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_missing_dependency_package(package_root)
            
            initial_entities_counter = get_counter("importer.entities.ingested")
            
            # Should fail during manifest validation
            with pytest.raises((ImporterError, ManifestValidationError)):
                self._run_import_expecting_failure(package_root)
            
            # Verify no partial state created
            assert get_counter("importer.entities.ingested") == initial_entities_counter, \
                "No entities should be created when manifest validation fails" 
            
            # Verify rollback counter incremented
            assert get_counter("importer.rollback") > 0, \
                "Rollback counter should increment on validation failure"

    def test_invalid_schema_rollback(self):
        """Test that invalid JSON schema causes proper rollback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)  
            FailureInjectionHarness.create_invalid_schema_package(package_root)
            
            initial_entities_counter = get_counter("importer.entities.ingested")
            
            # Should fail during entity parsing/validation
            with pytest.raises(ImporterError):
                self._run_import_expecting_failure(package_root)
            
            # Verify no partial entities created
            assert get_counter("importer.entities.ingested") == initial_entities_counter, \
                "No entities should be created when schema validation fails"
            
            # Verify rollback counter incremented  
            assert get_counter("importer.rollback") > 0, \
                "Rollback counter should increment on schema validation failure"

    def test_lore_collision_rollback(self): 
        """Test that lore chunk collision causes proper rollback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            self._create_lore_collision_package(package_root)
            
            initial_chunks_counter = get_counter("importer.chunks.ingested")
            
            # Should fail during lore processing with collision
            with pytest.raises(LoreCollisionError, match="collision"):
                self._run_lore_import_expecting_failure(package_root)
            
            # Verify no chunks ingested
            assert get_counter("importer.chunks.ingested") == initial_chunks_counter, \
                "No chunks should be ingested after collision failure"
                
            # Verify collision tracked
            assert get_counter("importer.lore.collisions") > 0, \
                "Lore collision should be tracked in metrics"
            
            # Verify rollback counter incremented
            assert get_counter("importer.rollback.lore") > 0, \
                "Rollback counter should increment on lore collision"

    def test_rollback_structured_logging(self):
        """Test that rollback scenarios emit proper structured logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_collision_package(package_root)
            
            captured_logs = []
            
            with patch('Adventorator.importer.emit_structured_log') as mock_log:
                mock_log.side_effect = lambda event, **kwargs: captured_logs.append({
                    'event': event, **kwargs
                })
                
                # Attempt import that will fail
                with pytest.raises(EntityCollisionError):
                    self._run_import_expecting_failure(package_root)
            
            # Verify rollback logs were emitted
            rollback_logs = [log for log in captured_logs if 'rollback' in log.get('event', '')]
            assert len(rollback_logs) > 0, "Should emit rollback structured logs"
            
            # Verify logs contain required fields
            for log in rollback_logs:
                assert 'manifest_hash' in log, "Rollback logs should include manifest hash"
                assert 'phase' in log, "Rollback logs should include affected phase"
                assert 'outcome' in log, "Rollback logs should include outcome"

    def test_per_phase_rollback_counters(self):
        """Test that per-phase rollback counters are properly instrumented.
        
        TASK-CDA-IMPORT-METRIC-21A: Per-phase rollback counters.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_collision_package(package_root)
            
            # Should fail in entity phase
            with pytest.raises(ImporterError):
                self._run_import_expecting_failure(package_root)
            
            # Verify phase-specific rollback counter
            assert get_counter("importer.rollback.entity") > 0, \
                "Entity phase rollback counter should increment"
        
        # Test lore phase rollback counter  
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            self._create_lore_collision_package(package_root)
            
            with pytest.raises(LoreCollisionError):
                self._run_lore_import_expecting_failure(package_root)
            
            # Verify lore phase rollback counter
            assert get_counter("importer.rollback.lore") > 0, \
                "Lore phase rollback counter should increment"

    def _run_import_expecting_failure(self, package_root: Path):
        """Run import pipeline expecting it to fail.""" 
        manifest_path = package_root / "package.manifest.json"
        
        # Initialize phases
        manifest_phase = ManifestPhase(features_importer_enabled=True)
        entity_phase = EntityPhase(features_importer_enabled=True)
        
        # Run pipeline - will fail at entity collision detection
        context = ImporterRunContext()
        
        try:
            # Manifest validation
            manifest_result = manifest_phase.validate_and_register(manifest_path, package_root)
            context.record_manifest(manifest_result)
            
            # Entity ingestion - collision will be detected here
            entities_dir = package_root / "entities"
            if entities_dir.exists():
                entity_results = entity_phase.parse_and_validate_entities(package_root, manifest_result["manifest"])
                # This should fail before context.record_entities is called
                
        except Exception as e:
            # Remove artificial counter increments - let the real business logic handle this
            raise

    def _run_lore_import_expecting_failure(self, package_root: Path):
        """Run lore import expecting collision failure."""
        manifest_path = package_root / "package.manifest.json"
        
        manifest_phase = ManifestPhase(features_importer_enabled=True)
        lore_phase = LorePhase(features_importer_enabled=True)
        
        context = ImporterRunContext()
        
        try:
            # Manifest validation
            manifest_result = manifest_phase.validate_and_register(manifest_path, package_root)
            context.record_manifest(manifest_result)
            
            # Lore ingestion - collision will be detected
            # Note: parse_and_validate_lore expects package_root, not lore_dir
            lore_results = lore_phase.parse_and_validate_lore(package_root, manifest_result["manifest"])
            # This should fail at collision detection
                
        except Exception as e:
            # Remove artificial counter increments - let the real business logic handle this
            raise

    def _create_lore_collision_package(self, package_root: Path):
        """Create package with lore chunk collision."""
        (package_root / "lore").mkdir(parents=True)
        
        # Create manifest
        manifest_data = {
            "package_id": "01JLORECOLL000000000000001",
            "schema_version": 1,
            "engine_contract_range": {"min": "1.0.0", "max": "2.0.0"},
            "dependencies": [],
            "content_index": {},
            "ruleset_version": "1.0.0",
            "recommended_flags": {},
            "signatures": []
        }
        
        with open(package_root / "package.manifest.json", "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        # Create two lore files with same chunk_id but different content
        lore1_content = """---
chunk_id: COLLISION-CHUNK
title: "Original Chunk"
audience: Player
tags:
  - test:original
---

This is the original content that differs from the other file.
"""
        
        lore2_content = """---
chunk_id: COLLISION-CHUNK
title: "Conflicting Chunk"  
audience: Player
tags:
  - test:conflicting
---

This is the conflicting content that differs from the original.
"""
        
        with open(package_root / "lore" / "original.md", "w") as f:
            f.write(lore1_content)
            
        with open(package_root / "lore" / "conflicting.md", "w") as f:
            f.write(lore2_content)


class TestFailureInjectionHarness:
    """Test the failure injection harness utility itself."""
    
    def test_collision_package_creation(self):
        """Test that collision package is created correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_collision_package(package_root)
            
            # Verify structure created
            assert (package_root / "package.manifest.json").exists()
            assert (package_root / "entities" / "entity1.json").exists()
            assert (package_root / "entities" / "entity2.json").exists()
            
            # Verify collision scenario
            with open(package_root / "entities" / "entity1.json") as f:
                entity1 = json.load(f)
            with open(package_root / "entities" / "entity2.json") as f:
                entity2 = json.load(f)
                
            # Same stable_id but different content
            assert entity1["stable_id"] == entity2["stable_id"]
            assert entity1["name"] != entity2["name"]

    def test_missing_dependency_package_creation(self):
        """Test that missing dependency package is created correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_missing_dependency_package(package_root)
            
            # Verify manifest exists but references missing file
            assert (package_root / "package.manifest.json").exists()
            assert not (package_root / "entities" / "missing.json").exists()
            
            with open(package_root / "package.manifest.json") as f:
                manifest = json.load(f)
            assert "entities/missing.json" in manifest["content_index"]

    def test_invalid_schema_package_creation(self):
        """Test that invalid schema package is created correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_invalid_schema_package(package_root)
            
            # Verify files created
            assert (package_root / "package.manifest.json").exists()
            assert (package_root / "entities" / "invalid.json").exists()
            
            # Verify entity is missing required field
            with open(package_root / "entities" / "invalid.json") as f:
                entity = json.load(f)
            assert "kind" not in entity  # Missing required field


class TestDatabaseRollbackValidation:
    """Test database state validation for rollback scenarios."""
    
    @pytest.mark.asyncio
    async def test_entity_collision_database_rollback(self):
        """Test that entity collision leaves database in clean state.""" 
        from Adventorator.importer import run_full_import_with_database
        from Adventorator.db import session_scope
        from Adventorator import models
        from sqlalchemy import select
        
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_collision_package(package_root)
            
            # Get initial database state
            async with session_scope() as session:
                initial_events = await session.execute(
                    select(models.Event).where(models.Event.campaign_id == 1)
                )
                initial_event_count = len(initial_events.scalars().all())
                
                initial_logs = await session.execute(
                    select(models.ImportLog).where(models.ImportLog.campaign_id == 1)
                )
                initial_log_count = len(initial_logs.scalars().all())
            
            # Attempt database import - should fail with collision
            from Adventorator.importer import EntityCollisionError
            with pytest.raises(EntityCollisionError):
                await run_full_import_with_database(
                    package_root=package_root,
                    campaign_id=1,
                    features_importer=True
                )
            
            # Verify database state is unchanged (rollback completed)
            async with session_scope() as session:
                post_failure_events = await session.execute(
                    select(models.Event).where(models.Event.campaign_id == 1)
                )
                post_failure_event_count = len(post_failure_events.scalars().all())
                
                post_failure_logs = await session.execute(
                    select(models.ImportLog).where(models.ImportLog.campaign_id == 1)
                )
                post_failure_log_count = len(post_failure_logs.scalars().all())
                
                # Database should be in exactly the same state as before
                assert post_failure_event_count == initial_event_count, \
                    "No Events should be persisted after collision rollback"
                assert post_failure_log_count == initial_log_count, \
                    "No ImportLog entries should be persisted after collision rollback"
            
            # Verify rollback metrics were incremented
            from Adventorator.metrics import get_counter
            assert get_counter("importer.rollback.entity") > 0, \
                "Entity rollback counter should increment"
    
    @pytest.mark.asyncio
    async def test_manifest_failure_database_rollback(self):
        """Test that manifest validation failure leaves database clean."""
        from Adventorator.importer import run_full_import_with_database
        from Adventorator.db import session_scope
        from Adventorator import models
        from sqlalchemy import select
        
        with tempfile.TemporaryDirectory() as temp_dir: 
            package_root = Path(temp_dir)
            FailureInjectionHarness.create_missing_dependency_package(package_root)
            
            # Get initial database state
            async with session_scope() as session:
                initial_events = await session.execute(
                    select(models.Event).where(models.Event.campaign_id == 1)
                )
                initial_event_count = len(initial_events.scalars().all())
                
                initial_logs = await session.execute(
                    select(models.ImportLog).where(models.ImportLog.campaign_id == 1)
                )
                initial_log_count = len(initial_logs.scalars().all())
            
            # Attempt database import - should fail with manifest error
            from Adventorator.importer import ImporterError
            with pytest.raises(ImporterError):
                await run_full_import_with_database(
                    package_root=package_root,
                    campaign_id=1,
                    features_importer=True
                )
            
            # Verify database state is unchanged (rollback completed)
            async with session_scope() as session:
                post_failure_events = await session.execute(
                    select(models.Event).where(models.Event.campaign_id == 1)
                )
                post_failure_event_count = len(post_failure_events.scalars().all())
                
                post_failure_logs = await session.execute(
                    select(models.ImportLog).where(models.ImportLog.campaign_id == 1)
                )
                post_failure_log_count = len(post_failure_logs.scalars().all())
                
                # Database should be in exactly the same state as before
                assert post_failure_event_count == initial_event_count, \
                    "No Events should be persisted after manifest failure rollback"
                assert post_failure_log_count == initial_log_count, \
                    "No ImportLog entries should be persisted after manifest failure rollback"
            
            # Verify rollback metrics were incremented
            from Adventorator.metrics import get_counter
            assert get_counter("importer.rollback.manifest") > 0, \
                "Manifest rollback counter should increment"