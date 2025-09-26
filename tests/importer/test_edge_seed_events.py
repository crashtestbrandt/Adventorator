"""Tests for seed.edge_created event generation (STORY-CDA-IMPORT-002C)."""

from Adventorator.importer import EdgePhase, validate_event_payload_schema


class TestEdgeSeedEvents:
    """Validate edge seed event payloads."""

    def test_create_seed_events(self):
        phase = EdgePhase(features_importer_enabled=True)

        edges = [
            {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                "type": "npc.resides_in.location",
                "src_ref": "01JAR9WYH41R8TFM6Z0X5E7NPC",
                "dst_ref": "01JAR9WYH41R8TFM6Z0X5E7C00",
                "attributes": {
                    "relationship_context": "liaison_residence",
                    "duty_schedule": "nocturnal",
                },
                "provenance": {
                    "package_id": "01JAR9WYH41R8TFM6Z0X5E7EDGE",
                    "source_path": "edges/edges.json#0",
                    "file_hash": "abc",
                },
            },
            {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED2",
                "type": "organization.controls.location",
                "src_ref": "01JAR9WYH41R8TFM6Z0X5E7RG0",
                "dst_ref": "01JAR9WYH41R8TFM6Z0X5E7C00",
                "attributes": {
                    "charter_clause": "Clause VII",
                    "oversight": "Council of Chronomancers",
                },
                "validity": {
                    "start_event_id": "01JAR9WYH41R8TFM6Z0X5EV001",
                    "end_event_id": None,
                },
                "provenance": {
                    "package_id": "01JAR9WYH41R8TFM6Z0X5E7EDGE",
                    "source_path": "edges/edges.json#1",
                    "file_hash": "def",
                },
            },
        ]

        events = phase.create_seed_events(edges)
        assert len(events) == 2

        for payload in events:
            validate_event_payload_schema(payload, event_type="edge")
            assert payload["provenance"]["package_id"] == "01JAR9WYH41R8TFM6Z0X5E7EDGE"

    def test_create_seed_events_requires_provenance(self):
        phase = EdgePhase(features_importer_enabled=True)

        edges = [
            {
                "stable_id": "01JAR9WYH41R8TFM6Z0X5E7ED1",
                "type": "npc.resides_in.location",
                "src_ref": "01JAR9WYH41R8TFM6Z0X5E7NPC",
                "dst_ref": "01JAR9WYH41R8TFM6Z0X5E7C00",
                "attributes": {"relationship_context": "liaison_residence"},
            }
        ]

        try:
            phase.create_seed_events(edges)
            raise AssertionError("Missing provenance should raise ValueError")
        except ValueError as exc:
            assert "provenance" in str(exc)


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__]))
