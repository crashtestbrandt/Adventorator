---
id: PROMPT-AIDD-DIVERGENCE
version: 1
author: Brandt
purpose: Analyze local AIDD implementation vs upstream AIDD framework; classify deviations.
---

Perform a structured comparative analysis between this repository's AI-Driven Development (AIDD) implementation (as expressed through local ADRs, architecture specs, implementation planning assets, and governance automation scripts) and the upstream canonical AIDD framework at `https://github.com/crashtestbrandt/AIDD` (main branch). Produce:
1. Candidate upstream improvements (local extensions with broad utility).
2. Project-specific (non-generalizable) deviations to retain locally only.
3. Misalignments that should be realigned in this repo to reduce divergence.

## Provided Local Artifacts (Scope Inputs)
- Core planning / lifecycle plan: `docs/implementation/aidd-plan.md`
- Definition-of-Ready / Definition-of-Done guidance: `docs/implementation/dor-dod-guide.md`
- Observability & feature flag integration plan: `docs/implementation/observability-and-flags.md`
- Improbability Drive implementation guide: `docs/implementation/improbability-drive-implementation.md`
- Action Validation epic & architecture linkage: `docs/implementation/epics/EPIC-AVA-001-action-validation-architecture.md`
- Core architecture specs:
  - `docs/architecture/ARCH-AVA-001-action-validation-architecture.md`
  - `docs/architecture/ARCH-CDA-001-campaign-data-architecture.md`
- ADR Set (governance & mechanisms):
  - `docs/adr/ADR-0001-planner-routing.md`
  - `docs/adr/ADR-0002-orchestrator-defenses.md`
  - `docs/adr/ADR-0003-executor-preview-apply.md`
  - `docs/adr/ADR-0004-mcp-adapter-architecture.md`
  - `docs/adr/ADR-0005-improbabilitydrive-contracts-and-flags.md`
  - `docs/adr/ADR-0006-event-envelope-and-hash-chain.md`
  - `docs/adr/ADR-0007-canonical-json-numeric-policy.md`
  - `docs/adr/ADR-0008-rng-streams-seed-derivation.md`
  - `docs/adr/ADR-0009-capability-approval-enforcement.md`
  - `docs/adr/ADR-0010-snapshot-fork-lineage.md`
  - `docs/adr/ADR-0011-package-import-provenance.md`
  - `docs/adr/ADR-0012-event-versioning-migration-protocol.md`
  - Template: `docs/adr/ADR-TEMPLATE.md`
- Epic documents (sample):
  - `docs/implementation/epics/EPIC-IPD-001-improbability-drive.md`
  - `docs/implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md`
  - `docs/implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md`
  - `docs/implementation/epics/EPIC-ACTLOG-001-activitylog-mechanics-ledger.md`
- Story documents (sample set):
  - `docs/implementation/stories/STORY-IPD-001A-contracts-and-flags.md` … through `STORY-IPD-001I-operational-rollout.md`
- Governance / traceability automation scripts:
  - `scripts/adr_lint.py`
  - `scripts/update_action_validation_traceability.py`
  - `scripts/validate_prompts_and_contracts.py`
- Prompt & contract validation integration (front-matter ADR linkage) via `scripts/validate_prompts_and_contracts.py`
- Local directory structures (derive during run):
  - `docs/adr/*`
  - `docs/architecture/*`
  - `docs/implementation/{epics,stories}/*`
  - `scripts/*.py` (governance-related subset above)
- CI / Quality references (status, guardrails) as presented in root `README.md`
- Naming conventions & ID taxonomy (EPIC-*, STORY-*, ADR-*) implied by filenames and enforced by linting scripts

If an upstream file is missing for any locally present concept (e.g., deterministic event envelope hashing), mark as "no upstream analogue".

## Remote (Upstream) Inputs Required
Fetch (read-only) from upstream AIDD repo:
- Root `README` / specification docs
- Principles / lifecycle / taxonomy definitions
- Directory structure (depth ≤ 3) for comparison

## Methodology (Agent MUST Follow)
1. Inventory Collection
   - Load local artifacts (list + short purpose notes)
   - Load upstream artifacts
2. Concept Extraction
   - Principles, lifecycle stages, artifact types, naming patterns, automation hooks, quality gates
3. Mapping Matrix Construction
   - For each concept dimension: classify relation (aligned | extended | diverged | novel | missing-local)
4. Deviation Classification
   - Heuristics:
     - Generalizable & low coupling → Candidate Upstream (Cat 1)
     - Domain/branding/runtime-specific coupling → Project-Specific (Cat 2)
     - Redundant/conflicting with upstream principle → Misalignment (Cat 3)
5. Impact Assessment
   - Cat 1: value (High/Med/Low), adoption friction, suggested upstream description
   - Cat 2: rationale, dependency summary
   - Cat 3: remediation steps & expected benefit
6. Risk & Opportunity Summary
7. Actionable Recommendations & Sequenced Roadmap
8. Produce structured outputs (Markdown ONLY; no JSON payload)

## Output Format (Markdown Only)
1. Executive Summary
2. Inventory Overview (tables)
3. Concept Mapping Matrix (compact)
4. Category (1) Candidate Upstream Improvements
5. Category (2) Project-Specific Retentions
6. Category (3) Misalignments & Remediation
7. Risks & Opportunities
8. Recommended Next Actions (ordered list)
9. Appendix: Raw Mapping Table (detailed rows)

## Structured Tables Specification
1. Inventory Table: `Scope (local|upstream) | Path | Type | Summary`
2. Mapping Matrix: `Dimension | Concept | Local | Upstream | Relationship | Notes`
3. Category Tables:
   - Candidate Upstream: `Concept | Justification | Value (H/M/L) | Adoption Friction (L/M/H) | Suggested Change`
   - Project-Specific: `Concept | Rationale | Key Dependencies | Risk If Upstreamed`
   - Misalignments: `Concept | Issue | Remediation | Benefit`
4. Summary Metrics: `Metric | Count/Value`
5. Recommendations: `# | Action | Category | Priority (H/M/L) | ETA | Owner (placeholder)`

## Validation Rules
- Every concept in category tables must appear in the Mapping Matrix.
- `Relationship=novel` implies Upstream=absent & Local=present.
- Misalignments must have `Relationship=diverged` or `missing-local`.
- Use `needs-verification` where upstream uncertainty exists (avoid hallucination).

## Constraints & Quality Checks
- Do not invent upstream concepts; mark gaps explicitly.
- Keep note fields ≤ 280 chars where possible.
- Use action verbs in recommendations.
- Avoid duplicated justifications; reference prior with `See: <concept>` if needed.

## Evaluation Rubric (Self-Check)
1. Coverage: All major local governance features (traceability log update script, ADR linting lifecycle states, deterministic event substrate lineage, RNG seed derivation policy, capability approval enforcement) classified.
2. Clarity: Distinct value/rationale per category entry.
3. Actionability: Recommendations use concrete verbs + targets.
4. Consistency: Counts in metrics align with tables.
5. Non-Redundancy: No duplicate concept keys across categories.

## Agent Execution Instructions
1. Gather required files (local) – list explicitly in output.
2. Retrieve upstream repository file list & core docs.
3. Build mapping & categories with heuristics.
4. Run rubric checklist; if any failure → internally revise before final output.
5. Emit Markdown ONLY (no JSON). No extra commentary outside sections.

## Example Concepts To Consider (Non-Exhaustive)
- ADR lifecycle status enforcement (allowed states enumeration)
- Automated traceability table regeneration for epics
- Prompt/contract front-matter ADR linkage validation
- Deterministic event envelope hashing & ordinal gap handling
- Snapshot fork lineage strategy
- RNG stream seed derivation policy
- Capability approval gate & enforcement path
- Package import provenance tracking
- Event versioning & migration protocol
- Separation of implementation plan vs DOR/DoD guide
- Integration of feature flags with governance (improbability drive)
- CI transparency of guardrails via README

## Deliverables
Return a single comprehensive Markdown report following the Output Format. No JSON or additional commentary outside defined sections.
