import scripts.update_action_validation_traceability as trace

CORE_DOC = """# EPIC-CORE-001 — Core AI Systems Hardening

## Stories

### STORY-CORE-001A — Example Story A
Stuff
- [ ] `TASK-CORE-VAL-01` — Do thing
- [ ] `TASK-CORE-PROMPT-02` — Do other

### STORY-CORE-001B — Example Story B
- [ ] `TASK-CORE-DEF-04`
"""


def test_generic_table_pending(tmp_path, monkeypatch):
    # Monkeypatch search to return empty so everything shows pending
    monkeypatch.setattr(trace, "gh_issues_search", lambda q: [])
    doc = tmp_path / "core.md"
    doc.write_text(CORE_DOC)
    table = trace.build_table_generic(doc)
    assert "Epic Issue" in table
    assert "_Pending_" in table
    assert "Story 001A" in table
    assert "Story 001B" in table
