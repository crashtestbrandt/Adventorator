"""Tests for edge import metrics (STORY-CDA-IMPORT-002C)."""

import json
import tempfile
from pathlib import Path

from Adventorator.importer import EdgeCollisionError, EdgePhase
from Adventorator.metrics import get_counter, reset_counters

SRC_ID = "01JAR9WYH41R8TFM6Z0X5E7NPC"
DST_ID = "01JAR9WYH41R8TFM6Z0X5E7C00"
ORG_ID = "01JAR9WYH41R8TFM6Z0X5E7RG0"


class TestEdgeMetrics:
    """Verify metrics for edge ingestion phase."""

    def setup_method(self):
        reset_counters()

    def _manifest(self) -> dict:
        return {"package_id": "01JAR9WYH41R8TFM6Z0X5E7EDGE", "manifest_hash": "abc"}

    def _entities(self) -> list[dict]:
        return [
            {"stable_id": SRC_ID},
            {"stable_id": DST_ID},
            {"stable_id": ORG_ID},
        ]

    def test_edges_created_metric(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            edges = [
                {
                    "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                    "type": "npc.resides_in.location",
                    "src_ref": SRC_ID,
                    "dst_ref": DST_ID,
                    "attributes": {"relationship_context": "liaison"},
                },
                {
                    "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED2",
                    "type": "organization.controls.location",
                    "src_ref": ORG_ID,
                    "dst_ref": DST_ID,
                    "attributes": {
                        "charter_clause": "Clause VII",
                        "oversight": "Council",
                    },
                    "validity": {
                        "start_event_id": "01JAR9WYH41R8TFM6Z0X5EV001",
                        "end_event_id": None,
                    },
                },
            ]

            with (edges_dir / "edges.json").open("w", encoding="utf-8") as handle:
                json.dump(edges, handle)

            phase.parse_and_validate_edges(package_root, self._manifest(), self._entities())

        assert get_counter("importer.edges.created") == 2

    def test_idempotent_metric_increment(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            duplicate_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                "type": "npc.resides_in.location",
                "src_ref": SRC_ID,
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison"},
            }

            for idx in range(3):
                with (edges_dir / f"edge_{idx}.json").open("w", encoding="utf-8") as handle:
                    json.dump(duplicate_edge, handle, separators=(",", ":"))

            phase.parse_and_validate_edges(package_root, self._manifest(), self._entities())

        assert get_counter("importer.edges.created") == 1
        assert get_counter("importer.edges.skipped_idempotent") == 2

    def test_collision_metric_increment(self):
        phase = EdgePhase(features_importer_enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            edges_dir = package_root / "edges"
            edges_dir.mkdir()

            base_edge = {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                "type": "npc.resides_in.location",
                "src_ref": SRC_ID,
                "dst_ref": DST_ID,
                "attributes": {"relationship_context": "liaison"},
            }

            variant_edge = {
                **base_edge,
                "attributes": {"relationship_context": "changed"},
            }

            with (edges_dir / "edge1.json").open("w", encoding="utf-8") as handle:
                json.dump(base_edge, handle)
            with (edges_dir / "edge2.json").open("w", encoding="utf-8") as handle:
                json.dump(variant_edge, handle)

            try:
                phase.parse_and_validate_edges(package_root, self._manifest(), self._entities())
                raise AssertionError("Collision should raise EdgeCollisionError")
            except EdgeCollisionError:
                pass

        assert get_counter("importer.edges.collision") == 1
        assert get_counter("importer.edges.created") == 0


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__]))
