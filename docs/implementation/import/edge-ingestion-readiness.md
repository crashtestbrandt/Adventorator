# Edge ingestion readiness evidence

This document collates the readiness artifacts required by the Definition of Ready for
[STORY-CDA-IMPORT-002C](../stories/STORY-CDA-IMPORT-002C-edge-ingestion.md).

## Entity ingestion outputs
- The entity phase exports deterministic dictionaries with `stable_id` and `provenance` data as shown in
  [`EntityPhase.parse_and_validate_entities`](../../../src/Adventorator/importer.py). The readiness test builds a registry directly
  from this output to drive referential validation.
- Test coverage in [`tests/importer/test_edge_readiness.py`](../../../tests/importer/test_edge_readiness.py) loads the
  `edge_package` fixture, runs the entity phase, and exposes the registry consumed by edge validation logic.

## Edge type taxonomy
- Approved edge types and their required attributes are documented in
  [`edge-type-taxonomy.md`](./edge-type-taxonomy.md) with a machine-readable source of truth in
  [`contracts/edges/edge-type-taxonomy-v1.json`](../../../contracts/edges/edge-type-taxonomy-v1.json).
- The readiness test asserts that every fixture edge conforms to this taxonomy and that edge types requiring temporal validity
  include a populated `validity` block.

## Multi-phase fixtures
- The `edge_package` fixture at [`tests/fixtures/import/edge_package`](../../../tests/fixtures/import/edge_package/README.md)
  supplies manifest, entity, and edge content for integration-style tests.
- [`tests/importer/test_edge_readiness.py`](../../../tests/importer/test_edge_readiness.py) validates that all fixture edges reference known entity stable IDs and that the
  optional temporal validity block behaves defensively (null end date allowed, lexical ordering enforced when present).
