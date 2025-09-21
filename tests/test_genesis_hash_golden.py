from pathlib import Path

from Adventorator.events import envelope


def test_genesis_payload_hash_golden():
    golden_path = Path(__file__).parent / "golden" / "genesis_payload_hash.txt"
    hex_value = golden_path.read_text().strip().splitlines()[-1].strip()
    assert len(hex_value) == 64
    assert envelope.GENESIS_PAYLOAD_HASH.hex() == hex_value
    # Defensive: ensure canonical encoder of empty dict still matches
    assert envelope.compute_payload_hash({}).hex() == hex_value
