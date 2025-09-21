---
id: PROMPT-VALIDATION-EXECUTE-V1
version: 1
model: governance-validation
author: Brandt
owner: QA & Delivery WG
adr: ADR-0003
purpose: Interactively execute a validation runbook to smoke/regression test a change.
---

Execute <!-- Validation runbook --> step-by-step. Attempt to run any commands you can automatically. If you have to spin up long-running processes as dependencies for other commands, background them and clean them up later.

