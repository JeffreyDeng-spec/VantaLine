"""Actual standard domain graphs, media, HTTP and native classification ownership."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
import ast
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service.text_inspection.standard_composition import (
    TextStandardWorkflows, StandardMediaStorage, StandardPolicy, StandardThreadScope,
)
from local_inspection_service.text_inspection.standard_ports import StandardAccess, StandardParsers
from local_inspection_service.text_inspection.document_ports import DocumentModels
from local_inspection_service.text_inspection.preparation_ports import PreparationModels
from local_inspection_service.text_inspection.revisions import confirmed_snapshot, expected_revision
from local_inspection_service.text_inspection.projection import public_record
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed
from local_inspection_service.storage.artifacts.files import BusinessFiles
from smoke_text_storage_composition import build


def digest(data): return hashlib.sha256(data).hexdigest()


def assemble(directory, owner):
    storage = build(directory)
    identity = ContextVar('standard-domain-' + owner, default=(owner, owner))
    events = []
    entered, release = threading.Event(), threading.Event()
    block = [False]
    calls = []
    @contextmanager
    def scope():
        events.append(('enter', threading.get_ident()))
        try: yield
        finally: events.append(('exit', threading.get_ident()))
    def permission(name, *, detail):
        if identity.get()[0] == 'denied': raise HTTPException(403, detail)
    def transport(request, settings, *, timeout):
        attempt = storage.records.owned('assets', 'asset', owner)['classification_attempt']
        assert attempt['state'] == 'attempting' and settings['single_attempt'] is True
        calls.append(threading.get_ident())
        entered.set()
        if block[0]: assert release.wait(3)
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{
            'content':json.dumps({'category':'label_design','reason':'synthetic artwork'})}}],
            'usage':{'total_tokens':1}}).encode())
    settings = {'provider':'qwen','model':'synthetic','api_key':'synthetic-only',
                'base_url':'https://fixture.invalid','profile_id':'fixture','profile_version':1}
    graph = TextStandardWorkflows(records=storage.records,
        access=StandardAccess(permission, identity.get),
        media=StandardMediaStorage(lambda: directory/'media', digest,
            lambda data, mime: 'synthetic-data-url', lambda: None, BusinessFiles(runtime_provider=lambda: None)),
        policy=StandardPolicy(lambda: public_record, confirmed_snapshot, lambda: expected_revision,
            lambda: lambda text, length: str(text)[:length],
            lambda data: (data, 'image/png', '.png', 'PNG'), lambda who: False),
        parsers=StandardParsers(lambda: Mock(side_effect=AssertionError('unexpected DOC parser')),
            Mock(side_effect=AssertionError('unexpected DOCX parser')),
            Mock(side_effect=AssertionError('unexpected PDF parser'))),
        documents=DocumentModels(lambda: True, lambda purpose: dict(settings), transport, lambda *a: None),
        preparation=PreparationModels(lambda purpose: dict(settings), lambda: False,
            Mock(side_effect=AssertionError('unexpected provider')), lambda *a: {}),
        runtime=StandardThreadScope(scope, lambda: events.append(('clear', threading.get_ident()))),
        raw_rows=lambda rows: rows)
    app = FastAPI()
    graph.register_standards(app)
    graph.register_documents(app)
    graph.register_preparation(app)
    @app.middleware('http')
    async def user(request, call_next):
        who = request.headers.get('x-owner', owner)
        token = identity.set((who, who))
        try: return await call_next(request)
        finally: identity.reset(token)
    return SimpleNamespace(graph=graph, storage=storage, app=app, events=events,
        entered=entered, release=release, block=block, calls=calls, owner=owner)


def seed(f):
    f.storage.records.save('standards', {'id':'order','owner_user_id':f.owner,
        'standard_type':'label','status':'draft','material_code':'same','version_label':'v1',
        'name':f.owner,'created_at':1,'revision_number':0})
    output = io.BytesIO(); Image.new('RGB', (100,60), 'white' if f.owner == 'alice' else 'lightblue').save(output, 'PNG')
    data = output.getvalue()
    path = f.graph.media_path(f.owner, 'order', 'source.png')
    f.graph.write(path, data)
    f.storage.records.save('assets', {'id':'asset','owner_user_id':f.owner,'standard_id':'order',
        'status':'candidate','ordinal':1,'sha256':digest(data),'media_path':str(path),'mime_type':'image/png'})
    return data


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='standard-domain-')
        self.addCleanup(self.temporary.cleanup); self.root = Path(self.temporary.name)
        env = patch.dict(os.environ, {'VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS':'alice,bob'})
        env.start(); self.addCleanup(env.stop)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('real provider'))
        network.start(); self.addCleanup(network.stop)
        process = patch('subprocess.Popen', side_effect=AssertionError('external process'))
        process.start(); self.addCleanup(process.stop)

    def test_parent_derived_external_ports_aliases_and_registration_positions(self):
        source = (ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8')
        fixture = json.loads((ROOT/'tests/backend_contract/text_standard_workflows_ports.json').read_text())
        aliases = {'_text_media':'media','_text_revisions':'revisions','_standard_access':'access',
            '_standard_records':'standard_records','_standard_media':'standard_media',
            '_standard_imports':'imports','_standard_library':'library','_standard_edits':'edits',
            '_document_records':'document_records','_document_models':'document_models',
            '_preparation_records':'preparation_records','_preparation_media':'preparation_media',
            '_preparation_models':'preparation_models'}
        registrars = {'_standard_routes':'register_standards','document_import_jobs':'register_documents',
                      'standard_preparation_jobs':'register_preparation'}
        def check(text):
            tree = ast.parse(text)
            def binding(name):
                nodes = [n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
                self.assertEqual(len(nodes),1,name)
                return nodes[0].value
            graph = binding('_text_standards')
            self.assertEqual(ast.dump(graph.func), ast.dump(ast.Name('TextStandardWorkflows',ast.Load())))
            actual = {k.arg:k.value for k in graph.keywords}
            self.assertEqual(set(actual),set(fixture['expressions']))
            for name, expression in fixture['expressions'].items():
                self.assertEqual(ast.dump(actual[name]),ast.dump(ast.parse(expression,mode='eval').body),name)
            for name, member in aliases.items():
                self.assertEqual(ast.dump(binding(name)),ast.dump(ast.parse('_text_standards.'+member,mode='eval').body))
            for name, member in registrars.items():
                self.assertEqual(ast.dump(binding(name)),ast.dump(ast.parse('_text_standards.'+member+'(app)',mode='eval').body))
            imports = [n for n in tree.body if isinstance(n,ast.ImportFrom)
                       and n.module=='text_inspection.standard_composition' and n.level==1]
            self.assertEqual(len(imports),1)
            self.assertEqual([(a.name,a.asname) for a in imports[0].names],
                [(name,None) for name in ('TextStandardWorkflows','StandardMediaStorage','StandardPolicy','StandardThreadScope')])
            for n in tree.body:
                if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.AsyncFunctionDef)):
                    self.assertNotIn(n.name,('TextStandardWorkflows','StandardMediaStorage','StandardPolicy','StandardThreadScope'))
                if isinstance(n,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
                    targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                    for t in targets:
                        self.assertFalse(any(isinstance(v,ast.Name) and v.id in ('TextStandardWorkflows','StandardMediaStorage','StandardPolicy','StandardThreadScope') for v in ast.walk(t)))
        check(source)
        for mutation in ('owner','repository','scope','alias','registrar','shadow'):
            tree=ast.parse(source)
            graph=next(n.value for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=='_text_standards' for t in n.targets))
            if mutation in ('owner','repository','scope'):
                name={'owner':'access','repository':'records','scope':'runtime'}[mutation]
                next(k for k in graph.keywords if k.arg==name).value=ast.parse('None',mode='eval').body
            elif mutation in ('alias','registrar'):
                name='_preparation_media' if mutation=='alias' else 'document_import_jobs'
                node=next(n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
                node.value=ast.parse('_text_standards.media' if mutation=='alias' else '_text_standards.register_preparation(app)',mode='eval').body
            else: tree.body.append(ast.parse('TextStandardWorkflows = None').body[0])
            ast.fix_missing_locations(tree)
            with self.assertRaises(AssertionError): check(ast.unparse(tree))

    def test_inert_full_domain_constructor(self):
        poison = Mock(side_effect=AssertionError('constructor performed external work'))
        def ports(cls): return cls(**{f.name:poison for f in fields(cls)})
        store = build(self.root, repository=poison)
        graph = TextStandardWorkflows(records=store.records, access=ports(StandardAccess),
            media=ports(StandardMediaStorage), policy=ports(StandardPolicy), parsers=ports(StandardParsers),
            documents=ports(DocumentModels), preparation=ports(PreparationModels),
            runtime=ports(StandardThreadScope), raw_rows=poison)
        poison.assert_not_called()
        self.assertIs(graph.documents.records, graph.document_records)
        self.assertIs(graph.preparation.records, graph.preparation_records)
        self.assertIs(graph.preparation.media_dependencies, graph.preparation_media)
        self.assertIsNot(graph.documents.runtime, graph.preparation.runtime)
        self.assertEqual(graph.standard_media.write(), graph.write)
        self.assertEqual(graph.edits.revisions.apply(), graph.apply_revision)
        self.assertFalse((self.root/'records').exists())

    def test_selected_owned_wrapper_resolves_record_store_after_argument_effects(self):
        def check(eager):
            f=assemble(self.root/('eager' if eager else 'owned'), 'alice')
            another=build(self.root/'second-store')
            old=Mock(return_value=None); late=Mock(return_value=None)
            with patch.object(f.storage.records,'owned',old), patch.object(another.records,'owned',late):
                if eager:
                    f.graph.media.records=replace(f.graph.media.records,
                        owned=lambda: f.graph.records.owned)
                selected=f.graph.media.records.owned()
                def argument():f.graph.records=another.records;return 'same'
                self.assertIsNone(selected('standards',argument(),'alice'))
                late.assert_called_once_with('standards','same','alice');old.assert_not_called()
        check(False)
        with self.assertRaises(AssertionError):check(True)

    def test_two_actual_registered_domains_same_ids_media_and_permission_isolation(self):
        a, b = assemble(self.root/'a', 'alice'), assemble(self.root/'b', 'bob')
        data_a, data_b = seed(a), seed(b)
        self.assertNotEqual(data_a, data_b)
        with TestClient(a.app) as ca, TestClient(b.app) as cb:
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(client.get, '/api/text-inspection/standards/order') for client in (ca, cb)]
                for future, owner in zip(futures, ('alice','bob')):
                    response = future.result(timeout=5)
                    self.assertEqual(response.status_code, 200); self.assertEqual(response.json()['name'], owner)
            self.assertEqual(ca.get('/api/text-inspection/standards/order', headers={'x-owner':'bob'}).status_code, 404)
            self.assertEqual(ca.get('/api/text-inspection/standards', headers={'x-owner':'denied'}).status_code, 403)
            self.assertEqual(ca.get('/api/text-inspection/assets/asset/content').content, data_a)
            self.assertEqual(cb.get('/api/text-inspection/assets/asset/content').content, data_b)
            self.assertTrue(a.graph.documents.close(1)); self.assertTrue(a.graph.preparation.close(1))
            self.assertEqual(cb.get('/api/text-inspection/standards/order').status_code, 200)
            with self.assertRaises(TrainingRuntimeClosed): a.graph.documents.start('order', 'alice')
        self.assertEqual(a.calls, []); self.assertEqual(b.calls, [])

    def test_actual_native_classification_persists_attempt_before_call_and_scope_cleanup(self):
        f = assemble(self.root, 'alice'); seed(f)
        with TestClient(f.app) as client:
            response = client.post('/api/text-inspection/standards/order/classify')
            self.assertEqual(response.status_code, 200)
        self.assertTrue(f.graph.documents.close(3))
        asset = f.storage.records.owned('assets', 'asset', 'alice')
        self.assertEqual(asset['classification_attempt']['state'], 'finished')
        self.assertEqual(f.storage.records.owned('standards','order','alice')['classification']['state'], 'completed')
        self.assertEqual(len(f.calls), 1)
        thread = f.calls[0]; self.assertNotEqual(thread, threading.get_ident())
        self.assertEqual(f.events, [('enter',thread),('clear',thread),('exit',thread)])
        self.assertTrue(f.graph.preparation.close(1))

    def test_one_native_domain_drains_without_closing_or_retrying_the_other(self):
        a, b = assemble(self.root/'a', 'alice'), assemble(self.root/'b', 'bob')
        seed(a); seed(b); a.block[0] = True
        try:
            a.graph.documents.start('order', 'alice')
            self.assertTrue(a.entered.wait(2)); self.assertFalse(a.graph.documents.close(0))
            with self.assertRaises(TrainingRuntimeClosed): a.graph.documents.start('order', 'alice')
            b.graph.documents.start('order', 'bob'); self.assertTrue(b.graph.documents.close(3))
            self.assertEqual(len(a.calls), 1); self.assertEqual(len(b.calls), 1)
            self.assertEqual(a.storage.records.owned('assets','asset','alice')['classification_attempt']['state'], 'attempting')
        finally:
            a.release.set(); self.assertTrue(a.graph.documents.close(3))
            self.assertTrue(a.graph.preparation.close(1)); self.assertTrue(b.graph.preparation.close(1))
        self.assertEqual(len(a.calls), 1)

    def test_actual_native_preparation_owns_media_revision_and_thread_cleanup(self):
        from local_inspection_service import standard_preparation as engine
        from local_inspection_service.scripts.smoke_standard_preparation import fixture
        from local_inspection_service.text_inspection.preparation_ports import PreparationModels
        f, other = assemble(self.root/'prepare', 'alice'), assemble(self.root/'other', 'bob')
        seed(f); seed(other)
        image, elements = fixture(); blob = engine.png(image)
        asset = f.storage.records.owned('assets', 'asset', 'alice')
        f.graph.write(Path(asset['media_path']), blob)
        asset['sha256'] = digest(blob); f.storage.records.save('assets', asset)
        calls = []
        def provider(name, payload):
            current = f.storage.records.owned('assets', 'asset', 'alice')
            self.assertEqual(current['preparation_attempt']['state'], 'classifying')
            self.assertEqual(payload['max_attempts'], 1)
            self.assertIsNone(other.storage.records.owned('assets', 'asset', 'bob').get('preparation_attempt'))
            calls.append(threading.get_ident())
            return {'ok':True, 'parsed':{'kind':'label_design','coverage_complete':True,
                'missing_regions':[],'reason':'synthetic',
                'elements':[{k:e[k] for k in ('id','state','reason')} for e in elements]}}
        f.graph.preparation.models = PreparationModels(
            lambda purpose: {'configured':True,'provider':'qwen','model':'synthetic',
                'api_key':'synthetic-only','profile_id':'bound','profile_version':7},
            lambda: True, provider, lambda *args: {})
        with patch.dict(os.environ, {'VANTALINE_STANDARD_PREPARATION_ACCOUNTS':'alice'}), \
                patch.object(f.graph.preparation, 'observe', side_effect=lambda *a, **k: copy.deepcopy(elements)):
            with TestClient(f.app) as client:
                response = client.post('/api/text-inspection/standards/order/preparation')
                self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(f.graph.preparation.close(3))
        saved = f.storage.records.owned('assets', 'asset', 'alice')
        self.assertEqual(saved['preparation_attempt']['state'], 'ready')
        standard = f.storage.records.owned('standards','order','alice')
        self.assertEqual(standard['preparation_job']['state'], 'completed')
        self.assertEqual(standard['revision_number'], 2)
        self.assertEqual([r['action'] for r in sorted(f.storage.records.load('revisions'), key=lambda r:r['revision_number'])], ['baseline', 'prepare'])
        self.assertEqual(other.storage.records.load('revisions'), [])
        revision = saved['active_preparation']
        for kind in ('clean','overlay'):
            path = f.graph.media_path('alice','order', 'preparation_' + revision['id'] + '_' + kind + '.png')
            data = f.graph.read_verified(str(path),'alice','order', expected_sha256=revision[kind+'_sha256'])
            self.assertEqual(digest(data), revision[kind+'_sha256'])
            with self.assertRaises(HTTPException):
                other.graph.read_verified(str(path),'bob','order')
        self.assertEqual(len(calls), 1)
        thread = calls[0]; self.assertNotEqual(thread, threading.get_ident())
        self.assertEqual(f.events, [('enter',thread),('clear',thread),('exit',thread)])
        self.assertTrue(f.graph.preparation.slots.acquire(False))
        f.graph.preparation.slots.release()
        self.assertTrue(f.graph.documents.close(1)); self.assertTrue(other.graph.documents.close(1))
        self.assertTrue(other.graph.preparation.close(1))

    def test_owned_revision_transaction_and_partial_failure_order(self):
        f = assemble(self.root, 'alice'); seed(f)
        standard = f.storage.records.owned('standards','order','alice')
        assets = f.storage.records.load('assets')
        with f.storage.lock:
            revision = f.graph.apply_revision(standard, assets, action='confirm', asset_id='', now=10)
            f.storage.records.save('standards', standard)
        self.assertEqual(f.storage.records.load('revisions')[0]['id'], revision['id'])
        self.assertEqual(f.storage.records.owned('standards','order','alice')['revision_number'], 1)
        failure = OSError('synthetic revision store failure')
        original = f.storage.records.save
        def save(kind, value, **kw):
            if kind == 'revisions': raise failure
            return original(kind, value, **kw)
        with patch.object(f.storage.records, 'save', side_effect=save), f.storage.lock:
            with self.assertRaises(OSError) as caught:
                f.graph.apply_revision(standard, assets, action='confirm', asset_id='', now=11)
        self.assertIs(caught.exception, failure)
        self.assertEqual(standard['revision_number'], 2)
        self.assertEqual(len(f.storage.records.load('revisions')), 1)
        self.assertEqual(f.calls, [])


if __name__ == '__main__': unittest.main()
