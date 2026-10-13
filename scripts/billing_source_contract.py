"""Exact additive financial extension over unchanged historical source oracles."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIXTURE_SHA256='fd805a87bb4bdbf71f3716eb80ea69d6e949af9edc0daee0a12e43cb9f7d2a9c'


def fixture():
    from billing_configuration_source_contract import added_backend_sources, checkpoint_bytes as configuration_checkpoint
    raw=(ROOT/'tests/backend_contract/billing_extension.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==FIXTURE_SHA256,'Unreviewed financial extension fixture'
    value=json.loads(raw)
    actual={str(p.relative_to(ROOT)) for p in (ROOT/'local_inspection_service/analytics/billing').glob('*.py')}
    actual-=added_backend_sources()
    expected={p for p in value['new_sources'] if p.startswith('local_inspection_service/analytics/billing/')}
    assert actual==expected,'Incomplete financial source inventory'
    for path,change in value['files'].items():
        assert hashlib.sha256(configuration_checkpoint(path,(ROOT/path).read_bytes())).hexdigest()==change['current_sha256'],'Actual financial assembly changed: '+path
    for path,digest in value['new_sources'].items():
        assert hashlib.sha256(configuration_checkpoint(path,(ROOT/path).read_bytes())).hexdigest()==digest,'Financial owner changed: '+path
    return value


def checkpoint_bytes(path,actual):
    from billing_configuration_source_contract import checkpoint_bytes as configuration_checkpoint
    actual=configuration_checkpoint(path,actual)
    change=fixture()['files'].get(path)
    if change is None:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest in [change['parent_sha256'],*change.get('accepted_ancestors',[])]:return actual
    assert digest==change['current_sha256'],'Unknown financial assembly extension: '+path
    parent=change['parent_source'].encode()
    assert hashlib.sha256(parent).hexdigest()==change['parent_sha256'],'Financial parent source changed'
    return parent


def openapi_checkpoint(openapi):
    expected=fixture()['openapi']
    result=copy.deepcopy(openapi)
    actual_paths={p for p in result['paths'] if p.startswith('/api/admin/billing/')}
    assert actual_paths==set(expected['paths']),'Unknown financial API inventory'
    for path,value in expected['paths'].items():
        assert result['paths'].pop(path)==value,'Financial API changed: '+path
    for name,value in expected['schemas'].items():
        assert result['components']['schemas'].pop(name)==value,'Financial request schema changed'
    return result


def startup_checkpoint(hooks):
    fixture()
    names=[hook.__name__ for hook in hooks]
    assert names.count('start_billing_sync')==1,'Financial startup must register once'
    return [name for name in names if name!='start_billing_sync']


def routes_checkpoint(routes):
    expected=fixture()['routes']
    positions=[i for i,row in enumerate(routes) if row['path'].startswith('/api/admin/billing/')]
    assert [routes[i] for i in positions]==expected,'Financial route metadata changed'
    first=positions[0]
    assert positions==list(range(first,first+len(expected))),'Financial route order changed'
    assert routes[first-1]['path']=='/api/admin/api-cost-ledger','Financial route predecessor changed'
    assert routes[first+len(expected)]['path']=='/api/admin/runtime-store/probe','Financial route successor changed'
    return routes[:first]+routes[first+len(expected):]
