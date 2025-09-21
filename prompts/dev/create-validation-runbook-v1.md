---
version: 1
author: Brandt
purpose: Generate an e2e runbook a dev can follow to smoke/regression test a change.
---

Produce an end-to-end validation runbook a developer can use to manually validate completed functionality and no regression for <!-- AIDD item -->. Capture the runbook in a new .md file in `./docs/smoke/`.

The runbook should assume a fresh clone of the repo, and should provide steps for standing up locally as well as with Docker, and testing with ./scripts/web_cli.py as well as Discord.

Requirements:
1. Title format: `Validation Runbook — <AIDD item short name>`.
2. Audience + status line (Draft/Final) at top.
3. Include: Preconditions, Environment Setup (local + Docker), Feature Flag Matrix (if applicable), Validation Scenarios (grouped by functional area), Observability (logs + metrics), Rollback/Disable procedure, Golden / Snapshot integrity, Failure Triage table, Completion checklist, Future hooks.
4. Commands must be copy-paste friendly, each in fenced blocks with language annotation.
5. Explicitly list required environment variables and default values / safe states.
6. Avoid duplicating deep architecture detail—link to ADRs or epic docs instead.
7. Provide both CLI (`./scripts/web_cli.py`) and Discord (if integrated) pathways; if Discord not configured, instruct how to skip.
8. Every validation scenario should state: Purpose, Inputs, Expected Result, Observability signals (log event / metric / side-effect).
9. Checklist entries must be actionable and binary (pass/fail) using `[ ]` boxes for manual ticking.
10. End with a summary paragraph of any watch items or known non-blocking deviations.

Template Skeleton (the generated runbook SHOULD follow this ordering):
```
# Validation Runbook — <AIDD item>
Status: Draft | Audience: Dev / Reviewer / QA
Scope: <one-line objective>

## 1. Preconditions
## 2. Environment Setup
### 2.1 Local
### 2.2 Docker
## 3. Feature Flags / Config Matrix
## 4. Core Validation Scenarios
### 4.x <Scenario Group>
## 5. Negative / Edge Cases
## 6. Observability (Logs & Metrics)
## 7. Rollback / Disable Procedure
## 8. Golden / Snapshot Integrity
## 9. Failure Triage
## 10. Completion Checklist
## 11. Future Hooks
## 12. Appendices / References
```

Checklist (meta – for the generated runbook itself):
- [ ] All required sections present in final doc.
- [ ] Each scenario lists Purpose / Steps / Expected / Observability.
- [ ] At least one rollback path documented.
- [ ] Feature flags (or N/A justification) explicitly addressed.
- [ ] Failure triage table includes symptom, likely cause, action.
- [ ] Completion checklist uses `[ ]` boxes and is exhaustive.

On completion of generation, the assistant should clearly state if all checklist items were satisfied. If any are missing, list remediation actions instead of claiming success.

