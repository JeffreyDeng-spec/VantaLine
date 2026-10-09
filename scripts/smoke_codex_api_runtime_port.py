"""Codex HTTP media ownership with real artifact stores and synthetic repositories."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.codex_compare import api
from local_inspection_service.codex_compare.dependencies import ComparisonAccess, StandardLibrary, ComparisonMedia, DocumentImports
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.codex_compare.contracts import digest
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable

class CodexRuntimeTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.data=b'synthetic private evidence';self.sha=digest(self.data)
        self.media_root=self.root/'codex_comparisons'/'media'
        self.path=api.PREFIX+'/tasks/shared/media/'+self.sha
        p=patch.object(api,'CodexComparisonsRepository',side_effect=lambda repository:repository)
        p.start();self.addCleanup(p.stop)
    def fixture(self,index,provider=None):
        state=SimpleNamespace(owner='alice',permission=True,available=True)
        evidence={key:self.sha for key in ('original','image','preview')}
        task={'inputs':{'reference':evidence,'actual':evidence},'artifacts':{}}
        def permission(_):
            if not state.permission:raise HTTPException(403,'forbidden')
        repository=Mock();repository.get.side_effect=lambda owner,key:task if owner=='alice' and key=='shared' else None
        state.provider=provider if provider is not None else Mock(return_value=self.runtimes[index])
        app=FastAPI()
        api.register(app,ComparisonAccess(permission,lambda:(state.owner,'user')),
            lambda:repository if state.available else None,StandardLibrary(Mock(),Mock(),Mock()),
            ComparisonMedia(lambda:self.root,Mock(),Mock(),Mock()),DocumentImports(Mock(),Mock()),
            runtime_provider=state.provider,environment={})
        state.client=TestClient(app,raise_server_exceptions=False);self.addCleanup(state.client.close)
        state.app=app;return state
    def put(self,index):
        return MediaStore(self.media_root,runtime_provider=lambda:self.runtimes[index]).put('alice',self.data)
    def test_same_task_and_media_paths_do_not_cross_stores(self):
        a,b=self.fixture(0),self.fixture(1);a.provider.assert_not_called();b.provider.assert_not_called()
        self.put(0)
        self.assertEqual(a.client.get(self.path).content,self.data)
        self.assertEqual(b.client.get(self.path).status_code,422)
        self.put(1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda state:state.client.get(self.path),(a,b)))
        for response in responses:
            self.assertEqual(response.status_code,200);self.assertEqual(response.content,self.data)
            self.assertEqual(response.headers['cache-control'],'private, no-store')
        with patch.object(self.runtimes[0].store,'read_bytes',side_effect=ArtifactUnavailable('fixture')):
            self.assertEqual(a.client.get(self.path).status_code,500)
            self.assertEqual(b.client.get(self.path).content,self.data)
        self.assertFalse(MediaStore(self.media_root,runtime_provider=lambda:None).path('alice',self.sha).exists())
    def test_permission_repository_owner_and_evidence_checks_precede_provider(self):
        state=self.fixture(0);state.permission=False
        self.assertEqual(state.client.get(self.path).status_code,403)
        state.permission=True;state.available=False
        self.assertEqual(state.client.get(self.path).status_code,503)
        state.available=True;state.owner='bob'
        self.assertEqual(state.client.get(self.path).status_code,404)
        state.owner='alice'
        self.assertEqual(state.client.get(self.path.replace(self.sha,'f'*64)).status_code,404)
        state.provider.assert_not_called()
    def test_selected_provider_failure_does_not_read_local_evidence(self):
        MediaStore(self.media_root,runtime_provider=lambda:None).put('alice',self.data)
        state=self.fixture(0,Mock(side_effect=ArtifactUnavailable('fixture unavailable')))
        self.assertEqual(state.client.get(self.path).status_code,500)
        state.provider.assert_called_once_with()
    def test_falsey_provider_with_local_result_is_preserved(self):
        class Falsey:
            def __bool__(self):raise AssertionError('truthiness')
            def __call__(self):return None
        MediaStore(self.media_root,runtime_provider=lambda:None).put('alice',self.data)
        state=self.fixture(0,Falsey())
        self.assertEqual(state.client.get(self.path).content,self.data)
    def test_missing_dependencies_fail_before_routes_and_root_supplies_owner(self):
        app=FastAPI();before=len(app.routes)
        args=(app,Mock(),Mock(),Mock(),Mock(),Mock())
        with self.assertRaises(TypeError):api.register(*args)
        with self.assertRaises(TypeError):api.register(*args,runtime_provider=None)
        with self.assertRaisesRegex(TypeError,'runtime_provider is required'):api.register(*args,runtime_provider=None,environment={})
        with self.assertRaisesRegex(TypeError,'environment is required'):api.register(*args,runtime_provider=lambda:None,environment=None)
        self.assertEqual(len(app.routes),before)
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='register_codex_compare')
        value=next(k.value for k in call.keywords if k.arg=='runtime_provider')
        self.assertEqual(ast.unparse(value),'_business_files.runtime_provider')

if __name__=='__main__':unittest.main()
