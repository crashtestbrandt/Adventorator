# AIDD DoR/DoD Rituals for Adventorator

The AI-Driven Development pipeline expects every Epic → Story → Task unit to satisfy a shared Definition of Ready (DoR) before work begins and Definition of Done (DoD) before it is considered complete. This guide explains how Adventorator teams and AI contributors incorporate the checklists baked into our GitHub templates into sprint rituals.

## Definition of Ready Checklist

Use this checklist during backlog refinement. If any item is missing, keep the issue in "Draft".

- ✅ Parent linkage: Feature Epic issues reference related ADRs, C4 assets, and contracts.
- ✅ Scope clarity: Story summary distinguishes in-scope vs. out-of-scope items and lists affected feature flags.
- ✅ Contract-first: Proposed schema or API changes exist in `contracts/` and consumers have been notified.
- ✅ Test strategy: The "Test Strategy" field in the issue template enumerates required unit, integration, contract, and AI evaluation coverage.
- ✅ Observability plan: Metrics/logs/traces appear in the "Observability Spec" field with owners and budgets.
- ✅ Task breakdown: Each per-prompt Task has an assignee or owner placeholder and clearly states expected artifacts (code, docs, evaluations).

Facilitation tips:
- During refinement, open the issue and walk through the template fields aloud.
- Capture open questions inline as unchecked checklist items so AI agents can address them asynchronously.

## Definition of Done Checklist

Review this checklist in standups and before closing an issue. It extends the template defaults with Adventorator-specific requirements.

- ✅ All acceptance criteria demonstrated via automated tests or documented manual runs.
- ✅ Contracts versioned with backward compatibility notes and, when relevant, CDC fixtures updated.
- ✅ Observability updates merged: metrics registered, logging fields documented, dashboards or alerts updated.
- ✅ Security gates (SAST, dependency audit) green; performance budgets within thresholds.
- ✅ Documentation refreshed: README snippets, runbooks, and developer guides reference new behavior.
- ✅ Story or Task issue links corresponding PR(s) and ADR(s); traceability table in the relevant epic updated.

## Sprint Ceremony Integration

- **Backlog Refinement.** Apply the DoR checklist above; move issues to "Ready" once all boxes are checked.
- **Sprint Planning.** Confirm that each selected issue has linked Tasks and owner placeholders. If a DoR item regresses, return the issue to refinement.
- **Daily Standup.** Highlight DoD blockers (e.g., missing metrics dashboards) so specialized contributors can swarm.
- **Review/Demo.** Demonstrate observability updates and feature flag rollout steps alongside functionality to satisfy DoD transparency expectations.
- **Retro.** Track DoR/DoD misses and feed improvements back into templates or automation.

## Automation Hooks

- The PR template requires linking Story/Task issues; reviewers verify DoR/DoD items before approving.
- Planned CI work (Phase 3) will enforce contract validation and ADR linkage; this document serves as a manual checklist until then.

Document owners: Delivery leads and operations should revisit this guide quarterly to incorporate lessons learned and tooling changes.
