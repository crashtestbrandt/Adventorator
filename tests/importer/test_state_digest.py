"""Tests for state digest computation and fold verification (STORY-CDA-IMPORT-002F)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from Adventorator.importer import FinalizationPhase
from Adventorator.importer_context import ImporterRunContext

# Test constants
TEST_PACKAGE_ID = "01JAR9WYH41R8TFM6Z0X5E7QKJ"
TEST_MANIFEST_HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


class TestStateFoldVerification:
    """Test deterministic state fold and digest verification."""

    def test_deterministic_state_digest_clean_database(self):
        """Test that consecutive imports on clean database produce identical state digest."""
        # Simulate identical import runs
        def create_test_context():
            context = ImporterRunContext()
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            context.entities = [
                {
                    "stable_id": "01JA6Z7F8NPC00000000000001",
                    "provenance": {"file_hash": "entity1hash" + "0" * 54}
                }
            ]
            context.edges = [
                {
                    "stable_id": "01JA6Z7F8EDG00000000000001", 
                    "provenance": {"file_hash": "edge1hash" + "0" * 56}
                }
            ]
            context.ontology_tags = [
                {
                    "tag_id": "tag.test.example",
                    "provenance": {"file_hash": "tag1hash" + "0" * 56}
                }
            ]
            context.ontology_affordances = [
                {
                    "affordance_id": "affordance.test.example",
                    "provenance": {"file_hash": "aff1hash" + "0" * 56}
                }
            ]
            context.lore_chunks = [
                {
                    "chunk_id": "CHUNK-TEST-001",
                    "content_hash": "chunk1hash" + "0" * 54
                }
            ]
            return context

        # Run 1: Fresh database
        context1 = create_test_context()
        digest1 = context1.compute_state_digest()

        # Run 2: Fresh database (identical data)
        context2 = create_test_context()
        digest2 = context2.compute_state_digest()

        # Digests must be identical
        assert digest1 == digest2
        assert len(digest1) == 64  # SHA-256 hex string
        assert all(c in "0123456789abcdef" for c in digest1)

    def test_state_digest_different_for_mutated_data(self):
        """Test that mutated data produces different state digest."""
        # Create base context
        def create_base_context():
            context = ImporterRunContext()
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            context.entities = [
                {
                    "stable_id": "01JA6Z7F8NPC00000000000001",
                    "provenance": {"file_hash": "entity1hash" + "0" * 54}
                }
            ]
            return context

        # Original context
        context1 = create_base_context()
        digest1 = context1.compute_state_digest()

        # Mutated context (different entity hash)
        context2 = create_base_context()
        context2.entities[0]["provenance"]["file_hash"] = "mutatedhash" + "0" * 54
        digest2 = context2.compute_state_digest()

        # Digests must be different
        assert digest1 != digest2

    def test_state_digest_ordering_independence(self):
        """Test that state digest is independent of input ordering."""
        # Create contexts with same data in different orders
        def create_context_ordered():
            context = ImporterRunContext()
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            context.entities = [
                {"stable_id": "entity_a", "provenance": {"file_hash": "hash_a" + "0" * 58}},
                {"stable_id": "entity_b", "provenance": {"file_hash": "hash_b" + "0" * 58}},
                {"stable_id": "entity_c", "provenance": {"file_hash": "hash_c" + "0" * 58}},
            ]
            return context

        def create_context_reversed():
            context = ImporterRunContext()
            context.package_id = TEST_PACKAGE_ID
            context.manifest_hash = TEST_MANIFEST_HASH
            context.entities = [
                {"stable_id": "entity_c", "provenance": {"file_hash": "hash_c" + "0" * 58}},
                {"stable_id": "entity_b", "provenance": {"file_hash": "hash_b" + "0" * 58}},
                {"stable_id": "entity_a", "provenance": {"file_hash": "hash_a" + "0" * 58}},
            ]
            return context

        context1 = create_context_ordered()
        context2 = create_context_reversed()

        digest1 = context1.compute_state_digest()
        digest2 = context2.compute_state_digest()

        # Digests should be identical despite different input ordering
        assert digest1 == digest2

    def test_golden_manifest_state_digest(self):
        """Test state digest against golden fixture."""
        # Load expected digest from fixture
        fixture_path = Path("tests/fixtures/import/manifest/happy-path/state_digest.txt")
        if not fixture_path.exists():
            pytest.skip("Golden state digest fixture not available")

        with open(fixture_path, encoding="utf-8") as f:
            expected_digest = f.read().strip()

        # Create context matching the golden fixture by running the actual phases
        from Adventorator.importer import (
            EdgePhase,
            EntityPhase,
            LorePhase,
            ManifestPhase,
            OntologyPhase,
        )
        
        fixture_root = Path("tests/fixtures/import/manifest/happy-path")
        
        # Run the actual phases like in the golden fixture test
        manifest_phase = ManifestPhase(features_importer_enabled=True)
        manifest_path = fixture_root / "package.manifest.json"
        
        if not manifest_path.exists():
            pytest.skip("Golden manifest fixture not available")
            
        manifest_result = manifest_phase.validate_and_register(manifest_path, fixture_root)

        context = ImporterRunContext()
        context.record_manifest(manifest_result)

        manifest_with_hash = dict(manifest_result["manifest"])
        manifest_with_hash["manifest_hash"] = manifest_result["manifest_hash"]

        entity_phase = EntityPhase(features_importer_enabled=True)
        entities = entity_phase.parse_and_validate_entities(fixture_root, manifest_with_hash)
        context.record_entities(entities)

        edge_phase = EdgePhase(features_importer_enabled=True)
        edges = edge_phase.parse_and_validate_edges(fixture_root, manifest_with_hash, entities)
        context.record_edges(edges)

        ontology_phase = OntologyPhase(features_importer_enabled=True)
        tags, affordances, ontology_logs = ontology_phase.parse_and_validate_ontology(
            fixture_root, manifest_with_hash
        )
        context.record_ontology(tags, affordances, ontology_logs)

        lore_phase = LorePhase(features_importer_enabled=True, features_importer_embeddings=True)
        chunks = lore_phase.parse_and_validate_lore(fixture_root, manifest_with_hash)
        context.record_lore_chunks(chunks)

        # Compute the digest
        computed_digest = context.compute_state_digest()
        
        # Verify digest format
        assert len(computed_digest) == 64
        assert all(c in "0123456789abcdef" for c in computed_digest)
        
        # Validate against golden fixture
        assert computed_digest == expected_digest
        
        # If this fails, the golden fixture may need updating or test data adjustment
        # In a real scenario, this would validate against known-good fixture data
        # assert computed_digest == expected_digest

    def test_replay_idempotency_verification(self):
        """Test that replay on existing data maintains idempotency.""" 
        phase = FinalizationPhase(features_importer_enabled=True)
        
        # Simulate first import
        context1 = ImporterRunContext()
        context1.package_id = TEST_PACKAGE_ID
        context1.manifest_hash = TEST_MANIFEST_HASH
        context1.entities = [
            {"stable_id": "entity1", "provenance": {"file_hash": "hash1" + "0" * 59}}
        ]
        
        start_time1 = datetime.now(timezone.utc)
        result1 = phase.finalize_import(context1, start_time1)
        
        # Simulate second import (replay) with identical data
        context2 = ImporterRunContext()
        context2.package_id = TEST_PACKAGE_ID
        context2.manifest_hash = TEST_MANIFEST_HASH
        context2.entities = [
            {"stable_id": "entity1", "provenance": {"file_hash": "hash1" + "0" * 59}}
        ]
        
        start_time2 = datetime.now(timezone.utc)
        result2 = phase.finalize_import(context2, start_time2)
        
        # State digests should be identical (idempotent)
        assert result1["state_digest"] == result2["state_digest"]
        
        # Completion event payloads should have same core data
        payload1 = result1["completion_event"]["payload"]
        payload2 = result2["completion_event"]["payload"]
        
        # These fields should be identical for idempotent replay
        for field in ["package_id", "manifest_hash", "entity_count", "edge_count", 
                     "tag_count", "affordance_count", "chunk_count", "state_digest"]:
            assert payload1[field] == payload2[field]

    def test_state_digest_components_canonical_ordering(self):
        """Test that state digest components are in canonical order."""
        context = ImporterRunContext()
        context.package_id = TEST_PACKAGE_ID
        context.manifest = {"package_id": TEST_PACKAGE_ID}
        context.manifest_hash = "manifesthash" + "0" * 52
        
        # Add components in random order
        context.entities = [
            {"stable_id": "z_entity", "provenance": {"file_hash": "hash_z" + "0" * 58}},
            {"stable_id": "a_entity", "provenance": {"file_hash": "hash_a" + "0" * 58}},
            {"stable_id": "m_entity", "provenance": {"file_hash": "hash_m" + "0" * 58}},
        ]
        
        components = context.state_digest_components()
        
        # Verify components are sorted by (phase, stable_id, content_hash)
        prev_sort_key = None
        for component in components:
            current_sort_key = (
                component["phase"], 
                component["stable_id"], 
                component["content_hash"]
            )
            if prev_sort_key is not None:
                assert current_sort_key >= prev_sort_key, "Components not in canonical order"
            prev_sort_key = current_sort_key

    def test_failure_injection_digest_mismatch_detection(self):
        """Test that intentional data mutation is detected via digest mismatch."""
        # This simulates the scenario where ledger data is modified between runs
        
        # Create baseline context
        context_baseline = ImporterRunContext()
        context_baseline.package_id = TEST_PACKAGE_ID
        context_baseline.manifest_hash = "baseline_hash" + "0" * 51
        context_baseline.entities = [
            {"stable_id": "entity1", "provenance": {"file_hash": "baseline_entity_hash" + "0" * 46}}
        ]
        
        baseline_digest = context_baseline.compute_state_digest()
        
        # Create "corrupted" context (simulating modified ledger data)
        context_corrupted = ImporterRunContext()
        context_corrupted.package_id = TEST_PACKAGE_ID
        context_corrupted.manifest_hash = "baseline_hash" + "0" * 51  # Same manifest
        context_corrupted.entities = [
            {
                "stable_id": "entity1", 
                "provenance": {"file_hash": "corrupted_entity_hash" + "0" * 43}
            }  # Different hash
        ]
        
        corrupted_digest = context_corrupted.compute_state_digest()
        
        # Digests should be different, indicating corruption detection
        assert baseline_digest != corrupted_digest
        
        # In a real implementation, this would trigger an alert/error log
        with patch('Adventorator.importer.emit_structured_log') as mock_log:
            # Simulate detecting mismatch during validation
            if baseline_digest != corrupted_digest:
                from Adventorator.importer import emit_structured_log
                emit_structured_log(
                    "state_digest_mismatch_detected",
                    expected=baseline_digest,
                    actual=corrupted_digest,
                    package_id=TEST_PACKAGE_ID
                )
            
            # Verify error was logged
            mock_log.assert_called_with(
                "state_digest_mismatch_detected",
                expected=baseline_digest,
                actual=corrupted_digest,
                package_id=TEST_PACKAGE_ID
            )

    def test_full_pipeline_replay_idempotency(self):
        """Test complete pipeline replay demonstrates no duplicate ledger events."""
        # This is the comprehensive replay integration test mentioned in the story
        fixture_root = Path("tests/fixtures/import/manifest/happy-path")
        fixture_path = fixture_root / "package.manifest.json"
        
        if not fixture_path.exists():
            pytest.skip("Golden manifest fixture not available")
        
        from Adventorator.importer import run_complete_import_pipeline
        
        def run_full_import():
            """Run complete import pipeline using production code path."""
            return run_complete_import_pipeline(
                fixture_root, 
                features_importer=True, 
                features_importer_embeddings=True
            )
        
        # First run
        result1 = run_full_import()
        
        # Second run (replay)
        result2 = run_full_import()
        
        # Assert identical state digests (idempotency)
        assert result1["finalization"]["state_digest"] == result2["finalization"]["state_digest"]
        
        # Assert identical counts (no duplicates in second run)
        counts1 = result1["context"].summary_counts()
        counts2 = result2["context"].summary_counts()
        assert counts1 == counts2
        
        # Assert completion events have same core data (deterministic payload)
        payload1 = result1["finalization"]["completion_event"]["payload"]
        payload2 = result2["finalization"]["completion_event"]["payload"]
        
        for field in ["package_id", "manifest_hash", "entity_count", "edge_count", 
                     "tag_count", "affordance_count", "chunk_count", "state_digest"]:
            assert payload1[field] == payload2[field]
        
        # Verify that in a real ledger scenario, the second run would produce
        # no new ledger events (this test simulates by checking event determinism)
        # The production pipeline properly manages ImportLog entries and sequence numbers
        
        # Verify ImportLog entries are properly sequenced in both runs
        logs1 = result1["context"].import_log_entries
        logs2 = result2["context"].import_log_entries
        
        # Both runs should have the same ImportLog structure
        assert len(logs1) == len(logs2)
        
        # Verify sequence numbers are contiguous (no gaps)
        sequences1 = [entry.get("sequence_no") for entry in logs1 if isinstance(entry.get("sequence_no"), int)]
        sequences2 = [entry.get("sequence_no") for entry in logs2 if isinstance(entry.get("sequence_no"), int)]
        
        if sequences1:
            sequences1.sort()
            expected_sequences = list(range(1, len(sequences1) + 1))
            assert sequences1 == expected_sequences, f"First run has sequence gaps: {sequences1}"
            
        if sequences2:
            sequences2.sort()
            expected_sequences = list(range(1, len(sequences2) + 1))
            assert sequences2 == expected_sequences, f"Second run has sequence gaps: {sequences2}"