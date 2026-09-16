"""Real HTTP contracts for accessory route selection, with no paid provider calls."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from fastapi import HTTPException


class RoutingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='accessory-routing-')
        root = Path(cls.temporary.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server
        cls.admin = TestClient(server.app,base_url='https://testserver',raise_server_exceptions=False)
        assert cls.admin.post('/api/auth/bootstrap',json={'username':'fixture-admin','password':'fixture-password-only'}).status_code==200
        cls.users,cls.clients = {},{}
        for name,permissions in [('alice',['accessory_library']),('bob',['accessory_library']),('blocked',['inspection'])]:
            response=cls.admin.post('/api/auth/users',json={'username':name,'password':'fixture-password-only','role':'user','permissions':permissions})
            assert response.status_code==200,response.text
            cls.users[name]=response.json()['user']
            client=TestClient(server.app,base_url='https://testserver',raise_server_exceptions=False)
            assert client.post('/api/auth/login',json={'username':name,'password':'fixture-password-only'}).status_code==200
            cls.clients[name]=client

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients.values():client.close()
        cls.admin.close()
        cls.temporary.cleanup()

    def setUp(self):
        self.events=[]
        self.state={'accessories':[{'id':'part','class_id':0,'name':'Part','material_type':'object',
                                   'owner_user_id':self.users['alice']['id'],
                                   'shared_with_user_ids':[self.users['bob']['id']]}]}
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        def load():
            self.events.append('load')
            self.loaded=copy.deepcopy(self.state)
            return self.loaded
        def profile(item):
            self.events.append('profile')
            self.assertIs(item,self.loaded['accessories'][0])
            item['ai_profile']={'fixture':True}
            return False
        def save(item,config):
            self.events.append('save')
            self.assertIs(config,self.loaded)
            self.assertIs(item,config['accessories'][0])
            self.state=copy.deepcopy(config)
            return {'id':'must-not-replace-original-item'}
        def upsert(identifier,config):
            self.events.append('upsert')
            self.assertEqual(identifier,'part')
            self.assertIs(config,self.loaded)
            config['accessories'][0]['task_marker']='after-save'
            return {'id':'synthetic-ai-task'}
        def serialize(item):
            self.events.append('serialize')
            return {'id':item['id'],'route':item['detection_route'],'task_marker':item.get('task_marker')}
        for name,fn in [('load_config',load),('ensure_accessory_ai_profile',profile),('save_accessory_item',save),
                        ('upsert_dashboard_ai_task',upsert),('serialize_accessory',serialize)]:
            self.stack.enter_context(patch.object(self.server,name,fn))

    def post(self,route='ai',apply=True,client='alice',identifier='part'):
        return self.clients[client].post(f'/api/accessories/{identifier}/route',json={'route':route,'apply':apply})

    def test_auth_validation_and_retired_route_before_storage(self):
        anonymous=TestClient(self.server.app,base_url='https://testserver')
        try:
            response=anonymous.post('/api/accessories/part/route',json={'route':'invalid'})
            self.assertEqual(response.status_code,401)
        finally:
            anonymous.close()
        self.assertEqual(self.post('invalid',client='blocked').status_code,403)
        invalid=self.post(' INVALID ')
        self.assertEqual((invalid.status_code,invalid.json()),(400,{'detail':'未知的检测路线:INVALID'}))
        retired=self.post(' locate ')
        self.assertEqual((retired.status_code,retired.json()),(410,{'detail':'LocateAnything accessory route has been removed from the Phase 1 core product.'}))
        self.assertEqual(self.post('invalid',client='bob').status_code,400)
        self.assertEqual(self.post('locate',identifier='missing').status_code,410)
        self.assertEqual(self.events,[])
        missing=self.post(identifier='missing')
        self.assertEqual((missing.status_code,missing.json()),(404,{'detail':'配件不存在'}))
        self.assertEqual(self.events,['load'])

    def test_owner_and_shared_write_guard(self):
        response=self.post(client='bob')
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.events,['load'])
        self.assertNotIn('detection_route',self.state['accessories'][0])
        self.assertNotIn('detection_route',self.loaded['accessories'][0])
        response=self.admin.post('/api/accessories/part/route',json={'route':'yolo','apply':False})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.events,['load','load','save','serialize'])

    def test_non_applied_ai_and_non_ai_routes_save_without_model(self):
        for route,apply in [(' ai ',False),('yolo',True),('archive_only',True)]:
            self.events.clear()
            response=self.post(route,apply)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json(),{'accessory_id':'part','route':route.strip(),
                'accessory':{'id':'part','route':route.strip(),'task_marker':None}})
            self.assertEqual(self.events,['load','save','serialize'])
            self.assertEqual(self.state['accessories'][0]['detection_route'],route.strip())

    def test_applied_ai_order_and_same_config_mutation(self):
        self.state['accessories'].append({'id':'part','class_id':1,'name':'Duplicate','owner_user_id':self.users['bob']['id']})
        response=self.clients['alice'].post('/api/accessories/part/route',json={'route':'ai'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.events,['load','profile','save','upsert','serialize'])
        self.assertEqual(response.json(),{'accessory_id':'part','route':'ai','profile_status':'ready',
            'ai_task':{'id':'synthetic-ai-task'},'accessory':{'id':'part','route':'ai','task_marker':'after-save'}})
        self.assertEqual(self.state['accessories'][0]['ai_profile'],{'fixture':True})
        self.assertNotIn('task_marker',self.state['accessories'][0])
        self.assertNotIn('detection_route',self.state['accessories'][1])

    def test_profile_failure_is_bounded_but_save_and_task_failures_propagate(self):
        error=HTTPException(503,'x'*250)
        def failing_profile(item):
            self.events.append('profile')
            item['partial_profile']='preserved'
            raise error
        with patch.object(self.server,'ensure_accessory_ai_profile',side_effect=failing_profile):
            response=self.post()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['profile_status'],'failed')
        self.assertEqual(response.json()['profile_error'],str(error)[:200])
        self.assertEqual(self.state['accessories'][0]['partial_profile'],'preserved')
        self.assertEqual(self.events,['load','profile','save','upsert','serialize'])
        self.events.clear()
        with patch.object(self.server,'save_accessory_item',side_effect=RuntimeError('synthetic save failure')) as save_failure:
            response=self.post()
        save_failure.assert_called_once()
        self.assertEqual(response.status_code,500)
        self.assertEqual(self.events,['load','profile'])
        self.events.clear()
        with patch.object(self.server,'upsert_dashboard_ai_task',side_effect=RuntimeError('synthetic task failure')) as task_failure:
            response=self.post()
        task_failure.assert_called_once()
        self.assertEqual(response.status_code,500)
        self.assertEqual(self.events,['load','profile','save'])
        self.assertEqual(self.state['accessories'][0]['detection_route'],'ai')
        self.assertEqual(self.state['accessories'][0]['ai_profile'],{'fixture':True})
        self.events.clear()
        with patch.object(self.server,'serialize_accessory',side_effect=RuntimeError('synthetic projection failure')) as projection_failure:
            response=self.post()
        projection_failure.assert_called_once()
        self.assertEqual(response.status_code,500)
        self.assertEqual(self.events,['load','profile','save','upsert'])


if __name__=='__main__':unittest.main()
