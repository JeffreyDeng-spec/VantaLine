"""Exact read-only dataset photo addition; every older source oracle stays fixed."""
import hashlib,json
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@lru_cache(maxsize=4)
def fixture_data(raw):
    assert hashlib.sha256(raw).hexdigest()=="c2bb6f707134f808022f8a07c660ece87cb2fdaadebf6887488e1b221d9fb9f5", 'Unreviewed dataset photos fixture'
    return json.loads(raw)

@lru_cache(maxsize=4)
def verify_source(raw,expected):
    assert hashlib.sha256(raw).hexdigest()==expected, 'Dataset photo source changed'

def checkpoint_bytes(path,actual):
    raw=(ROOT/'tests/backend_contract/dataset_photos_delta.json').read_bytes()
    fixture=fixture_data(raw)
    for name,expected in fixture['new_sources'].items():
        verify_source((ROOT/name).read_bytes(),expected)
    change=fixture['files'].get(path)
    if change is None:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest in change['accepted_ancestors']:return actual
    assert digest==change['current_sha256'], 'Dataset photo descendant changed: '+path
    parent=change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest()==change['parent_sha256'], 'Dataset photo parent changed: '+path
    return parent
