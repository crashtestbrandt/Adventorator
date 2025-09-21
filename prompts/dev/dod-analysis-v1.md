---
id: PROMPT-DOD-ANALYSIS-V1
version: 1
model: governance-analysis
author: Brandt
owner: AIDD Governance WG
adr: ADR-0003
purpose: Provide a rigorous, traceable Definition of Done (DoD) analysis ensuring all delivery, quality, and governance criteria are satisfied prior to closure of <!-- AIDD item -->.
---

Perform a comprehensive Definition of Done (DoD) verification for <!-- AIDD item -->.

Instructions:
1. Confirm the work item identifier (Epic/Story/Task) and restate the implemented capability in one sentence.
2. Walk the checklist in order. Mark each line `[x]` when satisfied, `[ ]` if unmet, or `[ ] (n/a)` if legitimately not applicable (must justify N/A). Do not remove lines.
3. Provide inline notes for context, linking to commits, PRs, test reports, or docs.
4. All mandatory items must be `[x]` (not N/A) before declaring completion.
5. Append: `DoD Achieved: <!-- UTC timestamp -->` upon successful completion.
6. If any item cannot be satisfied now, produce a follow-up ticket reference and rationale; DoD cannot be declared until resolved or explicitly waived by a named authority.

Checklist (Definition of Done):

Functional & Acceptance
- [ ] All acceptance criteria demonstrably met (reference test names / manual validation steps).
- [ ] Feature flags behave as specified (on-path and off-path verified).
- [ ] Edge cases exercised (list any intentionally deferred with justification).

Code & Implementation
- [ ] Code merged or in final PR with all review comments resolved.
- [ ] No debug / experimental code left (print, TODO without ticket, dead branches).
- [ ] Configuration defaults safe (flags default to disabled or conservative state).

Quality & Testing
- [ ] Unit tests added/updated (list key test modules).
- [ ] Integration / end-to-end tests present where applicable.
- [ ] Golden / snapshot fixtures updated or confirmed stable.
- [ ] Negative / failure-path tests included (or rationale for absence).
- [ ] Mutation / property / fuzz tests (if required by risk profile) executed or N/A justified.
- [ ] Test suite passes locally (attach summary: pass count, skips).
- [ ] Code coverage unchanged or improved for touched modules (list deltas if reduced).

Observability & Metrics
- [ ] Structured logs implemented (event names + fields documented).
- [ ] Metrics/counters/gauges registered and names stable.
- [ ] Alerts / dashboards updated or not required (justify).
- [ ] Log noise / cardinality reviewed (no unbounded labels).

Documentation & Governance
- [ ] ADRs written/updated and committed (list numbers or N/A).
- [ ] Architecture diagrams updated (paths in `docs/architecture/`).
- [ ] Runbook / operational docs updated (`docs/smoke/` or `docs/dev/`).
- [ ] CHANGELOG entry added or deemed unnecessary (justify if skipped).
- [ ] Traceability artifacts (epic/story implementation plan, contracts, prompts) updated and validated (`make quality-gates`).

Security & Compliance
- [ ] Input validation / sanitation in place for new surfaces.
- [ ] Secrets not committed; config uses env or secret manager.
- [ ] Permissions / authorization model unchanged or adjustments reviewed.
- [ ] Dependency changes scanned (SCA) or no new packages added.

Performance & Reliability
- [ ] Latency / throughput expectations met (spot measurement or existing budgets referenced).
- [ ] No known scalability regressions (load pattern assumptions recorded).
- [ ] Resource usage (CPU/memory) acceptable in dev/local test.
- [ ] Failure handling / retry / idempotency paths validated.

Data & Persistence
- [ ] Migrations applied forward & rollback tested (or N/A - no schema change).
- [ ] Data model changes versioned and documented.
- [ ] Backfill / data transform tasks executed or scheduled (if needed).

Operations & Deployment
- [ ] Zero-downtime deployment verified or outage window communicated.
- [ ] Rollback procedure verified (flag flip, revert commit, schema safe).
- [ ] No orphaned feature flags (unused flags removed or ticketed for cleanup).
- [ ] Post-deploy smoke plan defined (who + when).

Handover & Sustainability
- [ ] Bus factor acceptable (knowledge shared / PR reviewed by >1 engineer).
- [ ] Follow-up / hardening tickets created for deferred improvements (list IDs).
- [ ] Maintenance burden assessed (cron, background tasks, cost) and acceptable.

Definition Completeness
- [ ] All checklist items satisfied (no remaining plain `[ ]`).
- [ ] Risks re-assessed; none elevated to block release.
- [ ] Stakeholders (product, QA, platform, security as applicable) sign-off recorded.

On completion, add a concise summary paragraph plus any residual watch items for early production monitoring.

If gaps remain, do not declare DoD -- return remediation steps instead.
