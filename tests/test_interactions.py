# test_interactions.py

from fastapi.testclient import TestClient

from Adventorator.app import app

client = TestClient(app)


def test_missing_headers_401():
    r = client.post("/interactions", content=b"{}")
    assert r.status_code == 401
