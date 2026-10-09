"""Explicit label media owners through HTTP, PDF consumer and standalone worker."""
import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.label_inspection import api,worker,worker_api,pdf_import,runtime
from local_inspection_service.label_inspection.dependencies import LabelAccess,LabelImports,RepositoryLifecycle
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.codex_compare.contracts import digest
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable

class LabelMediaRuntimeTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.media_root=self.root/'label_inspection'/'media'
        self.providers=[Mock(return_value=value) for value in self.runtimes]
    def media(self,index):return MediaStore(self.media_root,runtime_provider=self.providers[index])
    def test_http_media_isolation_and_authorization_before_runtime(self):
        data=b'synthetic evidence';sha=self.media(0).put('alice',data);clients=[];states=[]
        with patch.object(api,'LabelRepository',side_effect=lambda raw:raw),patch.object(worker_api,'read_identity',return_value=None):
            for index in range(2):
                app=FastAPI();state=SimpleNamespace(owner='alice',permission=True)
                task={'id':'task','assets':[{'media':{'image':sha}}]}
                repo=SimpleNamespace(get=lambda owner,*args:task if owner=='alice' else None,list=lambda *args:[])
                def permission(_,state=state):
                    if not state.permission:raise HTTPException(403,'forbidden')
                api.register(app,LabelAccess(permission,Mock(),lambda state=state:(state.owner,'user')),
                    RepositoryLifecycle(lambda repo=repo:repo,Mock()),LabelImports(lambda:self.root,Mock(),Mock(),Mock(),Mock()),Mock(),Mock(),runtime_provider=self.providers[index])
                client=TestClient(app,raise_server_exceptions=False);self.addCleanup(client.close);clients.append(client);states.append(state)
            path=api.PREFIX+'/tasks/task/media/'+sha
            self.assertEqual(clients[0].get(path).content,data)
            self.assertEqual(clients[1].get(path).status_code,422)
            self.media(1).put('alice',data)
            self.assertEqual(clients[1].get(path).content,data)
            for client,state,provider in zip(clients,states,self.providers):
                provider.reset_mock();state.permission=False
                self.assertEqual(client.get(path).status_code,403)
                state.permission=True;state.owner='bob'
                self.assertEqual(client.get(path).status_code,404);provider.assert_not_called()
    def test_claimed_worker_uses_selected_store_and_model_failure_does_not_replay(self):
        models=SimpleNamespace(resolve=Mock(return_value={'api_key':'synthetic'}),record_call=Mock())
        run={'id':'run','owner_user_id':'alice','profile_snapshot':{'id':'profile','version':1}}
        repo=SimpleNamespace(claim=Mock(return_value=run));controllers=[]
        with patch.dict(os.environ,{'VANTALINE_LABEL_INSPECTION_ENABLED':'true'}),patch.object(worker,'LabelRepository',return_value=repo),patch.object(worker,'LabelRunProjection'):
            for index in range(2):
                controller=worker.LabelWorker(RepositoryLifecycle(lambda:object(),Mock()),lambda:self.root,lambda:models,runtime_provider=self.providers[index]);controllers.append(controller)
                data=('worker-'+str(index)).encode()
                with patch.object(worker,'process',side_effect=lambda repo,media,*args,**kw:media.put('alice',data)) as process:
                    self.assertIs(controller._iteration(),run);process.assert_called_once()
                self.assertEqual(self.media(index).read('alice',digest(data)),data)
                with self.assertRaises(FileNotFoundError):self.media(1-index).read('alice',digest(data))
            for provider in self.providers:provider.reset_mock()
            models.resolve.side_effect=ValueError('synthetic failure')
            with patch.object(worker,'process') as process,self.assertLogs(worker.__name__,level='ERROR'):
                self.assertIs(controllers[0]._iteration(),run)
            process.assert_not_called();self.providers[0].assert_not_called();self.assertEqual(repo.claim.call_count,3)
    def test_pdf_native_threads_use_selected_store_and_clear_on_same_thread(self):
        import threading
        for index in range(2):
            app=FastAPI();events=[];data=('pdf-'+str(index)).encode();task={'id':'synthetic'}
            def claim(token):events.append(('claim',threading.get_ident()));return task
            def clear():events.append(('clear',threading.get_ident()))
            repo=SimpleNamespace(claim_pdf=claim)
            owner=pdf_import.register(app,RepositoryLifecycle(lambda:repo,clear),lambda:self.root,runtime_provider=self.providers[index])
            done=threading.Event()
            def process(repo,media,*args):media.put('alice',data);owner.request_stop();done.set()
            with patch.object(pdf_import,'LabelRepository',side_effect=lambda raw:raw),patch.object(pdf_import,'process',side_effect=process):
                app.router.on_startup[0]()
                try:self.assertTrue(done.wait(3))
                finally:self.assertTrue(owner.close(3))
            self.assertEqual(events[0][0],'claim');self.assertEqual(events[1],('clear',events[0][1]));self.assertNotEqual(events[0][1],threading.get_ident())
            self.assertEqual(self.media(index).read('alice',digest(data)),data)
            with self.assertRaises(FileNotFoundError):self.media(1-index).read('alice',digest(data))
    def test_both_web_topologies_reject_different_runtime_provider(self):
        for identity in (None,SimpleNamespace(mode='external')):
            app=FastAPI();repositories=RepositoryLifecycle(Mock(),Mock());directory=lambda:self.root;models=Mock()
            with patch.object(worker_api,'read_identity',return_value=identity),patch.object(worker_api,'create_control_factory'),patch.object(worker_api,'LabelRuntimeControl'):
                handle=worker_api.register(app,repositories,directory,models,runtime_provider=self.providers[0]);hooks=(len(app.router.on_startup),len(app.router.on_shutdown))
                self.assertIs(worker_api.register(app,repositories,directory,models,runtime_provider=self.providers[0]),handle)
                with self.assertRaises(RuntimeError):worker_api.register(app,repositories,directory,models,runtime_provider=self.providers[1])
            self.assertEqual(hooks,(len(app.router.on_startup),len(app.router.on_shutdown)))
            self.assertIs(handle.runtime_provider,self.providers[0]);self.assertEqual(isinstance(handle,worker.LabelWorker),identity is None)
            self.providers[0].assert_not_called()
    def test_standalone_passes_provider_without_web_or_eager_storage(self):
        models=Mock();identity=SimpleNamespace(mode='external',config_revision='r');configuration=SimpleNamespace(revision='r')
        with patch.object(runtime,'LabelRuntimeControl'):
            process=runtime.LabelProcess(identity,configuration,self.root,Mock(),Mock(),models=models,runtime_provider=self.providers[1])
        self.assertIs(process.worker.runtime_provider,self.providers[1]);self.providers[1].assert_not_called()
        self.assertNotIn('local_inspection_service.server',sys.modules)
    def test_required_dependencies_reject_none_before_side_effects(self):
        calls=[(api.register,(FastAPI(),Mock(),Mock(),Mock(),Mock(),Mock())),(worker_api.register,(FastAPI(),Mock(),Mock(),Mock())),(pdf_import.register,(FastAPI(),Mock(),Mock())),(worker.LabelWorker,(Mock(),Mock(),Mock())),(runtime.LabelProcess,(Mock(),Mock(),Mock(),Mock(),Mock()))]
        for fn,args in calls:
            with self.assertRaises(TypeError):fn(*args)
            with self.assertRaises(TypeError):fn(*args,runtime_provider=None)
        class Falsey:
            def __bool__(self):raise AssertionError('truthiness')
            def __call__(self):return None
        provider=Falsey();controller=worker.LabelWorker(Mock(),Mock(),Mock(),runtime_provider=provider)
        self.assertIs(controller.runtime_provider,provider)
        root=Path(__file__).resolve().parents[1];tree=ast.parse((root/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='register_label_inspection')
        self.assertEqual(ast.unparse(next(k.value for k in call.keywords if k.arg=='runtime_provider')),'_business_files.runtime_provider')

if __name__=='__main__':unittest.main()
