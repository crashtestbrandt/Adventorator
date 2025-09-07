# test_crypto.py

from Adventorator.crypto import verify_ed25519


def test_verify_rejects_bad_sig():
    ok = verify_ed25519("0" * 64, "123", b"{}", "0" * 128)
    assert ok is False
