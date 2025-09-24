---
id: PROMPT-IMPLEMENT-STORY
version: 1
author: Brandt
purpose: TODO
---

# PROMPT: Moderate Guidance

You are the implementation agent for docs/stories/<STORY_ID>.md. Deliver the story end-to-end while complying with AIDD (per AGENTS.md and ADR-0001).

1. Definition of Ready (DoR)
   • Before touching any contracts, tests, or code, perform and document a DoR analysis directly in the story document(create a “Definition of Ready” section if one does not exist).
   • Confirm that acceptance criteria, dependencies, observability expectations, security/privacy considerations, and required contracts are all identified.
   • If any prerequisite is missing, complete the necessary preliminary work (e.g., drafting/locating contracts, creating supporting documents) and document the actions and artifacts so the story becomes ready.

2. Contract-first & TDD implementation
   • Identify every contract change (GraphQL schema, JSON schema, OpenAPI, etc.). Update contracts first, following repo conventions and ADR-0001 (AIDD) guidance on traceability.
   • Derive tests from the updated contracts and acceptance criteria. Author failing tests first (unit/integration/e2e as appropriate), then implement the minimal defensive code required to make them pass.
   • Ensure defensive programming practices (validation, error handling, logging) and embed required observability signals (metrics/logs/traces) as specified by the story.

3. Execution discipline
   • Keep work traceable: reference the story, relevant epics, and contracts in commit messages and documentation.
   • Run the necessary linting/type checks/tests to prove quality gates pass, capturing evidence for the DoD analysis.

4. Definition of Done (DoD)
   • When implementation and tests are complete, document a “Definition of Done” analysis in the story document summarizing how each acceptance criterion, contract update, test result, documentation update, and observability requirement has been satisfied.
   • Include links or filenames for any new/updated assets (contracts, tests, docs).

5. Manual validation runbook
   • If the DoD criteria are met, add a manual validation runbook in `docs/smoke/`
   • Provide step-by-step instructions a developer can follow on a fresh branch: environment setup, commands to execute, data to seed, expected outcomes, and rollback guidance if validation fails.

6. Final deliverable
   • In your final response, summarize the DoR findings, contract-first/TDD execution, DoD results, test commands run (with outcomes), and point to the new smoke-test runbook. Highlight any follow-up tasks if DoD was not fully met.

---
---

# PROMPT: Maximum Guidance

You are an implementation agent working in `/workspace/op-cti`. Follow the global AIDD guardrails in `AGENTS.md` and `docs/adr/ADR-0001-aidd-framework.md` (contract-first, test-driven, defensive engineering, observability) throughout.

Story to implement: `<STORY_ID>`.

From the story, derive its associated epic and any referenced ADR/ARCH docs. Review the story, its acceptance criteria, contracts, test strategy, observability needs, and tasks before writing any code. Use the epic and referenced docs to stay aligned with approved contracts, observability goals, and governance rules.

---

### Definition of Ready (DoR) first

* Read the story, its epic, and all referenced ADR/ARCH documents to confirm required keys, versioning rules, and observability expectations.
* Inventory existing examples and backend usage patterns (schemas, validators, logging, metrics) to understand conventions.
* Identify gaps that block readiness (e.g., missing folders, absent fixtures, missing metrics stubs). Document the DoR analysis in the story file by adding a clearly labeled section summarizing prerequisites, open questions, and decisions/resolutions.
* If prerequisites are missing, implement the minimum preparatory work (like creating folder scaffolding) before coding the main feature, and record the steps taken to reach readiness.

**Only proceed to implementation once DoR is satisfied and documented.**

---

### Implementation (contracts-first, TDD, defensive)

Work in small, test-first increments. For each requirement, write/extend tests before implementing code.

#### Contracts

* Create authoritative schemas, configs, or other contracts at repository-appropriate paths (e.g., `schema/<area>/<name>.schema.json`), versioned according to conventions.
* Ensure metadata (`$id`, `$schema`, etc.) aligns with repository patterns.
* If runtime consumption requires bundling, add a copy or import path under the runtime package, documenting the duplication rationale.

#### Validator / Core module

* Introduce a dedicated module (e.g., `src/<area>/<name>Schema.ts`).
* Import the schema/contract; compile/initialize once and reuse.
* Expose a typed function for validation, returning a stable result shape (e.g., `{ valid, errors?, sanitized?, version }`).
* Map underlying library errors to deterministic codes with structured detail.
* Emit defensive logging and increment/decrement metrics.
* Define supporting types in a dedicated `types.ts` file.

#### Observability hooks

* Extend the telemetry layer to register histograms and counters as required by the story/epic.
* Provide helper methods on the metrics manager to record timings and error counts.
* Ensure integration so every validation attempt logs duration and increments counters.

#### Fixtures

* Add valid and invalid fixtures under a descriptive test data directory.
* Include coverage for both happy-path and edge/failure cases explicitly called out by the story.
* Keep filenames descriptive for quick reference.

#### Tests (write first)

* Create a dedicated unit test suite under the appropriate test folder.
* Validate valid fixtures pass and snapshot their normalized outputs (if sanitization occurs).
* Validate invalid fixtures fail with deterministic error codes and stable payloads.
* Assert contracts fail closed (reject unexpected additional properties, unknown keys, etc.).
* Measure validator timing (mock metrics manager) to ensure instrumentation is invoked.
* Stub logging for validation.
* Add integration tests if loader/consumption behavior requires it.

#### Performance considerations

* Ensure contracts/validators are compiled or initialized once and reused to meet performance targets defined in the story/epic.
* Add caching/memoization if necessary, with tests.

---

### Documentation

* Update the story with DoR and DoD results.
* Update referenced ADR/ARCH docs if architecture narratives are impacted.
* Add references to new schema/module paths.
* Provide inline JSDoc/comments to explain defensive measures and observability hooks.

---

### Testing & quality gates

Run tests and quality checks in the relevant package folder:

```
yarn test --runInBand <unit-test-path>
yarn test --runInBand
yarn lint
yarn check-ts
```

Capture outputs with ✅/⚠️/❌ status.

---

### Definition of Done (DoD) validation

* Verify all acceptance criteria from the story are satisfied and tested.
* Summarize validation in a `## Definition of Done Verification` section in the story file.
* Confirm documentation updates.
* Validate metrics/logs locally.

---

### Manual validation runbook

* Author a runbook under `docs/smoke/` (e.g., `validation-runbook-<story-short-name>.md`).
* Cover preconditions, environment setup, scenarios, expected results, and observability.

---

### Final steps

* Summarize work, tests executed, DoR/DoD highlights, and runbook addition.
* Follow repository contribution workflow: keep worktree clean, commit with a conventional message referencing the story, then call `make_pr`.
* Preserve license headers when editing files.
* Deliver in a single coherent implementation with clean, passing state.
