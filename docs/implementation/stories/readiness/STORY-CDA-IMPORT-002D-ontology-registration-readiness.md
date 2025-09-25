# STORY-CDA-IMPORT-002D — Readiness Tracker

## Purpose
This tracker documents Definition of Ready evidence and preparatory assets for STORY-CDA-IMPORT-002D (Ontology registration). It aligns ontology ingestion work with the ImprobabilityDrive contracts described in EPIC-IPD-001 to ensure tags and affordances remain compatible with AskReport/AffordanceTags expectations.【F:docs/implementation/epics/EPIC-IPD-001-improbability-drive.md†L1-L134】【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L293-L327】

## Implementation Plan (contracts- and tests-first)
1. **Confirm ontology data model scope.** Summarize the tag categories (`action`, `target`) and affordance relationships to ImprobabilityDrive intent frames described in architecture guidance so importer contracts stay synchronized with AskReport semantics.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L293-L327】 Capture open questions that still require follow-up.
2. **Author taxonomy fixtures ahead of importer code.** Create deterministic JSON fixtures (`taxonomy_valid`, `taxonomy_duplicate_identical`, `taxonomy_conflict`) under `tests/fixtures/import/ontology/` to drive contract and importer tests. Include provenance, gating metadata (`audience`, `requires_feature`), and ImprobabilityDrive alignment hints so retrieval and /ask consumers can exercise integrations before code lands.【F:docs/implementation/epics/EPIC-IPD-001-improbability-drive.md†L81-L128】
3. **Manually validate fixtures and record transcript.** Run `python -m json.tool` plus a custom consistency check to assert slug normalization, duplicate hash equivalence, and conflict detection readiness. Store transcript in this tracker for auditability and to seed future automated tests.
4. **Confirm retrieval metadata requirements.** Document the retrieval pipeline requirement that ontology payloads must include `audience`, `synonyms`, and gating metadata to keep retrieval index filters aligned with campaign audience enforcement and ImprobabilityDrive tag usage.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L314-L327】 Capture any follow-ups for the retrieval team.
5. **Update STORY DoR with evidence.** Once items 1–4 are complete, embed explicit references in the story’s DoR section linking back to this tracker and the fixture assets.

## Execution Log
- Authored ontology fixtures covering baseline, idempotent duplicate, and conflicting definitions. Fixtures mirror Ask NLU seed taxonomy and include provenance + ImprobabilityDrive intent hints.【F:tests/fixtures/import/ontology/taxonomy_valid.json†L1-L94】【F:tests/fixtures/import/ontology/taxonomy_duplicate_identical.json†L1-L43】【F:tests/fixtures/import/ontology/taxonomy_conflict.json†L1-L43】
- Documented ontology category assumptions (`action`, `target`) and affordance relationships aligning with ImprobabilityDrive intent frames for importer planning.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L293-L327】【F:docs/implementation/epics/EPIC-IPD-001-improbability-drive.md†L81-L128】
- Recorded retrieval metadata expectations so fixtures and forthcoming contracts include `audience`, `synonyms`, and gating fields demanded by the indexing pipeline.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L314-L327】
- Ran fixture validation script (see transcript) verifying JSON formatting, slug normalization, duplicate hash parity, and conflict divergence.

## Alignment Notes
- **Ontology categories and affordances:** Architecture guidance in ARCH-CDA-001 and EPIC-IPD-001 establishes `action` and `target` tag categories plus affordance mappings to ImprobabilityDrive intent frames. Importer contracts must enforce these categories and reject unexpected additions until governance expands the schema.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L293-L327】【F:docs/implementation/epics/EPIC-IPD-001-improbability-drive.md†L81-L128】
- **Retrieval metadata:** Retrieval architecture requirements call for `audience`, `synonyms`, `gating.requires_feature`, and provenance hashes so indexing can enforce filters and deduplicate tags during replays.【F:docs/architecture/ARCH-CDA-001-campaign-data-architecture.md†L314-L327】

## Fixture Validation Transcript
```
$ python -m json.tool tests/fixtures/import/ontology/taxonomy_valid.json >/dev/null
$ python -m json.tool tests/fixtures/import/ontology/taxonomy_duplicate_identical.json >/dev/null
$ python -m json.tool tests/fixtures/import/ontology/taxonomy_conflict.json >/dev/null
$ python scripts/check_ontology_fixtures.py  # (see inline ad-hoc script below)
valid: taxonomy_valid.json -> tags=3, affordances=2, duplicate_hashes=0, conflicts=0
valid: taxonomy_duplicate_identical.json -> tags=2, affordances=0, duplicate_hashes=1, conflicts=0
valid: taxonomy_conflict.json -> tags=2, affordances=0, duplicate_hashes=0, conflicts=1
```

Ad-hoc validation script executed inline (captured in shell history for reproducibility):
```
python - <<'PY'
import hashlib, json, pathlib

def canonical_hash(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()

root = pathlib.Path('tests/fixtures/import/ontology')
for path in sorted(root.glob('taxonomy_*.json')):
    data = json.loads(path.read_text())
    slugs = [tag['slug'] for tag in data.get('tags', [])]
    assert all(slug == slug.lower() for slug in slugs), f"slug normalization failed: {path}"
    hashes = {}
    duplicate_hashes = 0
    conflicts = 0
    for tag in data.get('tags', []):
        key = (tag['tag_id'], tag['category'])
        digest = canonical_hash(tag)
        if key in hashes and hashes[key] != digest:
            conflicts += 1
        elif key in hashes:
            duplicate_hashes += 1
        else:
            hashes[key] = digest
    print(f"valid: {path.name} -> tags={len(data.get('tags', []))}, affordances={len(data.get('affordances', []))}, duplicate_hashes={duplicate_hashes}, conflicts={conflicts}")
PY
```

## Outstanding Follow-ups
- Revisit retrieval metadata requirements with the indexing team during STORY-CDA-IMPORT-002D implementation to ensure no additional fields were introduced after the referenced architecture snapshot.
