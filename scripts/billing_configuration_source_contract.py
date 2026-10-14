"""Exact configuration descendant before unchanged financial source replay."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIXTURE_SHA256='a784c30b9eda4036d138f9be7ce3214335bcf9fb2b6c19dee2c274f82b39b5f1'


def fixture():
    from billing_volc_summary_source_contract import checkpoint_bytes as summary_checkpoint
    raw=(ROOT/'tests/backend_contract/billing_configuration_extension.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==FIXTURE_SHA256,'Unreviewed financial configuration extension'
    value=json.loads(raw)
    for name,change in value['files'].items():
        assert hashlib.sha256(summary_checkpoint(name,(ROOT/name).read_bytes())).hexdigest()==change['current_sha256'],'Actual financial configuration owner changed: '+name
    for name,digest in value['new_sources'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'Actual private configuration reader changed: '+name
    return value


def added_backend_sources():
    return set(fixture()['new_sources'])


def checkpoint_bytes(path,actual):
    from billing_volc_summary_source_contract import checkpoint_bytes as summary_checkpoint
    actual=summary_checkpoint(path,actual)
    change=fixture()['files'].get(path)
    if change is None:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest in [change['parent_sha256'],*change['accepted_ancestors']]:return actual
    assert digest==change['current_sha256'],'Unknown financial configuration source: '+path
    parent=change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest()==change['parent_sha256'],'Financial configuration parent changed'
    return parent
