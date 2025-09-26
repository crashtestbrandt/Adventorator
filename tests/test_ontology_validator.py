"""Unit tests for ontology validator (scripts/validate_prompts_and_contracts.py).

Covers:
- Happy path validation of valid fixtures
- Schema violations from invalid fixtures
- Duplicate identical definitions (idempotent)
- Conflict differing definitions (hard error)
- Deterministic ordering (run twice, same error ordering)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validate_prompts_and_contracts.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ontology"


def _run_validator(extra: list[str] | None = None) -> tuple[int, str, str]:
    cmd = [sys.executable, str(VALIDATOR), "--only-ontology"]
    if extra:
        cmd.extend(extra)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return proc.returncode, proc.stdout, proc.stderr


def test_valid_fixtures_pass():
    # Ensure the basic valid collection validates (if moved into contracts later this may adapt)
    # For now we copy the valid fixture into a temp contracts/ontology collection file to exercise validator
    import tempfile, json, shutil

    contracts_ontology = REPO_ROOT / "contracts" / "ontology"
    target_file = contracts_ontology / "__tmp_validator_collection.json"

    data = (FIXTURE_DIR / "valid" / "basic.json").read_text(encoding="utf-8")
    target_file.write_text(data, encoding="utf-8")
    try:
        code, out, err = _run_validator()
        assert code == 0, f"Expected success. stdout=\n{out}\nstderr=\n{err}"
    finally:
        if target_file.exists():
            target_file.unlink()


def test_invalid_fixtures_fail():
    # Aggregate invalid fixtures into a temporary collection and expect failures
    import json

    combined = {"version": 1, "tags": [], "affordances": []}
    for path in (FIXTURE_DIR / "invalid").glob("*.json"):
        obj = json.loads(path.read_text(encoding="utf-8"))
        combined["tags"].extend(obj.get("tags", []))
        combined["affordances"].extend(obj.get("affordances", []))

    target_file = REPO_ROOT / "contracts" / "ontology" / "__tmp_invalid.json"
    target_file.write_text(json.dumps(combined), encoding="utf-8")
    try:
        code, _out, err = _run_validator()
        assert code == 1, "Invalid fixtures should fail validation"
        assert "schema violation" in err or "missing" in err.lower()
    finally:
        if target_file.exists():
            target_file.unlink()


def test_duplicate_identical_idempotent():
    import json

    # Build two files with identical tag definitions
    contracts_ontology = REPO_ROOT / "contracts" / "ontology"
    a = contracts_ontology / "__dup_a.json"
    b = contracts_ontology / "__dup_b.json"

    base = json.loads((FIXTURE_DIR / "duplicate" / "identical_a.json").read_text(encoding="utf-8"))

    a.write_text(json.dumps({"tags": [base["tags"][0]]}), encoding="utf-8")
    b.write_text(json.dumps({"tags": [base["tags"][0]]}), encoding="utf-8")
    try:
        code, out, err = _run_validator()
        # Duplicate identical should not error
        assert code == 0, f"Expected idempotent duplicates to pass. stderr=\n{err}"
    finally:
        for f in (a, b):
            if f.exists():
                f.unlink()


def test_conflict_definition_fails():
    import json

    contracts_ontology = REPO_ROOT / "contracts" / "ontology"
    a = contracts_ontology / "__conflict_a.json"
    b = contracts_ontology / "__conflict_b.json"

    diff_a = json.loads((FIXTURE_DIR / "conflict" / "different_a.json").read_text(encoding="utf-8"))
    diff_b = json.loads((FIXTURE_DIR / "conflict" / "different_b.json").read_text(encoding="utf-8"))

    a.write_text(json.dumps({"tags": [diff_a["tags"][0]]}), encoding="utf-8")
    b.write_text(json.dumps({"tags": [diff_b["tags"][0]]}), encoding="utf-8")
    try:
        code, _out, err = _run_validator()
        assert code == 1, "Conflicting definitions should fail"
        assert "conflict tag_id" in err
    finally:
        for f in (a, b):
            if f.exists():
                f.unlink()


def test_ordering_determinism():
    import json
    from time import perf_counter

    contracts_ontology = REPO_ROOT / "contracts" / "ontology"
    order_file = contracts_ontology / "__ordering.json"
    data = json.loads((FIXTURE_DIR / "valid" / "basic.json").read_text(encoding="utf-8"))
    # Duplicate tags reversed to test determinism; validator should ignore ordering for duplicates
    tags = list(reversed(data["tags"]))
    order_file.write_text(json.dumps({"tags": tags}), encoding="utf-8")
    try:
        # Run twice and ensure same exit + comparable timings
        code1, out1, err1 = _run_validator()
        t1 = perf_counter()
        code2, out2, err2 = _run_validator()
        t2 = perf_counter()
        assert code1 == code2 == 0
        filt1 = [l for l in out1.splitlines() if not l.startswith("ontology.validate summary:")]
        filt2 = [l for l in out2.splitlines() if not l.startswith("ontology.validate summary:")]
        assert filt1 == filt2
        # Basic sanity: second run not drastically slower (no strict perf assert, just placeholder)
        assert abs((t2 - t1)) < 5
    finally:
        if order_file.exists():
            order_file.unlink()
