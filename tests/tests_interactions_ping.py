# tests/test_interactions_ping.py
import json

from fastapi.testclient import TestClient

import Adventorator.app as appmod
from Adventorator.app import app

client = TestClient(app)


def test_ping_returns_pong(monkeypatch):
    # Bypass signature verification
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    body = {"type": 1}
    r = client.post(
        "/interactions",
        content=json.dumps(body).encode(),
        headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"},
    )
    assert r.status_code == 200
    assert r.json() == {"type": 1}
