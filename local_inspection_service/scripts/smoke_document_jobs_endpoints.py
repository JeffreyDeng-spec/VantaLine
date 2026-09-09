"""Real routes/auth with isolated JSON storage and a deterministic fake VLM."""
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD, picture, assert_status


def main():
    admin = TestClient(server.app, base_url='https://testserver')
    user = admin.post('/api/auth/bootstrap', json={'username': 'admin', 'password': PASSWORD}).json()['user']
    owner = user['id']
    os.environ['VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS'] = owner
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED = True
    server.ai_detection_settings = lambda: dict(provider='qwen', model='fixture-vl', api_key='never-log-this', base_url='https://fixture.invalid')
    blobs = [picture('LABEL'), picture('LABEL'), picture('PRODUCT')]
    server.extract_doc_images = lambda data: ([dict(ordinal=i+1, sha256=server.sha256_bytes(b), mime_type='image/png') for i,b in enumerate(blobs)], blobs)
    calls = []
    def transport(request, settings, timeout):
        # Attempt is committed before the transport sees any request.
        assert any(a.get('classification_attempt', {}).get('state') == 'attempting' for a in server._text_v2_load('assets'))
        calls.append(1)
        category = 'label_design' if len(calls) % 2 else 'physical_photo'
        return io.BytesIO(json.dumps(dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps(dict(category=category, reason='visible fixture evidence'))))])).encode())
    server.ai_urlopen = transport
    def upload(version):
        response = admin.post('/api/text-inspection/standards/import', data=dict(name='Test', material_code='TEST', version_label=version), files={'file': ('test.doc', b'fixture-doc', 'application/msword')})
        assert_status(response, 200, 'DOC import')
        return response.json()['id']
    def wait(identity):
        for _ in range(200):
            value = admin.get('/api/text-inspection/standards/'+identity).json()
            if value.get('classification', {}).get('state') != 'processing':
                return value
            time.sleep(.05)
        raise AssertionError('worker did not finish')
    identity = upload('1')
    result = wait(identity)
    assert result['classification']['state'] == 'completed'
    assert [a['status'] for a in result['assets']] == ['candidate', 'candidate', 'excluded']
    assert len(calls) == 2, 'duplicate images require one model call'
    assert 'never-log-this' not in json.dumps(result)
    assert upload('1') == identity
    assert_status(admin.post(f'/api/text-inspection/standards/{identity}/classify'), 200, 'duplicate classify')
    assert len(calls) == 2
    assert_status(admin.post(f'/api/text-inspection/standards/{identity}/confirm'), 200, 'confirm classified')
    revisions = server._text_v2_load('revisions')
    admin.post('/api/auth/users', json=dict(username='other', password=PASSWORD, role='user', permissions=['inspection']))
    other = TestClient(server.app, base_url='https://testserver')
    other.post('/api/auth/login', json=dict(username='other', password=PASSWORD))
    assert_status(other.delete(f'/api/text-inspection/standards/{identity}'), 404, 'cross owner delete')
    assert_status(other.post(f'/api/text-inspection/standards/{identity}/classify'), 404, 'cross owner classify')
    assert_status(admin.delete(f'/api/text-inspection/standards/{identity}'), 200, 'delete')
    assert_status(admin.delete(f'/api/text-inspection/standards/{identity}'), 200, 'idempotent delete')
    assert admin.get('/api/text-inspection/standards').json()['items'] == []
    assert server._text_v2_load('revisions') == revisions
    assert_status(admin.get(result['assets'][0]['content_url']), 200, 'historical media retained')
    assert_status(admin.post(f'/api/text-inspection/standards/{identity}/confirm'), 409, 'deleted cannot enable')
    assert_status(admin.patch(f"/api/text-inspection/standards/{identity}/assets/{result['assets'][0]['id']}", json={'action':'confirm'}), 409, 'deleted cannot mutate')

    entered, release = threading.Event(), threading.Event()
    def delayed(*args, **kwargs):
        entered.set(); assert release.wait(10)
        return transport(*args, **kwargs)
    server.ai_urlopen = delayed
    identity = upload('2')
    assert entered.wait(5)
    detail = admin.get('/api/text-inspection/standards/'+identity).json()
    assert_status(admin.post(f'/api/text-inspection/standards/{identity}/confirm'), 409, 'in-flight confirmation rejected')
    first = detail['assets'][0]['id']
    admin.patch(f'/api/text-inspection/standards/{identity}/assets/{first}', json={'action':'remove'})
    release.set()
    detail = wait(identity)
    assert detail['assets'][0]['status'] == 'excluded' and detail['assets'][0]['classification_source'] == 'human'
    # Stale work is exposed as interrupted, never re-submitted by polling.
    standard = server._text_v2_owned('standards', identity, owner)
    standard['classification'].update(state='processing', heartbeat=0)
    server._text_v2_save('standards', standard)
    before = len(calls)
    assert admin.get('/api/text-inspection/standards/'+identity).json()['classification']['state'] == 'interrupted'
    admin.post(f'/api/text-inspection/standards/{identity}/classify')
    assert len(calls) == before
    print('document jobs endpoints/auth/dedup/history/stale/human-race: PASS')


if __name__ == '__main__': main()
