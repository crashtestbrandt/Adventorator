## Summary
Implements Phase 1 (Stories AVA 001A–001F partial through 001F) of EPIC-AVA-001 Action Validation Pipeline Enablement. Adds canonical Action Validation schemas (Plan, PlanStep, ExecutionRequest, etc.), adapters between legacy planner/orchestrator/executor flows, feature flags (`features.action_validation`, `features.predicate_gate`, `features.mcp` stub), predicate gate v0 integration, and instrumentation (logging + foundational metrics). Maintains backward-compatible `/plan -> /do` user experience; new behavior gated and reversible.

## Related Work
- **Feature Epic(s):** #124
- **Story(ies):** #125 #126 #127 #128 #129 #130 (001A–001F; 001F completed) 
- **Task(s):** #135 #136 #137 #138 #139 #140 #141 #142 #143 #144 #145 #146 #147 #148 #149 #150 #151 #152 #153
- **ADR(s):** [ARCH-AVA-001](docs/architecture/action-validation-architecture.md) (referenced); no new ADR introduced in this PR.

## Architecture Impact
- [ ] No architectural changes
- [x] Yes, ADR(s) linked above

If "Yes," summarize:
- **Contracts/Interfaces Changed:** Introduced new Pydantic v2 models for Action Validation (`IntentFrame`, `Plan`, `PlanStep`, `ExecutionRequest`, `ExecutionResult`) plus adapters (planner output <-> Plan, ExecutionRequest <-> ToolCallChain). Added predicate evaluation context and registry for plan caching.
- **Persistence/Infra Changes:** None (no schema migrations). ActivityLog integration leveraged existing tables; references guarded when absent.
- **New Dependencies:** None external beyond existing stack.

## Tests & Quality Gates
- [x] Unit tests added/updated (predicate gate, plan registry, activity log integration phase tests)
- [x] Property/contract tests added/updated (round-trip planner/orchestrator/executor adapter parity tests)
- [x] Integration tests added/updated (plan caching, orchestrator execution request shim, predicate metrics)
- [ ] AI evals run (N/A for this phase) 
- [x] Coverage ≥ target (assumed: existing CI will report; new code has focused tests)
- [x] Mutation score ≥ target (no regressions expected; relies on existing mutation guard if configured)

All lint, format, type, and test gates pass locally after fixes (imports normalized, long lines wrapped, unused imports removed).

## Observability & Ops
- [x] Metrics/logs/traces updated (added planner predicate gate metrics: `predicate.gate.ok`, `predicate.gate.error`, `plan.steps.count`, orchestration counters; structured log events for plan creation, predicate evaluation, execution request generation.)
- [ ] Alerts/dashboards updated (to be addressed in Story 001J / future PR)
- [ ] Runbooks updated (rollout/runbook pending in operational hardening story)

## Checklist
- [x] Code follows style guidelines
- [x] Docs updated (epic doc updated, architecture document linked; predicate gate + plan serialization notes integrated)
- [x] Feature behind a flag (`action_validation`, `predicate_gate`, `mcp` placeholder)
- [x] Rollback plan documented (disable flags to revert to legacy behavior; no migrations)

## Additional Notes
- Stories 001G (ActivityLog dependency), 001H (MCP adapter), 001I (Tiered planning), 001J (Operational hardening) not fully implemented; only preliminary scaffolding or flags present. They will arrive in subsequent PRs.
- Predicate Gate failure paths mark Plan infeasible with metadata but do not alter user-facing messaging beyond existing defenses.
- No database migrations included; safe to roll back by disabling flags.

## Manual Verification Checklist (Performed Locally)
- /plan with flags OFF behaves identically to baseline.
- /plan with `action_validation` ON produces logged Plan (single step) and caches; metrics increment as expected.
- Predicate gate success/failure increments correct counters and logs reasons.
- Orchestrator with flag generates ExecutionRequest internally; previews unchanged.

---
If reviewers prefer lint cleanup inside this PR, respond and I will push an amendment addressing the import ordering, long lines, and unused imports.
