"""Actual Codex API registrations select their own live environment mapping."""
from concurrent.futures import ThreadPoolExecutor
import ast
from pathlib import Path
import sys
from unittest.mock import Mock,patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.codex_compare import api
from local_inspection_service.codex_compare.dependencies import ComparisonAccess,StandardLibrary,ComparisonMedia,DocumentImports

def build(environment,owner='a'):
    app=FastAPI();events=[];permission=[True]
    def permitted(key):
        events.append(key)
        if not permission[0]:raise HTTPException(403,'denied')
    def poison(*args,**kwargs):raise AssertionError('capabilities must not select storage/media or a model')
    api.register(app,ComparisonAccess(permitted,lambda:(owner,'synthetic')),
        poison,StandardLibrary(poison,poison,poison),ComparisonMedia(poison,poison,poison,poison),
        DocumentImports(poison,poison),runtime_provider=poison,environment=environment)
    return app,TestClient(app),events,permission

class EnvironmentContracts(unittest.TestCase):
    def test_actual_submission_uses_each_apps_live_admission_mapping(self):
        from smoke_codex_dependencies import CodexDependencyContracts
        fixture=CodexDependencyContracts('test_two_apps_concurrent_identity_repositories_and_frozen_source')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        original=api.register
        environments=[{'VANTALINE_CODEX_COMPARE_ACCOUNTS':'alice','VANTALINE_CODEX_COMPARE_MODEL':'a'},
            {'VANTALINE_CODEX_COMPARE_ACCOUNTS':'bob','VANTALINE_CODEX_COMPARE_MODEL':'b'}]
        def registration(environment):
            def register(*args,**kwargs):
                kwargs['environment']=environment
                return original(*args,**kwargs)
            return register
        with patch.object(api,'CodexComparisonsRepository',side_effect=lambda raw:raw):
            states=[]
            for index,environment in enumerate(environments):
                with patch.object(api,'register',registration(environment)):
                    states.append(fixture.fixture('admission-'+str(index)))
            a,b=states
            self.assertEqual(fixture.create(a,'alice').status_code,200)
            self.assertEqual(fixture.create(b,'alice').status_code,403)
            self.assertEqual(len(a.saved),1)
            self.assertEqual(b.saved,[]);self.assertEqual(b.references,[])
            self.assertNotIn('owned',b.events)
            environments[0]['VANTALINE_CODEX_COMPARE_MODEL']=''
            self.assertEqual(fixture.create(a,'alice').status_code,503)
            self.assertEqual(len(a.saved),1)
            for state in states:
                path=api.PREFIX+'/tasks/task-admission-0/retry'
                response=state.client.post(path,json={'request_id':'retry-environment'})
                self.assertEqual(response.status_code,503 if state is a else 403)
            self.assertEqual(b.saved,[]);self.assertEqual(b.references,[])

    def test_root_environment_binding_is_explicit_and_not_copied(self):
        def check(source):
            tree=ast.parse(source)
            calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
                and isinstance(node.func,ast.Name) and node.func.id=='register_codex_compare']
            self.assertEqual(len(calls),1)
            keywords=[node.value for node in calls[0].keywords if node.arg=='environment']
            self.assertEqual(len(keywords),1)
            self.assertEqual(ast.dump(keywords[0]),ast.dump(ast.parse('os.environ',mode='eval').body))
        source=read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8')
        check(source)
        for replacement in ('',', environment={}',', environment=dict(os.environ)'):
            mutant=source.replace(', environment=os.environ\n)',replacement+'\n)')
            self.assertNotEqual(mutant,source)
            with self.assertRaises(AssertionError):check(mutant)

    def test_two_actual_apps_same_account_concurrent_live_isolation(self):
        environments=[{'VANTALINE_CODEX_COMPARE_ACCOUNTS':' a, b ', 'VANTALINE_CODEX_COMPARE_MODEL':'model-a'},
            {'VANTALINE_CODEX_COMPARE_ACCOUNTS':'b','VANTALINE_CODEX_COMPARE_MODEL':'model-b'}]
        a,b=[build(env) for env in environments]
        self.addCleanup(a[1].close);self.addCleanup(b[1].close)
        with patch.dict('os.environ',{'VANTALINE_CODEX_COMPARE_ACCOUNTS':'a','VANTALINE_CODEX_COMPARE_MODEL':'process-poison'}):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda f:f[1].get(api.PREFIX+'/capabilities'),(a,b)))
            self.assertTrue(all(r.status_code==200 for r in results))
            self.assertEqual(results[0].json(),{'enabled':True,'model':'model-a','timeout_seconds':600,'concurrency':1})
            self.assertEqual(results[1].json(),{'enabled':False,'model':'model-b','timeout_seconds':600,'concurrency':1})
            environments[0]['VANTALINE_CODEX_COMPARE_MODEL']='  '
            self.assertEqual(a[1].get(api.PREFIX+'/capabilities').json()['model'],'  ')
            self.assertFalse(a[1].get(api.PREFIX+'/capabilities').json()['enabled'])
            self.assertEqual(b[1].get(api.PREFIX+'/capabilities').json()['model'],'model-b')
        self.assertEqual(a[0].openapi(),b[0].openapi())
        self.assertIsNot(next(r.endpoint for r in a[0].routes if getattr(r,'path',None)==api.PREFIX+'/capabilities'),
            next(r.endpoint for r in b[0].routes if getattr(r,'path',None)==api.PREFIX+'/capabilities'))
    def test_explicit_empty_and_falsey_mapping_never_fall_back_to_process(self):
        class Falsey(dict):
            def __bool__(self):raise AssertionError('mapping truthiness')
        with patch.dict('os.environ',{'VANTALINE_CODEX_COMPARE_ACCOUNTS':'a','VANTALINE_CODEX_COMPARE_MODEL':'process-poison'}):
            for environment in ({},Falsey()):
                app,client,events,permission=build(environment)
                with client:
                    self.assertEqual(client.get(api.PREFIX+'/capabilities').json(),
                        {'enabled':False,'model':'','timeout_seconds':600,'concurrency':1})
                    permission[0]=False
                    self.assertEqual(client.get(api.PREFIX+'/capabilities').status_code,403)
                self.assertEqual(events,['inspection','inspection'])
    def test_missing_dependencies_fail_before_any_registration(self):
        app=FastAPI();before=list(app.routes);arguments=(app,Mock(),Mock(),Mock(),Mock(),Mock())
        with self.assertRaises(TypeError):api.register(*arguments,runtime_provider=lambda:None)
        with self.assertRaisesRegex(TypeError,'environment is required'):
            api.register(*arguments,runtime_provider=lambda:None,environment=None)
        with self.assertRaisesRegex(TypeError,'runtime_provider is required'):
            api.register(*arguments,runtime_provider=None,environment={})
        self.assertEqual(app.routes,before)

if __name__=='__main__':unittest.main()
