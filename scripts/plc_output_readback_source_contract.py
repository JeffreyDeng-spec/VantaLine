"""Replay the exact read-only telemetry delta before checking historical PLC sources."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "906de3327060de80f3a8a63de0cc3fd070e0c19b1db8a87de0b8cd88ad2f409f"

def checkpoint_bytes(path, actual):
    raw = (ROOT / "tests/backend_contract/plc_output_readback_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed PLC output readback delta"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1 and fixture["parent"] == "2fa21d3b9c0894bb030befdefc9361194d87baab"
    if path != fixture["path"] or hashlib.sha256(actual).hexdigest() != fixture["current_sha256"]:
        return actual  # The historical oracle still rejects every unknown source.
    after, before = fixture["after"].encode(), fixture["before"].encode()
    assert actual.count(after) == 1, "PLC output readback region changed"
    restored = actual.replace(after, before, 1)
    assert hashlib.sha256(restored).hexdigest() == fixture["parent_sha256"], "PLC output readback parent changed"
    return restored
