"""Readiness checks for STORY-CDA-IMPORT-002C edge ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from Adventorator.importer import EntityPhase

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "import" / "edge_package"
TAXONOMY_PATH = Path("contracts/edges/edge-type-taxonomy.json")


def load_manifest() -> dict:
    """Load the manifest fixture for the edge package."""
    with (FIXTURE_ROOT / "package.manifest.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def load_entities(manifest: dict) -> list[dict]:
    """Run the entity phase to produce parser output used by edge validation."""
    phase = EntityPhase(features_importer_enabled=True)
    return phase.parse_and_validate_entities(FIXTURE_ROOT, manifest)


def load_edges() -> list[dict]:
    """Load edge definitions from the fixture package."""
    with (FIXTURE_ROOT / "edges" / "edges.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def load_taxonomy() -> dict:
    """Load the documented edge type taxonomy."""
    with TAXONOMY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_entity_phase_exposes_stable_id_registry() -> None:
    """Entity ingestion output should provide stable IDs and provenance for edge validation."""
    manifest = load_manifest()
    entities = load_entities(manifest)

    assert entities, "edge readiness fixture must contain entities"

    registry = {entity["stable_id"]: entity for entity in entities}
    assert len(registry) == len(entities), "stable_id values must be unique"

    for entity in entities:
        assert entity["stable_id"] in registry
        assert entity["provenance"]["package_id"] == manifest["package_id"]
        assert entity["provenance"]["source_path"].startswith("entities/")
        file_hash = entity["provenance"]["file_hash"]
        assert isinstance(file_hash, str) and len(file_hash) == 64


def test_edge_fixture_matches_taxonomy_and_entities() -> None:
    """Edges should reference known entities and honor the documented taxonomy."""
    manifest = load_manifest()
    entities = load_entities(manifest)
    registry = {entity["stable_id"]: entity for entity in entities}
    taxonomy = load_taxonomy()
    edges = load_edges()

    assert edges, "edge readiness fixture must contain edges"

    for edge in edges:
        edge_type = edge["type"]
        assert edge_type in taxonomy, f"edge type {edge_type} missing from taxonomy"
        taxonomy_entry = taxonomy[edge_type]

        assert edge["src_ref"] in registry, "source reference missing from entity registry"
        assert edge["dst_ref"] in registry, "destination reference missing from entity registry"

        attributes = edge.get("attributes", {})
        for required_attribute in taxonomy_entry.get("required_attributes", []):
            assert required_attribute in attributes, (
                f"missing required attribute {required_attribute}"
            )

        validity = edge.get("validity")
        validity_required = taxonomy_entry.get("validity_required", False)
        if validity_required:
            assert validity is not None, f"validity block required for {edge_type}"
        if validity:
            start_event = validity.get("start_event_id")
            assert isinstance(start_event, str) and start_event, "start_event_id must be populated"
            end_event = validity.get("end_event_id")
            if end_event is not None:
                assert isinstance(end_event, str) and end_event >= start_event, (
                    "end_event_id must be lexically >= start_event_id"
                )
