"""Exact reviewed privacy delta; historical model/PLC source fixtures stay immutable."""
import hashlib
import json
from pathlib import Path
from functools import lru_cache
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "61fc66d3023bbc28c25ec66b912ea73562418f9fc9d2f96a0e479c75862e0af9"


@lru_cache(maxsize=4)
def checked_fixture(raw):
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed model privacy fixture"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1
    return fixture


@lru_cache(maxsize=64)
def exact_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checkpoint_bytes(path, actual):
    raw = (ROOT / "tests/backend_contract/model_privacy_delta.json").read_bytes()
    fixture = checked_fixture(raw)
    change = fixture["files"].get(path)
    if change is None:
        return actual
    for name, expected in fixture["new_sources"].items():
        assert exact_digest((ROOT/name).read_bytes()) == expected, "Privacy source changed: " + name
    digest = exact_digest(actual)
    if digest == change["parent_sha256"]:
        return actual
    assert digest == change["current_sha256"], "Unknown model privacy source: " + path
    parent = change["parent_source"].encode()
    assert exact_digest(parent) == change["parent_sha256"], "Privacy parent changed"
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
