"""Golden fixture coverage for importer state digest readiness."""

from __future__ import annotations

from pathlib import Path

from Adventorator.importer import (
    EdgePhase,
    EntityPhase,
    LorePhase,
    ManifestPhase,
    OntologyPhase,
)
from Adventorator.importer_context import ImporterRunContext


FIXTURE_ROOT = Path("tests/fixtures/import/manifest/happy-path")
EXPECTED_DIGEST_PATH = FIXTURE_ROOT / "state_digest.txt"


def test_happy_path_fixture_generates_expected_digest() -> None:
    """End-to-end parse should produce deterministic state digest."""

    manifest_phase = ManifestPhase(features_importer_enabled=True)
    manifest_path = FIXTURE_ROOT / "package.manifest.json"
    manifest_result = manifest_phase.validate_and_register(manifest_path, FIXTURE_ROOT)

    context = ImporterRunContext()
    context.record_manifest(manifest_result)

    manifest_with_hash = dict(manifest_result["manifest"])
    manifest_with_hash["manifest_hash"] = manifest_result["manifest_hash"]

    entity_phase = EntityPhase(features_importer_enabled=True)
    entities = entity_phase.parse_and_validate_entities(FIXTURE_ROOT, manifest_with_hash)
    context.record_entities(entities)

    edge_phase = EdgePhase(features_importer_enabled=True)
    edges = edge_phase.parse_and_validate_edges(FIXTURE_ROOT, manifest_with_hash, entities)
    context.record_edges(edges)

    ontology_phase = OntologyPhase(features_importer_enabled=True)
    tags, affordances, ontology_logs = ontology_phase.parse_and_validate_ontology(
        FIXTURE_ROOT, manifest_with_hash
    )
    context.record_ontology(tags, affordances, ontology_logs)

    lore_phase = LorePhase(features_importer_enabled=True, features_importer_embeddings=True)
    chunks = lore_phase.parse_and_validate_lore(FIXTURE_ROOT, manifest_with_hash)
    context.record_lore_chunks(chunks)

    digest = context.compute_state_digest()

    expected_digest = EXPECTED_DIGEST_PATH.read_text(encoding="utf-8").strip()
    assert digest == expected_digest

    counts = context.summary_counts()
    assert counts["entities"] > 0
    assert counts["edges"] > 0
    assert counts["tags"] >= 0
    assert counts["affordances"] >= 0
    assert counts["chunks"] > 0
