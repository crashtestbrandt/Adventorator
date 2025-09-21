---
id: PROMPT-DOR-ANALYSIS-V1
version: 1
model: governance-analysis
author: Brandt
owner: AIDD Governance WG
adr: ADR-0003
purpose: Verify project is in an appropriate state prior to moving forward with a new epic, story, or task.
---

Perform a rigorous Definition of Ready (DoR) analysis for <!-- AIDD item -->.

Instructions:
1. Identify the work item by stable identifier (Epic/Story/Task code) and restate its objective in one sentence.
2. For each checklist category below, explicitly mark each line with `[x]` (met) or `[ ]` (gap). Do not delete any lines. Add clarifying notes inline after a `-` dash if needed.
3. Where a gap exists, propose a concrete remediation action and (if possible) an owner.
4. Stop when all mandatory items are `[x]`. Then append a line: `DoR Achieved: <UTC timestamp>`.
5. If any item is intentionally deferred, mark `[ ] (deferred)` and justify why deferral does not block safe start.

Checklist (Definition of Ready):

Scope & Intent
- [ ] Problem statement is unambiguous and user / system value articulated.
- [ ] Success criteria (acceptance criteria) are enumerated and testable.
- [ ] Out-of-scope boundaries stated to prevent scope creep.

Traceability & Governance
- [ ] Linked to roadmap / AIDD epic path (docs/implementation/epics/*) with upstream dependency references.
- [ ] Related ADRs exist (or ADR stubs created) for any architectural decisions; numbers listed.
- [ ] Contracts (`contracts/`) and prompts (`prompts/`) impacts identified (list files or declare N/A).
- [ ] Issue / template artifacts (GitHub issue or PR template section) reflect this scope.

Risks & Assumptions
- [ ] Key assumptions documented (performance, security, external services, rate limits, latency budgets).
- [ ] Risks assessed with mitigation or monitoring plan.
- [ ] Rollback / feature flag strategy defined (flag name + default state + failure detection trigger).

Design Readiness
- [ ] High-level flow / sequence or component diagram exists or is not needed (justify if absent).
- [ ] Data model or schema impacts listed (including migrations plan or N/A).
- [ ] Interfaces / public APIs (internal or external) with expected I/O shapes defined.
- [ ] Performance / mutation / concurrency considerations evaluated.

Quality Gates
- [ ] Test strategy outlined (unit, integration, golden, property, performance, chaos—mark those applicable).
- [ ] Metrics & logging events enumerated (names + rationale) or N/A justified.
- [ ] Observability review: how to detect success vs. regression in prod.
- [ ] Security / validation / input sanitization requirements listed.

Operational Readiness
- [ ] Deployment impact (zero-downtime, migrations ordering) addressed.
- [ ] Runbook / manual validation steps drafted or referenced (path provided).
- [ ] Backout plan documented (flag flip, revert commit, data restore steps if needed).
- [ ] Capacity / cost considerations assessed (N/A allowed with justification).

Dependencies & Resources
- [ ] External service / API dependencies enumerated (auth, rate limits, credentials availability).
- [ ] Team / calendar dependencies (e.g., needs security review slot) noted.
- [ ] Tooling or script updates required identified.

Definition Completeness
- [ ] All gaps above have a remediation owner/action.
- [ ] No blocking unanswered questions remain.
- [ ] Stakeholders acknowledged (reviewers, domain SMEs) and availability confirmed.

When complete, provide a concise summary paragraph highlighting any watch-points.

If there are any gaps, work with me to fix them; once all required items are `[x]`, explicitly state DoR Achieved.