"""Fixed additive admin workbench delta; preserve historical source oracles."""
from account_records_source_contract import checkpoint_bytes as records_checkpoint
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/backend_contract/admin_user_data_delta.json'


def fixture():
    raw=FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "eb4a6e930a7b1305a4958cc89907c8194efdf9a75074bb542eb463f031f2de37", 'Unreviewed admin data fixture'
    data=json.loads(raw)
    for path, expected in data['new_sources'].items():
        assert hashlib.sha256(records_checkpoint(path, (ROOT/path).read_bytes())).hexdigest() == expected, 'Admin service changed: '+path
    return data


def checkpoint_bytes(path, actual):
    actual=records_checkpoint(path, actual)
    if path == "local_inspection_service/model_profiles/prompt_sources.json":
        from plc_global_protocol_source_contract import global_parent_bytes
        actual=global_parent_bytes(path, actual)
    change=fixture()['files'].get(path)
    if change is None:
        return actual
    assert hashlib.sha256(actual).hexdigest() == change['current_sha256'], 'Admin descendant changed: '+path
    parent=change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest() == change['parent_sha256'], 'Admin parent changed: '+path
    return parent
