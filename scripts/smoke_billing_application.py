"""Real authentication, route registration and lifetime billing acceptance."""
import os
import json
os.environ.setdefault('YOLO_CONFIG_DIR','/private/tmp/billing-yolo-settings')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.runtime.application import create_application


class OwnedFinancialApplication(unittest.TestCase):
    def test_real_sessions_roles_private_configuration_and_no_get_work(self):
        with tempfile.TemporaryDirectory(prefix='billing-application-') as directory:
            home=Path(directory);(home/'local_inspection_service/static').mkdir(parents=True)
            env={'LOCAL_INSPECTION_ROOT':str(home),'VANTALINE_DATA_STORE':'json','VANTALINE_FILE_STORE':'local','VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0','INSPECTION_ENABLE_LAN_CORS':'0','INSPECTION_CORS_ORIGINS':''}
            env['VANTALINE_BILLING_ACCOUNTS_JSON']=json.dumps([{'provider':'ali','payer_id':'synthetic-private-payer','key_ref':'SYNTHETIC_FINANCE_KEY','secret_ref':'SYNTHETIC_FINANCE_SECRET'}])
            owned=create_application(env)
            self.addCleanup(lambda:self.assertTrue(owned.lifetime.close(10)))
            anonymous=TestClient(owned.app,base_url='https://testserver')
            admin=TestClient(owned.app,base_url='https://testserver')
            user=TestClient(owned.app,base_url='https://testserver')
            second=TestClient(owned.app,base_url='https://testserver')
            for client in (anonymous,admin,user,second):self.addCleanup(client.close)
            password='synthetic-financial-application-password'
            self.assertEqual(admin.post('/api/auth/bootstrap',json={'username':'owner','password':password}).status_code,200)
            self.assertEqual(admin.post('/api/auth/users',json={'username':'reader','password':password,'role':'user','permissions':['system_settings','inspection']}).status_code,200)
            self.assertEqual(admin.post('/api/auth/users',json={'username':'another-owner','password':password,'role':'admin'}).status_code,200)
            self.assertEqual(user.post('/api/auth/login',json={'username':'reader','password':password}).status_code,200)
            self.assertEqual(second.post('/api/auth/login',json={'username':'another-owner','password':password}).status_code,200)
            service=owned.analytics._billing
            service.reader=Mock()
            for client in (admin,second):
                response=client.get('/api/admin/billing/overview')
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(len(response.json()['accounts']),6)
                self.assertTrue(all(a['balance'] is None for a in response.json()['accounts']))
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                self.assertNotIn('key_ref',response.text)
                self.assertNotIn('synthetic-private-payer',response.text)
                status=client.get('/api/status').text
                for private in ('VANTALINE_BILLING','SYNTHETIC_FINANCE_KEY','SYNTHETIC_FINANCE_SECRET','synthetic-private-payer'):
                    self.assertNotIn(private,status)
            requests=[('get','/api/admin/billing/overview'),('get','/api/admin/billing/accounts/pending_codex'),('get','/api/admin/billing/accounts/pending_codex/entries'),('get','/api/admin/billing/jobs/unknown'),('post','/api/admin/billing/refresh')]
            for client,expected in ((anonymous,401),(user,403)):
                for method,path in requests:
                    response=client.post(path,json={}) if method=='post' else client.get(path+'?role=admin&user_id=owner')
                    self.assertEqual(response.status_code,expected,response.text)
            # Removing a real session denies the same previously privileged client.
            self.assertEqual(second.post('/api/auth/logout').status_code,200)
            self.assertEqual(second.get('/api/admin/billing/overview').status_code,401)
            self.assertEqual(service.reader.mock_calls,[])
            self.assertIsNone(service.thread)
            self.assertEqual(owned.app.router.on_startup.count(service.start),0)
            self.assertEqual([step.name for step in owned.http._web_shutdown.steps][0],'billing-sync')


if __name__=='__main__':unittest.main()
