"""Exact reviewed privacy delta; historical model/PLC source fixtures stay immutable."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "8452e591580f7e4d7f7e3985c9f390dad5a5099dd294032034d1ea53f10adba7"


def checkpoint_bytes(path, actual):
    raw = (ROOT / "tests/backend_contract/model_privacy_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed model privacy fixture"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1
    for name, expected in fixture["new_sources"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, "Privacy source changed: " + name
    change = fixture["files"].get(path)
    if change is None:
        return actual
    digest = hashlib.sha256(actual).hexdigest()
    if digest == change["parent_sha256"]:
        return actual
    assert digest == change["current_sha256"], "Unknown model privacy source: " + path
    parent = change["parent_source"].encode()
    assert hashlib.sha256(parent).hexdigest() == change["parent_sha256"], "Privacy parent changed"
    return parent
