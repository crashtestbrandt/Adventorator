# Contract Workspace

Use this directory to manage contract-first assets such as OpenAPI documents, protobuf schemas, and GraphQL SDL files.

## Guidelines
- Group contracts by surface area (`http/`, `events/`, `internal/`) or by service name.
- Version files explicitly (for example, `openapi/v1/encounter.yaml`) and document backward-compatibility guarantees.
- Pair schema updates with consumer-driven contract tests or golden files to validate compatibility.

Contracts should be referenced from Stories and Tasks using the new templates so that every change remains tied to the appropriate quality gates.
