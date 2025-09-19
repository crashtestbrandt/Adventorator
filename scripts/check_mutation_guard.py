#!/usr/bin/env python3
"""Run a targeted mutation check to ensure critical metrics tests fail when broken."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET_FILE = Path("src/Adventorator/metrics.py")
SENTINEL = "return _counters.get(name, 0)"
MUTATION = "return 0"
TEST_COMMAND = ["pytest", "-q", "tests/test_metrics_counters.py"]


def main() -> int:
    original = TARGET_FILE.read_text(encoding="utf-8")
    if SENTINEL not in original:
        print(
            "Expected sentinel expression not found in metrics module;"
            " update check_mutation_guard.py.",
            file=sys.stderr,
        )
        return 1

    mutated = original.replace(SENTINEL, MUTATION, 1)
    TARGET_FILE.write_text(mutated, encoding="utf-8")
    try:
        print("Running mutation guard tests...")
        proc = subprocess.run(TEST_COMMAND, check=False)
    finally:
        TARGET_FILE.write_text(original, encoding="utf-8")

    if proc.returncode == 0:
        print(
            "Mutation survived: tests passed with broken counter implementation.", file=sys.stderr
        )
        return 1

    print("Mutation killed as expected (tests failed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
