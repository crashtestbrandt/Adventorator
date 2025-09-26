"""Tests for edge parsing phase (STORY-CDA-IMPORT-002C)."""

import json
import tempfile
from pathlib import Path

from Adventorator.importer import (
    EdgeCollisionError,
    EdgePhase,
    EdgeValidationError,
    ImporterError,
)
from Adventorator.metrics import get_counter, reset_counters

SRC_ID = "01JAR9WYH41R8TFM6Z0X5E7NPC"
DST_ID = "01JAR9WYH41R8TFM6Z0X5E7L0C"
ORG_ID = "01JAR9WYH41R8TFM6Z0X5E7ORG"


class TestEdgePhase:
    """Test edge parsing and validation logic."""

    def setup_method(self):
        reset_counters()

    def _manifest(self) -> dict:
        return {"package_id": "01JAR9WYH41R8TFM6Z0X5E7EDGE", "manifest_hash": "abc"}

    def _entity_registry(self) -> list[dict]:
        return [
            {"stable_id": SRC_ID},
            {"stable_id": DST_ID},
            {"stable_id": ORG_ID},
        ]

    def test_feature_flag_disabled(self):
        phase = EdgePhase(features_importer_enabled=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Feature flag disabled should raise ImporterError")
            except ImporterError:
                pass

    def test_no_edges_directory(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            manifest = self._manifest()

            edges = phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
            assert edges == []
            assert get_counter("importer.edges.created") == 0

    def test_parse_valid_edges(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            edges_payload = [
                {
                    "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                    "type": "npc.resides_in.location",
                    "src_ref": SRC_ID,
                    "dst_ref": DST_ID,
                    "attributes": {
                        "relationship_context": "liaison_residence",
                        "duty_schedule": "nocturnal",
                    },
                },
                {
                    "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED2",
                    "type": "organization.controls.location",
                    "src_ref": ORG_ID,
                    "dst_ref": DST_ID,
                    "attributes": {
                        "charter_clause": "Clause VII",
                        "oversight": "Council of Chronomancers",
                    },
                    "validity": {
                        "start_event_id": "01JAR9WYH41R8TFM6Z0X5EVLD1",
                        "end_event_id": None,
                    },
                },
            ]

            with (edges_dir / "edges.json").open("w", encoding="utf-8") as handle:
                json.dump(edges_payload, handle, indent=2)

            manifest = self._manifest()
            edges = phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())

            assert [edge["type"] for edge in edges] == [
                "npc.resides_in.location",
                "organization.controls.location",
            ]
            assert all("provenance" in edge for edge in edges)
            assert all("import_log_entry" in edge for edge in edges)
            assert get_counter("importer.edges.created") == 2

    def test_missing_reference_raises(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            invalid_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "npc.resides_in.location",
                "src_ref": "01JAR9WYH41R8TFM6Z0X5E7MISSING",
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison_residence"},
            }

            with (edges_dir / "invalid.json").open("w", encoding="utf-8") as handle:
                json.dump(invalid_edge, handle)

            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Missing reference should raise EdgeValidationError")
            except EdgeValidationError as exc:
                assert "missing entity reference" in str(exc)
            assert get_counter("importer.edges.created") == 0

    def test_invalid_edge_type(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            invalid_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "npc.knows.magic",
                "src_ref": SRC_ID,
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison_residence"},
            }

            with (edges_dir / "invalid.json").open("w", encoding="utf-8") as handle:
                json.dump(invalid_edge, handle)

            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Unsupported type should raise EdgeValidationError")
            except EdgeValidationError as exc:
                assert "unsupported edge type" in str(exc)

    def test_required_attributes_enforced(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            invalid_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "organization.controls.location",
                "src_ref": ORG_ID,
                "dst_ref": DST_ID,
                "attributes": {
                    "charter_clause": "Clause VII",
                },
                "validity": {
                    "start_event_id": "01JAR9WYH41R8TFM6Z0X5EVLD1",
                    "end_event_id": None,
                },
            }

            with (edges_dir / "missing_attr.json").open("w", encoding="utf-8") as handle:
                json.dump(invalid_edge, handle)

            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Missing taxonomy attribute should raise EdgeValidationError")
            except EdgeValidationError as exc:
                assert "missing required attribute" in str(exc)

    def test_validity_ordering_enforced(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            invalid_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "organization.controls.location",
                "src_ref": ORG_ID,
                "dst_ref": DST_ID,
                "attributes": {
                    "charter_clause": "Clause VII",
                    "oversight": "Council",
                },
                "validity": {
                    "start_event_id": "01JAR9WYH41R8TFM6Z0X5EVLD9",
                    "end_event_id": "01JAR9WYH41R8TFM6Z0X5EVLD1",
                },
            }

            with (edges_dir / "invalid_validity.json").open("w", encoding="utf-8") as handle:
                json.dump(invalid_edge, handle)

            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Invalid validity ordering should raise EdgeValidationError")
            except EdgeValidationError as exc:
                assert "end_event_id must not precede start_event_id" in str(exc)

    def test_idempotent_duplicates_skipped(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            duplicate_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "npc.resides_in.location",
                "src_ref": SRC_ID,
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison_residence"},
            }

            for idx in range(2):
                with (edges_dir / f"dup_{idx}.json").open("w", encoding="utf-8") as handle:
                    json.dump(duplicate_edge, handle, separators=(",", ":"))

            manifest = self._manifest()

            edges = phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())

            assert len(edges) == 1
            assert get_counter("importer.edges.created") == 1
            assert get_counter("importer.edges.skipped_idempotent") == 1

    def test_collision_raises_and_records_metric(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            base_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7EDX",
                "type": "npc.resides_in.location",
                "src_ref": SRC_ID,
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison_residence"},
            }

            modified_edge = {
                **base_edge,
                "attributes": {"relationship_context": "updated"},
            }

            with (edges_dir / "edge1.json").open("w", encoding="utf-8") as handle:
                json.dump(base_edge, handle)
            with (edges_dir / "edge2.json").open("w", encoding="utf-8") as handle:
                json.dump(modified_edge, handle)

            manifest = self._manifest()

            try:
                phase.parse_and_validate_edges(package_root, manifest, self._entity_registry())
                raise AssertionError("Collision should raise EdgeCollisionError")
            except EdgeCollisionError:
                pass

            assert get_counter("importer.edges.collision") == 1


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__]))
