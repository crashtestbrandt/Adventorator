---
name: "Story"
description: "PR-sized unit of work delivering a vertical slice."
title: "[Story] <Concise description>"
labels: ["type: story"]
assignees: []
about: "A PR-sized unit of work. Represents a coherent slice of functionality (often vertical: UI → API → DB). Carries acceptance criteria, tests, and contracts."
---

## Summary & Scope
What this Story delivers. Include both in-scope and out-of-scope.

- In scope:
  - …
- Out of scope:
  - …

Epic Link: #<EpicID>

## Acceptance Criteria
Concrete, testable criteria (Gherkin welcome):

- [ ] Given … When … Then …
- [ ] …

## Contracts & Compatibility
- OpenAPI/Protobuf/GraphQL deltas: <path and version>
- CDCs (consumer/provider): <details>
- Versioning & deprecation plan: <strategy>

## Test Strategy
- Unit & property-based tests
- Contract tests (provider/consumer)
- Integration slice (service + datastore + 1 dependency)
- Performance budget checks
- Security/abuse cases (authZ/validation; secrets scan baseline)
- AI evals (if applicable): factuality, safety, cost/latency

## Observability
- Metrics: app.request.duration (histogram), p95 budget 200ms
- Logs: structured error with `error_code`
- Traces: span names <namespace>/<operation>
- Dashboards/alerts to update

## Tasks
- [ ] #<TaskID-or-placeholder> — Define contract deltas
- [ ] #<TaskID-or-placeholder> — Write acceptance tests
- [ ] #<TaskID-or-placeholder> — Implement against tests
- [ ] #<TaskID-or-placeholder> — Add metrics/logs/traces
- [ ] #<TaskID-or-placeholder> — Update docs/runbook

## Definition of Ready (DoR)
- [ ] Acceptance criteria defined
- [ ] Contracts drafted and reviewed
- [ ] Test strategy approved
- [ ] Observability plan documented

## Definition of Done (DoD)
- [ ] Acceptance criteria verified by automated tests
- [ ] Contracts versioned & backward compatible (CDC/compat checks pass)
- [ ] Observability signals implemented and documented
- [ ] Security/SCA/SAST/secrets checks pass; perf within budget
- [ ] Docs updated; PR merged with all quality gates green
