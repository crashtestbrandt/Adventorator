# Ontology Validator Fixtures

Purpose: These fixtures are for ontology governance & validation tests (STORY-IPD-001E). They are NOT package import artifacts and intentionally include invalid, duplicate, and conflict cases that must never appear inside a single import bundle.

Directory roles:
- `valid/` Minimal canonical ontology collection(s) used as a happy path for the validator.
- `invalid/` Negative cases (schema omissions, pattern violations, unknown fields) to assert strictness.
- `duplicate/` Multiple files defining the same tag/affordance identically (should be treated as idempotent by the validator).
- `conflict/` Same identifiers with divergent definitions (validator must hard-fail with a diff/hash notice).

Why separate from `tests/fixtures/import/manifest/.../ontologies/`?
- Import package fixtures must represent a coherent, production-like bundle referenced by a manifest content index for deterministic hashing and replay.
- Validator fixtures need freedom to model pathological inputs without affecting manifest hashes or importer happy-path tests.

Cross-references:
- Import ontology ingestion story: `docs/implementation/stories/STORY-CDA-IMPORT-002D-ontology-registration.md`
- Ontology management story (this fixtures' owning story): `docs/implementation/stories/STORY-IPD-001E-ontology-management.md`
- Epic (import): `docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md`

Maintenance guidelines:
- Add new negative cases only when a new validation rule or schema invariant is introduced; name files descriptively.
- Do not reuse the same slug/identifier across unrelated negative cases unless the case specifically tests duplicate vs conflict handling.
- Keep examples minimal: remove extraneous fields not required to trigger the intended validation path.
- When adding fixtures, update any validator unit tests to assert precise error messages or hash-diff outputs.

Hash/idempotency note:
- Duplicate fixtures should remain byte-for-byte identical in their canonical JSON sections (ordering, spacing irrelevant once canonicalized) so tests can confirm idempotent pass behavior.

If you are looking for the ontology files used by the importer integration tests, see: `tests/fixtures/import/manifest/happy-path/ontologies/`.
