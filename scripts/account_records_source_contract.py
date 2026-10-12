"""Exact additive records inverse; retained historical fixtures are unchanged."""
from user_records_recovery_source_contract import checkpoint_bytes as recovery_checkpoint
from functools import lru_cache
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
@lru_cache(maxsize=4)
def parse_fixture(raw):
    return json.loads(raw)

def checkpoint_bytes(path, actual):
    actual = recovery_checkpoint(path, actual)
    raw = (ROOT/'tests/backend_contract/account_records_delta.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "e5e7caf439cdfee37bcc73e08f86617ab7aa3c0098cb5b10b291e773a89126a9", 'Unreviewed account records fixture'
    fixture = parse_fixture(raw)
    for name, expected in fixture['new_sources'].items():
        assert hashlib.sha256(recovery_checkpoint(name, (ROOT/name).read_bytes())).hexdigest() == expected, 'Records source changed: '+name
    change = fixture['files'].get(path)
    if change is None:
        return actual
    if hashlib.sha256(actual).hexdigest() in (change['parent_sha256'], change.get('accepted_ancestor_sha256')):
        return actual
    assert hashlib.sha256(actual).hexdigest() == change['current_sha256'], 'Records descendant changed: '+path
    parent = change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest() == change['parent_sha256'], 'Records parent changed: '+path
    return parent
