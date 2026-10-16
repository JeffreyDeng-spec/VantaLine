"""Exact reviewed privacy delta; historical model/PLC source fixtures stay immutable."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "eb5e873161bb5b81653aa7994ef8ce888d6ff62722485ef8d7851ff65bb57eb7"


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
