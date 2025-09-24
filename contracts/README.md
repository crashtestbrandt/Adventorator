# Contract Workspace

Use this directory to manage contract-first assets such as OpenAPI documents, protobuf schemas, and GraphQL SDL files.

## Guidelines
- Group contracts by surface area (`http/`, `events/`, `internal/`) or by service name.
- Version files explicitly (for example, `openapi/v1/encounter.yaml`) and document backward-compatibility guarantees.
- Pair schema updates with consumer-driven contract tests or golden files to validate compatibility.

Contracts should be referenced from Stories and Tasks using the new templates so that every change remains tied to the appropriate quality gates.

## Package Manifests

Campaign package manifests are validated against `package/manifest.v1.json` schema implementing:
- ADR-0011 Package Import Provenance
- ADR-0006 Event Envelope & Hash Chain  
- ADR-0007 Canonical JSON Policy
- ARCH-CDA-001 Campaign Data Architecture

See STORY-CDA-IMPORT-002A for manifest validation requirements and `src/Adventorator/manifest_validation.py` for implementation.

## Event Schemas

Synthetic seed events are defined under `events/seed/` with schemas for:
- `manifest-validated.v1.json` - Emitted after successful manifest validation

## Ontology Seed

The ontology (planner / action-validation tag taxonomy) is versioned under `ontology/v1/seed.json`.

- Include a version token either in the folder name (`v1`) or filename per validator rules.
- The file must contain an `openapi` field (even if not a full API) to satisfy traceability and tooling expectations.
- Extend via additional version folders (`v2/`) rather than mutating prior versions; deprecate tags via docs and downstream migration stories.

Validator script: `python scripts/validate_prompts_and_contracts.py --only-contracts`.
