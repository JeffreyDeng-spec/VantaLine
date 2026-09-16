"""Native ASGI contracts for explicit Agent operation API dependencies."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.agent import api
from local_inspection_service.agent.dependencies import AgentAccess, AgentAccounts
from local_inspection_service.storage.agent_operations import OperationConflict, OperationDenied


class AgentContracts(unittest.TestCase):
    def setUp(self):
        from local_inspection_service import agent_api as compatibility
        from local_inspection_service.schemas import agent as schemas
        from local_inspection_service.agent import projection
        self.assertIs(compatibility.register,api.register)
        self.assertIs(compatibility.public_operation,projection.public_operation)
        self.assertIs(compatibility.PolicyUpdate,schemas.PolicyUpdate)
        self.assertIs(compatibility.CancelOperation,schemas.CancelOperation)
        first=schemas.PolicyUpdate(expected_version=0,enabled=True,budget=1)
        second=schemas.PolicyUpdate(expected_version=0,enabled=True,budget=1)
        first.cloud_targets.append('fixture');self.assertEqual(second.cloud_targets,[])
        self.enterContext(patch.object(api,'AgentOperationsRepository',lambda underlying:underlying))
    def fixture(self,name):
        app=FastAPI();who=ContextVar(name,default=None)
        f=SimpleNamespace(events=[],enabled=True,pg=True,policy=None,transition_error=None,policy_error=None)
        f.accounts={uid:{'id':uid,'role':'admin' if uid=='alice' else 'user','permissions':['inspection','agent_config']} for uid in ['alice','bob']}
        @app.middleware('http')
        async def bind(request,call_next):
            token=who.set(request.headers.get('x-owner'))
            try:return await call_next(request)
            finally:who.reset(token)
        def current():
            f.events.append(('user',who.get()))
            if who.get() not in f.accounts:raise HTTPException(401,'Authentication required')
            return f.accounts[who.get()]
        def admin():
            f.events.append(('admin',))
            if current()['role']!='admin':raise HTTPException(403,'Admin role required')
        def store():f.events.append(('store',));return f.accounts
        def find(accounts,key):f.events.append(('find',key));return accounts.get(key)
        class Repo:
            def policy(self,owner):f.events.append(('policy',owner,who.get()));return f.policy
            def set_policy(self,owner,**kwargs):
                f.events.append(('set',owner,kwargs))
                if f.policy_error:raise f.policy_error
                return {'id':owner,**kwargs}
            def get(self,owner,identifier):
                f.events.append(('get',owner,identifier,who.get()))
                if identifier!=owner+'-job':return None
                return {'id':identifier,'kind':'fixture','status':'running','version':4,'payload':{'secret':'hidden'},'credentials':'hidden','actual_cost':2}
            def transition(self,owner,identifier,**kwargs):
                f.events.append(('transition',owner,identifier,kwargs))
                if f.transition_error:raise f.transition_error
                return {'id':identifier,'status':'cancel_requested','version':5,'payload':'hidden'}
        repo=Repo()
        def factory():f.events.append(('repository',who.get()));return repo if f.pg else None
        api.register(app,AgentAccess(current,admin),AgentAccounts(store,find),factory)
        self.assertEqual(f.events,[])
        routes={(route.path,method) for route in app.routes for method in route.methods if route.path.startswith('/api/')}
        self.assertEqual(routes,{('/api/agent/capabilities','GET'),('/api/agent/policy/{account_id}','GET'),('/api/agent/policy/{account_id}','PUT'),('/api/operations/{operation_id}','GET'),('/api/operations/{operation_id}/cancel','POST')})
        f.client=TestClient(app,raise_server_exceptions=False);self.addCleanup(f.client.close)
        return f
    def test_commissioning_gate_dynamic_policy_and_pg_availability(self):
        f=self.fixture('gates')
        with patch.dict('os.environ',{'VANTALINE_WEBMCP_ACCOUNTS':''}):
            self.assertEqual(f.client.get('/api/agent/capabilities').status_code,401)
            f.events.clear();response=f.client.get('/api/agent/capabilities',headers={'x-owner':'alice'})
            self.assertEqual(response.json(),{'enabled':False,'reason':'NOT_COMMISSIONED','account_id':'alice','operation_submission':False})
            self.assertEqual(f.events,[('user','alice')])
        with patch.dict('os.environ',{'VANTALINE_WEBMCP_ACCOUNTS':' alice, bob '}):
            f.pg=False;response=f.client.get('/api/agent/capabilities',headers={'x-owner':'alice'})
            self.assertEqual((response.status_code,response.json()),(503,{'detail':'Durable agent operations require PostgreSQL'}))
            f.pg=True;response=f.client.get('/api/agent/capabilities',headers={'x-owner':'alice'})
            self.assertEqual(response.json()['reason'],'POLICY_DISABLED');self.assertEqual(response.json()['policy_version'],0)
            f.policy={'enabled':True,'version':12};response=f.client.get('/api/agent/capabilities',headers={'x-owner':'alice'})
            self.assertTrue(response.json()['enabled']);self.assertFalse(response.json()['operation_submission']);self.assertEqual(response.json()['policy_version'],12)
    def test_native_concurrent_account_and_app_isolation_and_projection(self):
        first,second=self.fixture('first'),self.fixture('second')
        def get(f,owner):return f.client.get('/api/operations/'+owner+'-job',headers={'x-owner':owner})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(get,first,'alice');b=pool.submit(get,second,'bob')
            self.assertEqual(a.result().json(),{'id':'alice-job','kind':'fixture','status':'running','version':4,'actual_cost':2})
            self.assertEqual(b.result().json()['id'],'bob-job')
        self.assertEqual(first.events,[('repository','alice'),('user','alice'),('get','alice','alice-job','alice')])
        self.assertEqual(second.events,[('repository','bob'),('user','bob'),('get','bob','bob-job','bob')])
        self.assertEqual(first.client.get('/api/operations/alice-job',headers={'x-owner':'bob'}).status_code,404)
    def test_admin_policy_validation_error_mapping_and_order(self):
        f=self.fixture('policy');url='/api/agent/policy/alice';headers={'x-owner':'alice'}
        self.assertEqual(f.client.get(url,headers={'x-owner':'bob'}).status_code,403)
        self.assertFalse(any(e[0]=='repository' for e in f.events))
        f.events.clear();self.assertEqual(f.client.get(url,headers=headers).json(),{'id':'alice','version':0,'enabled':False,'budget':0,'reserved':0,'spent':0,'cloud_targets':[]})
        body={'expected_version':0,'enabled':True,'budget':10}
        f.events.clear();response=f.client.put('/api/agent/policy/missing',headers=headers,json=body)
        self.assertEqual(response.status_code,404);self.assertEqual(f.events,[('admin',),('user','alice'),('store',),('find','missing')])
        for update in [{'enabled':1},{'expected_version':True},{'budget':True},{'budget':-1},{'extra':'value'},{'cloud_targets':['x']*51}]:
            f.events.clear();self.assertEqual(f.client.put(url,headers=headers,json={**body,**update}).status_code,422);self.assertEqual(f.events,[])
        for error,code in [(OperationConflict('stale'),409),(ValueError('invalid'),422)]:
            f.policy_error=error;f.events.clear();response=f.client.put(url,headers=headers,json=body)
            self.assertEqual((response.status_code,response.json()),(code,{'detail':str(error)}));self.assertEqual(sum(e[0]=='set' for e in f.events),1)
        f.policy_error=None;f.events.clear();self.assertEqual(f.client.put(url,headers=headers,json=body).json(),{'id':'alice',**body,'cloud_targets':[]})
        self.assertEqual([e[0] for e in f.events],['admin','user','store','find','repository','set'])
    def test_cancel_owner_version_errors_and_existing_access_order(self):
        f=self.fixture('cancel');url='/api/operations/alice-job/cancel';headers={'x-owner':'alice'}
        self.assertEqual(f.client.post(url,headers={'x-owner':'bob'},json={'expected_version':4}).status_code,404)
        self.assertFalse(any(e[0]=='transition' for e in f.events))
        for error,code in [(OperationConflict('stale'),409),(OperationDenied('denied'),403)]:
            f.transition_error=error;f.events.clear();response=f.client.post(url,headers=headers,json={'expected_version':4})
            self.assertEqual((response.status_code,response.json()),(code,{'detail':str(error)}));self.assertEqual(sum(e[0]=='transition' for e in f.events),1)
        f.transition_error=None;f.events.clear();response=f.client.post(url,headers=headers,json={'expected_version':4})
        self.assertEqual(response.json(),{'id':'alice-job','status':'cancel_requested','version':5})
        self.assertEqual(f.events,[('user','alice'),('repository','alice'),('get','alice','alice-job','alice'),('transition','alice','alice-job',{'expected_version':4,'event':'cancel'})])
        for version in [0,True,'4',4.0]:
            f.events.clear();self.assertEqual(f.client.post(url,headers=headers,json={'expected_version':version}).status_code,422);self.assertEqual(f.events,[])
        f.pg=False;f.events.clear();self.assertEqual(f.client.get('/api/operations/alice-job').status_code,503)
        self.assertEqual(f.events,[('repository',None)])
        f.events.clear();self.assertEqual(f.client.post(url,json={'expected_version':4}).status_code,401);self.assertEqual(f.events,[('user',None)])


if __name__=='__main__':unittest.main(verbosity=2)
