"""Exact reviewed privacy delta; historical model/PLC source fixtures stay immutable."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "4c3c5b9d74a7402c258760f3a1c8a08ac3057238252c3bf193a63c4706db9c3f"


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
