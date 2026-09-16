"""Original management HTTP contracts with isolated media and provider substitutes."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


class ManagementContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='accessory-management-')
        cls.root = Path(cls.temporary.name)
        (cls.root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server
        cls.admin = TestClient(server.app, base_url='https://testserver')
        assert cls.admin.post('/api/auth/bootstrap', json={'username':'fixture-admin','password':'fixture-password-only'}).status_code == 200
        cls.clients, cls.users = {}, {}
        for name in ('alice', 'bob'):
            response = cls.admin.post('/api/auth/users', json={'username':name,'password':'fixture-password-only',
                                                              'role':'user','permissions':['accessory_library']})
            assert response.status_code == 200, response.text
            cls.users[name] = response.json()['user']
            client = TestClient(server.app, base_url='https://testserver', raise_server_exceptions=False)
            assert client.post('/api/auth/login', json={'username':name,'password':'fixture-password-only'}).status_code == 200
            cls.clients[name] = client

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients.values(): client.close()
        cls.admin.close()
        cls.temporary.cleanup()

    def setUp(self):
        self.state = {'accessories':[], 'training':{'selected_accessory_ids':[]}}
        self.candidates, self.events = {}, []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.depth = 0
        guard = threading.RLock()
        fixture = self
        class CandidateLock:
            def __enter__(self):
                guard.acquire()
                fixture.depth += 1
                fixture.events.append(('enter', fixture.depth))
                return self
            def __exit__(self, *args):
                fixture.events.append(('exit', fixture.depth))
                fixture.depth -= 1
                guard.release()
        def load_candidate(identifier):
            self.events.append(('load_candidate', self.depth))
            if identifier not in self.candidates: raise HTTPException(404, 'Candidate not found')
            return copy.deepcopy(self.candidates[identifier])
        def save_candidate(path, candidate):
            self.events.append(('save_candidate', self.depth, candidate['status']))
            self.candidates[Path(path).stem] = copy.deepcopy(candidate)
        def save_item(item, config=None):
            self.events.append(('save_item', self.depth))
            self.state = copy.deepcopy(config)
            return dict(item)
        def ensure_profile(item, *, force=False, allow_provider=False):
            self.events.append(('profile', force, allow_provider, self.depth))
            item['ai_profile'] = {'fixture':True}
        def defer(item):
            self.events.append(('defer', self.depth))
            item['normalization_deferred'] = True
        def normalize(item):
            self.events.append(('normalize', self.depth))
            return {'normalized_assets':[{'path':'synthetic-page.png'}]}
        def store_job(candidate, job):
            self.events.append(('store_job', self.depth))
            candidate['codex_image_jobs'] = [copy.deepcopy(job)]
        callbacks = {
            'load_config': lambda: copy.deepcopy(self.state),
            'save_accessory_item': save_item,
            'load_accessory_candidate': load_candidate,
            'save_accessory_candidate': save_candidate,
            '_candidate_store_lock': CandidateLock(),
            'ensure_accessory_ai_profile': ensure_profile,
            'defer_accessory_normalization': defer,
            'normalize_accessory_assets': normalize,
            'ensure_default_ai_profile_reference': lambda item: self.events.append(('reference', self.depth)),
            'ensure_pose_collection_image_jobs': lambda item: False,
            'ensure_candidate_image_job_task_ids': lambda item: False,
            'refresh_codex_image_job': lambda job: dict(job),
            'store_candidate_image_job': store_job,
            'canonical_text_assets': lambda item: item.get('normalized_assets', []),
            'canonical_text_assets_complete': lambda item, assets=None: True,
            'accessory_ai_profile_ready': lambda item: True,
            'accessory_ai_profile_rejected': lambda item: False,
            'start_image_worker': lambda: self.events.append(('worker', self.depth)),
            'add_pipeline_accessory_id': lambda identifier: self.events.append(('pipeline_add', identifier, self.depth)),
            'remove_pipeline_accessory_id': lambda identifier: self.events.append(('pipeline_remove', identifier, self.depth)),
            'add_pipeline_pending_candidate_id': lambda identifier: self.events.append(('pending_add', identifier, self.depth)),
            'remove_pipeline_pending_candidate_id': lambda identifier: self.events.append(('pending_remove', identifier, self.depth)),
            'pipeline_accessories_payload': lambda config, user=None: {'fixture_owner':user['id'] if user else None},
        }
        for name, value in callbacks.items(): self.stack.enter_context(patch.object(self.server, name, value))

    def seed(self, identifier='cand_fixture', kind='object', **extra):
        candidate = {'id':identifier, 'class_id':-1, 'name':'Fixture part', 'material_type':kind,
                     'status':'candidate_review', 'material_alpha_policy':'opaque', 'source_files':[],
                     'owner_user_id':self.users['alice']['id'], 'shared_with_user_ids':[self.users['bob']['id']]}
        candidate.update(extra)
        self.candidates[identifier] = candidate
        return candidate

    def confirm(self, identifier='cand_fixture', client='alice'):
        return self.clients[client].post('/api/accessories/confirm/' + identifier)

    def test_create_validation_owner_class_and_pipeline_order(self):
        client = self.clients['alice']
        for data, detail in (({'name':'bad','material_type':'invalid'}, 'material_type must be text or object'),
                             ({'name':'bad'}, '请选择物品透明或不透明')):
            response = client.post('/api/accessories', data=data)
            self.assertEqual((response.status_code, response.json()), (400, {'detail':detail}))
        self.assertEqual(self.events, [])
        with patch.object(self.server, 'candidate_has_active_image_jobs', return_value=True):
            response = client.post('/api/accessories', data={'name':'Object', 'material_alpha_policy':'opaque', 'pipeline_context':' YES '})
        self.assertEqual(response.status_code, 200, response.text)
        item = self.state['accessories'][0]
        self.assertTrue(item['id'].startswith('acc_'))
        self.assertEqual(item['class_id'], max(self.server.CLASS_NAMES) + 1)
        self.assertEqual(item['owner_user_id'], self.users['alice']['id'])
        self.assertEqual(item['material_alpha_policy'], 'opaque')
        self.assertTrue(item['normalization_deferred'])
        self.assertEqual([event[0] for event in self.events], ['defer','reference','profile','save_item','worker','pipeline_add'])
        self.assertEqual(response.json()['pipeline']['fixture_owner'], self.users['alice']['id'])
        self.events.clear()
        response = client.post('/api/accessories', data={'name':'Object','material_alpha_policy':'opaque'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.events, [])
        response = self.clients['bob'].post('/api/accessories', data={'name':'Object','material_type':'text','class_id':'52'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.state['accessories'][-1]['class_id'], 52)
        self.assertFalse(self.state['accessories'][-1]['normalization_deferred'])
        self.assertEqual(self.events[0], ('normalize', 0))

    def test_preview_persistence_pipeline_and_worker_condition(self):
        def ensure_jobs(item):
            item['codex_image_job'] = {'status':'completed'}
            return True
        with patch.object(self.server, 'ensure_pose_collection_image_jobs', side_effect=ensure_jobs):
            response = self.clients['alice'].post('/api/accessories/preview', data={'name':'Preview','material_alpha_policy':'opaque','pipeline_context':'pipeline'})
        self.assertEqual(response.status_code, 200, response.text)
        candidate = response.json()['candidate']
        self.assertEqual(candidate['pipeline_context'], 'pipeline')
        self.assertEqual(candidate['owner_user_id'], self.users['alice']['id'])
        self.assertEqual(self.candidates[candidate['id']], candidate)
        self.assertEqual([event[0] for event in self.events], ['defer','reference','profile','save_candidate','save_candidate','pending_add','worker'])
        self.assertEqual(self.state['accessories'], [])

    def test_object_upload_accepts_original_extensions_and_keeps_failed_files(self):
        def fail_profile(*args, **kwargs):
            self.assertEqual(kwargs, {'allow_provider':True})
            raise RuntimeError('synthetic profile failure')
        with patch.object(self.server, 'ensure_accessory_ai_profile', side_effect=fail_profile):
            response = self.clients['alice'].post('/api/accessories',
                data={'name':'Partial object', 'material_alpha_policy':'opaque'},
                files={'files':('fixture.txt', b'synthetic media')})
        self.assertEqual(response.status_code, 500)
        paths = list((self.server.UPLOAD_DIR/'accessories').glob('acc_*/*_fixture.txt'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].read_bytes(), b'synthetic media')
        self.assertEqual(self.state['accessories'], [])
        self.assertNotIn('save_item', [event[0] for event in self.events])
        response = self.clients['alice'].post('/api/accessories/preview',
            data={'name':'Text invalid', 'material_type':'text'},
            files={'files':('fixture.txt', b'synthetic media')})
        self.assertEqual(response.status_code, 400)

    def test_failed_job_does_not_block_and_existing_profile_is_not_forced_initially(self):
        self.seed(ai_profile={'fixture':True}, codex_image_jobs=[{'status':'failed'}])
        projection = self.server._accessory_projection
        original_summary = projection.serialize_accessory_summary
        def summary(item):
            self.assertEqual(self.depth, 1)
            return original_summary(item)
        with patch.object(projection, 'serialize_accessory_summary', side_effect=summary):
            response = self.confirm()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([event for event in self.events if event[0]=='profile'],
                         [('profile',False,True,1),('profile',True,True,1)])
        self.assertNotIn('worker', [event[0] for event in self.events])
        self.assertIn('pipeline', response.json())

    def test_confirmation_lock_authorization_active_jobs_and_idempotence(self):
        self.seed()
        denied = self.confirm(client='bob')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.events, [('enter',1),('load_candidate',1),('exit',1)])
        self.assertEqual(self.depth, 0)
        self.events.clear()
        self.candidates['cand_fixture']['codex_image_jobs'] = [{'status':'queued'}]
        response = self.confirm()
        self.assertEqual(response.status_code, 409)
        self.assertEqual([event[0] for event in self.events], ['enter','load_candidate','store_job','worker','exit'])
        self.assertEqual(self.state['accessories'], [])
        self.events.clear()
        self.candidates['cand_fixture']['codex_image_jobs'] = []
        self.candidates['cand_fixture']['pipeline_context'] = 'pipeline'
        response = self.confirm()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'saved')
        saved = self.state['accessories'][0]
        candidate = self.candidates['cand_fixture']
        self.assertEqual(candidate['id'], 'cand_fixture')
        self.assertEqual(candidate['class_id'], -1)
        self.assertEqual(candidate['confirmed_accessory_id'], saved['id'])
        self.assertEqual([event for event in self.events if event[0]=='profile'], [('profile',True,True,1),('profile',True,True,1)])
        names = [event[0] for event in self.events]
        self.assertLess(names.index('save_item'), names.index('save_candidate'))
        self.assertLess(names.index('save_candidate'), names.index('pipeline_add'))
        self.assertEqual(self.events[-1], ('exit',1))
        self.events.clear()
        repeated = self.confirm()
        self.assertEqual(repeated.json()['status'], 'already_saved')
        self.assertEqual(len(self.state['accessories']), 1)
        self.assertEqual([event[0] for event in self.events], ['enter','load_candidate','pipeline_add','pending_remove','exit'])

    def test_confirmation_missing_saved_record_repairs_before_failure(self):
        self.seed(confirmed_accessory_id='missing', confirmed_at=123, confirmed_class_id=4, material_alpha_policy='')
        response = self.confirm()
        self.assertEqual(response.status_code, 400)
        persisted = self.candidates['cand_fixture']
        self.assertFalse(any(key.startswith('confirmed_') for key in persisted))
        self.assertEqual(persisted['status'], 'candidate_review')
        self.assertEqual(self.events, [('enter',1),('load_candidate',1),('save_candidate',1,'candidate_review'),('exit',1)])

    def test_confirmation_plan_and_state_changes_save_before_active_rejection(self):
        self.seed(codex_image_jobs=[{'status':'queued'}])
        def ensure_ids(item):
            self.events.append(('ids',self.depth))
            item['fixture_plan'] = True
            return True
        def ensure_pose(item):
            self.events.append(('pose',self.depth))
            return False
        with patch.object(self.server, 'ensure_candidate_image_job_task_ids', side_effect=ensure_ids), \
             patch.object(self.server, 'ensure_pose_collection_image_jobs', side_effect=ensure_pose), \
             patch.object(self.server, 'refresh_codex_image_job', side_effect=lambda job:{**job,'status':'running','completed_at':22}):
            response = self.confirm()
        self.assertEqual(response.status_code, 409)
        self.assertEqual([event[0] for event in self.events],
                         ['enter','load_candidate','ids','pose','save_candidate','store_job','save_candidate','worker','exit'])
        self.assertTrue(self.candidates['cand_fixture']['fixture_plan'])
        self.assertEqual(self.candidates['cand_fixture']['codex_image_jobs'][0]['completed_at'], 22)
        self.seed(codex_image_jobs=[{'status':'queued'}])
        self.events.clear()
        with patch.object(self.server, 'refresh_codex_image_job', side_effect=lambda job:{**job,'progress':40}):
            response = self.confirm()
        self.assertEqual(response.status_code, 409)
        self.assertEqual([event[0] for event in self.events], ['enter','load_candidate','store_job','worker','exit'])
        self.assertNotIn('progress', self.candidates['cand_fixture']['codex_image_jobs'][0])

    def test_text_confirmation_failure_restores_candidate_identity(self):
        self.seed(kind='text')
        with patch.object(self.server, 'canonical_text_assets_complete', return_value=False):
            response = self.confirm()
        self.assertEqual(response.status_code, 422, response.text)
        candidate = self.candidates['cand_fixture']
        self.assertEqual((candidate['id'],candidate['class_id'],candidate['status']), ('cand_fixture',-1,'candidate_review'))
        self.assertNotIn('confirmed_at', candidate)
        self.assertEqual(self.state['accessories'], [])
        self.assertEqual(self.events[-2:], [('save_candidate',1,'candidate_review'),('exit',1)])
        self.events.clear()
        with patch.object(self.server, 'accessory_ai_profile_rejected', return_value=True):
            response = self.confirm()
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(len([event for event in self.events if event[0]=='profile']), 1)
        self.assertNotIn('normalize', [event[0] for event in self.events])

    def test_confirmation_save_failure_retains_prior_accessory_write(self):
        self.seed()
        def failure(*args):
            self.events.append(('save_candidate_failed',self.depth))
            raise RuntimeError('synthetic candidate write failure')
        with patch.object(self.server, 'save_accessory_candidate', side_effect=failure):
            response = self.confirm()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(self.state['accessories']), 1)
        self.assertEqual(self.candidates['cand_fixture']['status'], 'candidate_review')
        self.assertEqual(self.events[-3:], [('save_item',1),('save_candidate_failed',1),('exit',1)])

    def test_delete_storage_branches_and_shared_denial(self):
        item = self.seed(identifier='acc_remove')
        self.state['accessories'] = [item]
        self.state['training']['selected_accessory_ids'] = ['acc_remove','keep']
        denied = self.clients['bob'].delete('/api/accessories/acc_remove')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.events, [])
        # Existing JSON behavior: root removes the record before its repository lookup.
        response = self.clients['alice'].delete('/api/accessories/acc_remove')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.state['accessories']), 1)
        self.assertEqual(self.events, [])
        def delete(identifier, config=None):
            self.assertIsNone(config)
            self.events.append(('delete_item',identifier))
            return True
        def save_config(config):
            self.events.append(('save_config',))
            self.state = copy.deepcopy(config)
        # Isolate this route's PG branch from the real JSON authentication store.
        isolated = FastAPI()
        isolated.delete('/api/accessories/{accessory_id}')(self.server.delete_accessory)
        with TestClient(isolated) as client, \
             patch.object(self.server, 'current_auth_user', return_value=self.users['alice']), \
             patch.object(self.server, 'runtime_postgres_repository_or_none', return_value=object()), \
             patch.object(self.server, 'delete_accessory_item', side_effect=delete), \
             patch.object(self.server, 'save_app_config', side_effect=save_config):
            response = client.delete('/api/accessories/acc_remove')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.state['accessories'], [])
        self.assertEqual(self.state['training']['selected_accessory_ids'], ['keep'])
        self.assertEqual([event[0] for event in self.events], ['delete_item','save_config','pipeline_remove'])


if __name__ == '__main__':
    unittest.main()
