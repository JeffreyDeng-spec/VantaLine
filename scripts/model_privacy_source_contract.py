"""Exact reviewed privacy delta; historical model/PLC source fixtures stay immutable."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "e7aaa292604eb7065bd8f435f4a8dff863077d47114d5267b90d85678778226f"


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


def middleware_checkpoint(entries, presentation):
    """Validate the added owner and position before comparing the frozen parent."""
    from local_inspection_service.privacy.http import ModelPrivacyMiddleware
    from local_inspection_service.privacy.presentation import Presentation
    assert type(presentation) is Presentation
    selected = [entry for entry in entries if entry.cls is ModelPrivacyMiddleware]
    assert len(selected) == 1 and entries[-1] is selected[0], "Privacy middleware must run inside transport wrappers"
    assert selected[0].kwargs == {"presentation": presentation}, "Privacy middleware owner changed"
    return entries[:-1]
