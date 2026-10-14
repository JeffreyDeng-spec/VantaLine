"""Exact Volcengine envelope descendant before unchanged financial checkpoints."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIXTURE_SHA256='2f3fb65318f646fc1820239fdf846a4ffda8583590b6232d831319622c340e61'


def fixture():
    raw=(ROOT/'tests/backend_contract/billing_volc_summary_extension.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==FIXTURE_SHA256,'Unreviewed Volcengine summary extension'
    value=json.loads(raw)
    assert hashlib.sha256((ROOT/value['provider_path']).read_bytes()).hexdigest()==value['current_sha256'],'Actual Volcengine provider changed'
    assert hashlib.sha256((ROOT/value['configuration_guard_path']).read_bytes()).hexdigest()==value['configuration_guard_sha256'],'Actual configuration guard changed'
    assert hashlib.sha256(value['parent_source'].encode()).hexdigest()==value['parent_sha256'],'Volcengine summary parent changed'
    for name,digest in value['locked_prior_fixtures'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'Prior financial fixture changed: '+name
    return value


def checkpoint_bytes(path,actual):
    value=fixture()
    if path!=value['provider_path']:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest in [value['parent_sha256'],*value['accepted_ancestors']]:return actual
    assert digest==value['current_sha256'],'Unknown Volcengine summary source: '+path
    return value['parent_source'].encode()
