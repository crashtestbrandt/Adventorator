"""Unit tests for ImporterRunContext readiness helpers."""

from Adventorator.canonical_json import compute_canonical_hash
from Adventorator.importer_context import ImporterRunContext


def _hex(prefix: str) -> str:
    """Create deterministic 64-character hex strings for tests."""

    return (prefix * 64)[:64]


def test_context_collects_counts_and_logs() -> None:
    """ImporterRunContext should aggregate counts and unique ImportLog entries."""

    context = ImporterRunContext()

    manifest_hash = _hex("a")
    context.record_manifest(
        {
            "manifest": {"package_id": "pkg-123"},
            "manifest_hash": manifest_hash,
            "import_log_entry": {
                "phase": "manifest",
                "stable_id": "pkg-123",
                "file_hash": manifest_hash,
                "sequence_no": 1,
            },
        }
    )

    entity_hash = _hex("b")
    context.record_entities(
        [
            {
                "stable_id": "entity-1",
                "provenance": {
                    "package_id": "pkg-123",
                    "file_hash": entity_hash,
                },
                "import_log_entries": [
                    {
                        "phase": "entity",
                        "stable_id": "entity-1",
                        "file_hash": entity_hash,
                        "sequence_no": 2,
                    }
                ],
            }
        ]
    )

    edge_hash = _hex("c")
    context.record_edges(
        [
            {
                "stable_id": "edge-1",
                "provenance": {"file_hash": edge_hash},
                "import_log_entry": {
                    "phase": "edge",
                    "stable_id": "edge-1",
                    "file_hash": edge_hash,
                    "sequence_no": 3,
                },
            }
        ]
    )

    tag_hash = _hex("d")
    affordance_hash = _hex("e")
    context.record_ontology(
        tags=[
            {
                "tag_id": "tag.one",
                "provenance": {"file_hash": tag_hash},
            }
        ],
        affordances=[
            {
                "affordance_id": "affordance.one",
                "provenance": {"file_hash": affordance_hash},
            }
        ],
        import_log_entries=[
            {
                "phase": "ontology",
                "stable_id": "tag.one",
                "file_hash": tag_hash,
                "sequence_no": 4,
            },
            {
                "phase": "ontology",
                "stable_id": "affordance.one",
                "file_hash": affordance_hash,
                "sequence_no": 5,
            },
        ],
    )

    chunk_hash = _hex("f")
    context.record_lore_chunks(
        [
            {
                "chunk_id": "chunk-1",
                "content_hash": chunk_hash,
                "import_log_entries": [
                    {
                        "phase": "lore",
                        "stable_id": "chunk-1",
                        "file_hash": chunk_hash,
                        "sequence_no": 6,
                    }
                ],
            }
        ]
    )

    assert context.summary_counts() == {
        "entities": 1,
        "edges": 1,
        "tags": 1,
        "affordances": 1,
        "chunks": 1,
    }

    phases = [entry["phase"] for entry in context.import_log_entries]
    assert phases == ["edge", "entity", "lore", "manifest", "ontology", "ontology"]

    components = context.state_digest_components()
    phases_in_components = {component["phase"] for component in components}
    assert phases_in_components == {
        "manifest",
        "entity",
        "edge",
        "ontology.tag",
        "ontology.affordance",
        "lore",
    }


def test_context_digest_matches_manual_hash() -> None:
    """compute_state_digest should reuse canonical hash helper."""

    context = ImporterRunContext()
    manifest_hash = _hex("1")
    context.record_manifest(
        {
            "manifest": {"package_id": "pkg"},
            "manifest_hash": manifest_hash,
        }
    )

    context.record_entities(
        [
            {
                "stable_id": "entity",
                "provenance": {"file_hash": _hex("2")},
            }
        ]
    )

    digest = context.compute_state_digest()
    manual_payload = {"state_components": context.state_digest_components()}
    assert digest == compute_canonical_hash(manual_payload).hex()
