"""Fixed additive admin workbench delta; preserve historical source oracles."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/backend_contract/admin_user_data_delta.json'


def fixture():
    raw=FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "36829f57b3da1976a6338c330fca5b873043b4fe69c7cebc4f73708b7dc9b1b0", 'Unreviewed admin data fixture'
    data=json.loads(raw)
    for path, expected in data['new_sources'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected, 'Admin service changed: '+path
    return data


def checkpoint_bytes(path, actual):
    change=fixture()['files'].get(path)
    if change is None:
        return actual
    assert hashlib.sha256(actual).hexdigest() == change['current_sha256'], 'Admin descendant changed: '+path
    parent=change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest() == change['parent_sha256'], 'Admin parent changed: '+path
    return parent
