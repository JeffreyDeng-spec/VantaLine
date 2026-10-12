"""Exact record metadata compatibility correction; old fixtures stay fixed."""
from dataset_photos_source_contract import checkpoint_bytes as photos_checkpoint
from plc_result_values_source_contract import checkpoint_bytes as result_values_checkpoint
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def checkpoint_bytes(path,actual):
    actual=photos_checkpoint(path,actual)
    actual=result_values_checkpoint(path,actual)
    raw=(ROOT/'tests/backend_contract/user_records_recovery_delta.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=="feffc6abb53a7e254c04cb249a4acd6139943dc1640e982f8a7f98edd75f25ce", 'Unreviewed records recovery fixture'
    change=json.loads(raw)['files'].get(path)
    if change is None:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest in [change['parent_sha256'], *change['accepted_ancestors']]:return actual
    assert digest==change['current_sha256'], 'Records recovery descendant changed: '+path
    for region in reversed(change['regions']):
        current,parent=region['current'].encode(),region['parent'].encode()
        assert actual.count(current)==1, 'Records recovery inverse ambiguous: '+path
        actual=actual.replace(current,parent,1)
    assert hashlib.sha256(actual).hexdigest()==change['parent_sha256'], 'Records recovery parent changed: '+path
    return actual
