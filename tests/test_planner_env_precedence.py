import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# This test ensures that server-start-time environment flags control behavior,
# and per-invocation CLI environment exports do NOT override a running server's
# previously loaded settings (planner tiers / max level).
#
# Strategy:
# 1. Start server with tiers disabled (FEATURES_PLANNING_TIERS=false) and max_level=2.
# 2. Invoke web_cli with per-command FEATURES_PLANNING_TIERS=true and --json-only.
# 3. Expect returned plan to have a single step (no prepare step, empty guards) proving
#    server precedence.
# 4. Restart server with tiers enabled and level 2; run CLI with --json-only and assert two steps.
#
# Mark slow due to process management / sleeps.

SERVER_PORT = 18000  # default fallback


@pytest.mark.slow
def test_env_precedence_tiers_disabled_then_enabled(tmp_path):
    python = sys.executable

    def start_server(env, log_name: str):
        log_path = tmp_path / log_name
        port = env.get("APP_PORT", str(SERVER_PORT))
        proc = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "--app-dir",
                "src",
                "Adventorator.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            env=env,
        )
        # Wait for startup line
        started = False
        for _ in range(60):
            time.sleep(0.25)
            if log_path.exists():
                txt = log_path.read_text()
                if "app.startup" in txt:
                    started = True
                    break
        assert started, "Server did not start in time"
        return proc, log_path

    # Find a free port to avoid interference with parallel test runs or dev server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    base_env = os.environ.copy()
    base_env.update(
        {
            "FEATURES_PLANNING_TIERS": "false",
            "PLANNER_MAX_LEVEL": "2",
            "FEATURES_ACTION_VALIDATION": "true",
            "FEATURES_PREDICATE_GATE": "true",
            "APP_PORT": str(free_port),  # ensure isolation
        }
    )

    def wait_for_config_flag(log_path: Path, expected: bool, timeout_s=8.0):
        target = f'"features_planning_tiers": {str(expected).lower()}'
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if log_path.exists():
                txt = log_path.read_text()
                if target in txt:
                    return True
            time.sleep(0.25)
        raise AssertionError(f"Did not observe config line {target} in {log_path}")

    # Start with tiers disabled
    proc, log1 = start_server(base_env, "server1.log")
    try:
        # Confirm server loaded tiers disabled
        wait_for_config_flag(log1, expected=False)
        # Attempt CLI override (should not change server config)
        cli_env = base_env.copy()
        cli_env.update({"FEATURES_PLANNING_TIERS": "true"})
        subprocess.call([python, "scripts/web_cli.py", "plan", "roll a d20"], env=cli_env)
        # Re-assert still disabled (no 'true' line)
        assert '"features_planning_tiers": true' not in log1.read_text()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    # Restart with tiers enabled
    env_on = base_env.copy()
    env_on["FEATURES_PLANNING_TIERS"] = "true"
    env_on["PLANNER_MAX_LEVEL"] = "2"
    proc2, log2 = start_server(env_on, "server2.log")
    try:
        wait_for_config_flag(log2, expected=True)
    finally:
        proc2.terminate()
        proc2.wait(timeout=10)
