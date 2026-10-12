"""Exact output-value addition over the immutable pre-feature source oracle."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "c1a740d97ddadb4af467d940fd20d70b3e67a792304a49f84713c56e04ccf95e"

def checkpoint_bytes(path, actual):
    raw = (ROOT / "tests/backend_contract/plc_result_values_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed PLC result values delta"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1 and fixture["parent"] == "040ec66845b1179b2125a54828e6df6bcb4cb43c"
    change = fixture["files"].get(path)
    if change is None:
        return actual
    digest = hashlib.sha256(actual).hexdigest()
    if digest in [change["parent_sha256"], *change["accepted_ancestors"]]:
        return actual
    assert digest == change["current_sha256"], "Unknown PLC result values source: " + path
    parent = change["parent_source"].encode()
    assert hashlib.sha256(parent).hexdigest() == change["parent_sha256"], "PLC result values parent changed"
    return parent
