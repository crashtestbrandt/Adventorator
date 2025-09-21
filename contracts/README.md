# Contract Workspace

Use this directory to manage contract-first assets such as OpenAPI documents, protobuf schemas, and GraphQL SDL files.

## Guidelines
- Group contracts by surface area (`http/`, `events/`, `internal/`) or by service name.
- Version files explicitly (for example, `openapi/v1/encounter.yaml`) and document backward-compatibility guarantees.
- Pair schema updates with consumer-driven contract tests or golden files to validate compatibility.

Contracts should be referenced from Stories and Tasks using the new templates so that every change remains tied to the appropriate quality gates.

## Ontology Seed

The ontology (planner / action-validation tag taxonomy) is versioned under `ontology/v1/seed.json`.

- Include a version token either in the folder name (`v1`) or filename per validator rules.
- The file must contain an `openapi` field (even if not a full API) to satisfy traceability and tooling expectations.
- Extend via additional version folders (`v2/`) rather than mutating prior versions; deprecate tags via docs and downstream migration stories.

Validator script: `python scripts/validate_prompts_and_contracts.py --only-contracts`.
