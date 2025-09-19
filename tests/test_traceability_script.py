import types
import scripts.update_action_validation_traceability as mod

class GhCallRecorder:
    def __init__(self):
        self.calls = []
    def view_issue(self, number):
        titles = {
            124: "[Epic] EPIC-AVA-001 Action Validation Pipeline Enablement",
            125: "[Story] STORY-AVA-001A Contracts and feature flag scaffolding",
        }
        return {"number": number, "title": titles[number], "state": "open"}

rec = GhCallRecorder()


def fake_check_output(args, text=True):
    if args[:3] == ["gh","issue","view"]:
        num = int(args[3])
        return mod.json.dumps(rec.view_issue(num))
    if args[:3] == ["gh","search","issues"]:
        query = args[3]
        if query.startswith("STORY-AVA-001"):
            # Return subset with one story
            return mod.json.dumps([
                {"number":125,"title":"[Story] STORY-AVA-001A Contracts and feature flag scaffolding","state":"open"}
            ])
        if query.startswith("TASK-AVA"):
            return mod.json.dumps([
                {"number":135,"title":"[Task] TASK-AVA-SCHEMA-01 Implement core AVA schemas","state":"open"},
                {"number":136,"title":"[Task] TASK-AVA-CONVERT-02 Add legacy converters","state":"open"},
            ])
    raise AssertionError(f"Unexpected args {args}")


def test_build_table_monkeypatch(monkeypatch):
    monkeypatch.setattr(mod.subprocess, 'check_output', fake_check_output)
    table = mod.build_table()
    assert "Epic Issue" in table
    assert "Story 001A" in table
    assert "#135-#136" in table or "#135, #136" in table
