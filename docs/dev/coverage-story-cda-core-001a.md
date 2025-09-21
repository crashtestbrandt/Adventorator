# Coverage Report — STORY-CDA-CORE-001A

Date: 2025-09-21
Branch: codex/implement-story-cda-core-001a

Command:
```
. .venv/bin/activate && pytest
```

Summary: 191 passed, 2 skipped; overall line coverage 81% (4677 stmts / 904 miss).

| Module | Coverage | Key Miss Highlights |
|--------|----------|---------------------|
| action_validation.* | ~89–100% core modules | Remaining gaps in predicate_gate branches (conflict/failure paths not triggered) |
| commands.* | Mixed (52%–100%) | Lower in `do.py` (future story instrumentation) |
| executor/orchestrator | 79–81% | Multiphase error handling branches untested (intentional defer) |
| repos.py | 70% | Long tail of rarely exercised persistence helpers; append_event path covered |

Raw excerpt (top-level):
```
TOTAL 4677 statements; 904 missed; 81% line coverage
191 passed, 2 skipped in 50.34s
```

HR-007 Status: Coverage snapshot captured; attach this file in PR summary under Observability / Quality Gates.

Follow-ups (optional):
- Add targeted tests for predicate_gate failure branches.
- Increase repos.py coverage for rollback/error retry code.
- Exercise executor multi-tool error handling (Phase 8+ stories).
