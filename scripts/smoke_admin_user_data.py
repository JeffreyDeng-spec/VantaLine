"""Administrator actor/owner and mutation boundaries using isolated records."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from contextlib import nullcontext
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.auth.data_workbench import UserDataWorkbench, WorkbenchPorts, DataOperation, register
from local_inspection_service.training.real_photo_contracts import approved

from types import SimpleNamespace

actor = {'id': 'admin', 'username': 'admin', 'role': 'admin'}
users = [{'id': 'a', 'username': 'a', 'role': 'user', 'active': True}, {'id': 'b', 'username': 'b', 'role': 'user', 'active': False}]
pipelines = [{'id': 'p1', 'owner_user_id': 'a', 'auto_advance': True, 'params': {'epochs': 80}}]
training = [{'job_id': 'j1', 'owner_user_id': 'a', 'status': 'running'}]
config = {'accessories': [{'id': 'x', 'owner_user_id': 'a', 'name': 'x', 'ai_profile_reference_files': ['first', 'second']}]}
logs, calls = [], []
class Repo:
    def insert_row_once(self, table, row):
        assert table == 'agent_operation_audit'
        logs.append(row['raw_json'])
        return True
repo = Repo()
def admin():
    if actor['role'] != 'admin': raise HTTPException(403, 'admin required')
    return actor
def save_user(u):
    return True
def pause(identifier):
    calls.append(('pause', identifier))
    pipelines[0]['auto_advance'] = False
def update(identifier, request):
    calls.append(('update', identifier))
    if request.params: pipelines[0]['params'].update(request.params)
    if request.auto_advance is not None: pipelines[0]['auto_advance'] = request.auto_advance
def save_item(item, full):
    assert item['owner_user_id'] == 'a'
    calls.append(('reference', item['id']))
ports = WorkbenchPorts(admin=admin, auth_load=lambda: {'users': users}, auth_save_user=save_user,
    repository=lambda: repo, config=lambda: config, accessory_save=save_item,
    pipelines=lambda: pipelines, pipeline_save=lambda t: None, pipeline_update=update,
    pipeline_pause=pause, training_records=lambda: training, resources=lambda **k: {'datasets': [], 'models': []}, feedback=lambda: SimpleNamespace(repo=lambda: nullcontext(SimpleNamespace(states=lambda owners: [])), ports=SimpleNamespace(tasks=lambda: [])))
service = UserDataWorkbench(ports)
service.events = lambda owner: [e for e in logs if e["owner_user_id"] == owner]
assert service.summary()['counts']['a']['tasks'] == 1
assert not calls and not logs, 'read-only summary cannot mutate or enqueue'
def fail(code, fn):
    try: fn()
    except HTTPException as e: assert e.status_code == code, e
    else: raise AssertionError('expected denial')
actor['role'] = 'user'
fail(403, lambda: service.target('a'))
actor['role'] = 'admin'
fail(404, lambda: service.target('missing'))
fail(404, lambda: service.operate('b', DataOperation(action='params', kind='pipeline', resource_id='p1', epochs=10, reason='cross owner')))
assert not calls
assert logs[-1]['result'] == 'failed' and logs[-1]['owner_user_id'] == 'b'
service.operate('a', DataOperation(action='params', kind='pipeline', resource_id='p1', epochs=100, reason='adjust'))
assert pipelines[0]['params']['epochs'] == 100
assert logs[-1]['actor_user_id'] == 'admin' and logs[-1]['owner_user_id'] == 'a'
assert logs[-2]['result'] == 'requested' and logs[-1]['result'] == 'succeeded'
fail(409, lambda: service.operate('b', DataOperation(action='resume', kind='pipeline', resource_id='p1', reason='inactive')))
fail(409, lambda: service.apply(users[0], DataOperation(action='pause', kind='training', resource_id='j1', reason='no fake cancel')))
ref = service.references('a')[0]
assert 'path' not in ref and ref['enabled']
service.operate('a', DataOperation(action='image_usage', kind='reference', resource_id=ref['resource_id'], enabled=False, reason='disable reference'))
assert not service.references('a')[0]['enabled']
last = service.references('a')[1]
fail(409, lambda: service.operate('a', DataOperation(action='image_usage', kind='reference', resource_id=last['resource_id'], enabled=False, reason='last reference')))
assert 'second' not in config['accessories'][0].get('disabled_ai_profile_reference_files', [])
fail(404, lambda: service.reference('b', ref['resource_id']))
app=FastAPI();register(app,service)
client=TestClient(app)
actor['role']='user'
assert client.get('/api/auth/users/a/data').status_code==403
actor['role']='admin'
assert client.post('/api/auth/users/a/data/operations',json={'action':'params','kind':'pipeline','resource_id':'p1','epochs':501,'reason':'bad'}).status_code==422
assert client.post('/api/auth/users/a/data/operations',json={'action':'params','kind':'pipeline','resource_id':'p1','epochs':1,'reason':'   '}).status_code==422
assert client.get('/api/auth/users-data-summary').status_code==200
assert actor['id']=='admin', 'admin reads/mutations never change ambient identity'
# Archive follows explicit AI linkage, even when the pipeline ID has no pipe_ai prefix.
pipelines[0]['ai_task_id'] = 'ai1'
original_snapshot, original_feedback = service.snapshot, service.feedback
service.snapshot = lambda owner: {'real_photo': [{'task_id': 'ai1', 'enabled': True}]}
service.feedback = lambda target: SimpleNamespace(enable=lambda identifier, request: calls.append(('feedback_pause', identifier, request.enabled)))
service.operate('a', DataOperation(action='archive', kind='pipeline', resource_id='p1', reason='archive linked task'))
assert ('feedback_pause', 'ai1', False) in calls
for mode in ('real_photo', 'legacy'):
    fail(409, lambda: service.apply(users[0], DataOperation(action='resume', kind=mode, resource_id='ai1', reason='must restore archive')))
service.snapshot, service.feedback = original_snapshot, original_feedback
print('PASS admin user data: readonly counts, role/owner isolation, durable intents, parameter bounds, inactive resume, no fake remote cancellation, reference usage, last-reference guard, no identity impersonation')
