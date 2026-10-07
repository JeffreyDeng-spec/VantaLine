"""Actual comparison graphs and registered history/extraction/review ownership."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
import ast
import json
import copy
import io
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from fastapi import FastAPI, HTTPException
from PIL import Image
from fastapi.testclient import TestClient
from local_inspection_service.text_inspection.comparison_composition import (
    TextComparisonWorkflows, ComparisonImages, ComparisonAudit)
from local_inspection_service.text_inspection.standard_composition import StandardThreadScope
from local_inspection_service.text_inspection.inspection_ports import (
    InspectionAccess, SubmissionModels, SubmissionPolicy, SubmissionDiagnostics)
from local_inspection_service.text_inspection.extraction_ports import ExtractionModels
from local_inspection_service.text_inspection.comparison_ports import ComparisonModels
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed
from local_inspection_service import standard_preparation as engine
from local_inspection_service.scripts.smoke_standard_preparation import fixture
from smoke_text_standard_composition import assemble, seed, digest


def ports(cls):
    return cls(**{f.name:Mock(side_effect=AssertionError('unexpected capability '+f.name)) for f in fields(cls)})


def compose(directory, owner, *, provider=None, enabled=False):
    f=assemble(directory, owner)
    events=[];audit=[];done=threading.Event();settings={'configured':enabled,'provider':'synthetic','model':owner,'timeout_seconds':1}
    @contextmanager
    def scope():
        events.append(('enter',threading.get_ident()))
        try:yield
        finally:events.append(('exit',threading.get_ident()));done.set()
    graph=TextComparisonWorkflows(standards=f.graph,
        access=InspectionAccess(f.graph.access.require_permission, f.graph.access.owner),
        images=replace(ports(ComparisonImages),data_url=lambda data,mime:"synthetic-image"),models=ports(SubmissionModels),policy=ports(SubmissionPolicy),
        diagnostics=ports(SubmissionDiagnostics),extraction=ExtractionModels(
            lambda:dict(settings),lambda purpose:{},provider or Mock(side_effect=AssertionError('paid image')),
            Mock(side_effect=AssertionError('paid transport')),copy.deepcopy,lambda:enabled),
        prepared_models=lambda:ComparisonModels(Mock(side_effect=AssertionError('paid profile')),False,None),
        digest=lambda:digest,environment=lambda: (lambda name,default:default),
        prepared_cleanup=lambda: (lambda:events.append(('clear',threading.get_ident()))),
        audit=ComparisonAudit(lambda:audit.append,lambda:lambda value,length:str(value or '')[:length]),
        runtime=StandardThreadScope(scope,lambda:events.append(('clear',threading.get_ident()))),
        files=f.graph.edits.files)
    graph.register_history(f.app);graph.register_extraction(f.app);graph.register_inspections(f.app)
    return SimpleNamespace(graph=graph,standard=f,events=events,audit=audit,app=f.app,done=done)


def prepared(f):
    seed(f.standard)
    image,elements=fixture();data=engine.png(image);clean,template=engine.clean(image,elements)
    template['id']='same-template';template['clean_sha256']=digest(clean)
    asset=f.standard.storage.records.owned('assets','asset',f.standard.owner)
    asset['sha256']=digest(data);f.standard.graph.write(Path(asset['media_path']),data)
    asset['preparation_revisions']=[template];asset['active_preparation']=template
    f.standard.storage.records.save('assets',asset)
    path=f.standard.graph.media_path(f.standard.owner,'order','preparation_same-template_clean.png')
    f.standard.graph.write(path,clean)
    standard=f.standard.storage.records.owned('standards','order',f.standard.owner)
    standard.update(status='confirmed',revision_number=1,current_revision_id='same-revision')
    f.standard.storage.records.save('standards',standard)
    return standard,asset,{'preparation':template},data,elements


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='comparison-domain-')
        self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        network=patch('requests.sessions.Session.request',side_effect=AssertionError('network'))
        network.start();self.addCleanup(network.stop)
        process=patch('subprocess.Popen',side_effect=AssertionError('external process'))
        process.start();self.addCleanup(process.stop)

    def close(self,f):
        self.assertTrue(f.graph.comparison_runtime.close(3));self.assertTrue(f.graph.extraction_runtime.close(3))
        self.assertTrue(f.standard.graph.documents.close(1));self.assertTrue(f.standard.graph.preparation.close(1))

    def test_parent_derived_ports_aliases_registrars_and_shadow_rejection(self):
        source=(ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8')
        fixture=json.loads((ROOT/'tests/backend_contract/text_comparison_workflows_ports.json').read_text())
        aliases={'_history_records':'history_records','_history_media':'history_media',
            '_extraction_records':'extraction_records','_extraction_media':'extraction_media',
            '_extraction_models':'extraction_models','_text_extraction_runtime':'extraction_runtime',
            '_prepared_comparison_runtime':'comparison_runtime','_inspection_access':'access',
            '_inspection_records':'inspection_records','_comparison_submission':'submission',
            '_inspection_reviews':'reviews'}
        imported=('TextComparisonWorkflows','ComparisonImages','ComparisonAudit')
        def check(text):
            tree=ast.parse(text)
            def binding(name):
                nodes=[n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
                self.assertEqual(len(nodes),1,name);return nodes[0].value
            graph=binding('_text_comparisons');self.assertEqual(ast.unparse(graph.func),'TextComparisonWorkflows')
            actual={k.arg:k.value for k in graph.keywords};self.assertEqual(set(actual),set(fixture['expressions']))
            for name,expression in fixture['expressions'].items():
                self.assertEqual(ast.dump(actual[name]),ast.dump(ast.parse(expression,mode='eval').body),name)
            for name,member in aliases.items():
                self.assertEqual(ast.dump(binding(name)),ast.dump(ast.parse('_text_comparisons.'+member,mode='eval').body))
            for name,member in [('resolve_label_extraction','register_extraction'),('_inspection_routes','register_inspections')]:
                self.assertEqual(ast.dump(binding(name)),ast.dump(ast.parse('_text_comparisons.'+member+'(app)',mode='eval').body))
            history=[n for n in tree.body if isinstance(n,ast.Expr) and ast.unparse(n.value)=='_text_comparisons.register_history(app)']
            self.assertEqual(len(history),1)
            imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='text_inspection.comparison_composition' and n.level==1]
            self.assertEqual(len(imports),1);self.assertEqual([(a.name,a.asname) for a in imports[0].names],[(x,None) for x in imported])
            protected=set(aliases)|{'_text_comparisons','resolve_label_extraction','_inspection_routes'}
            for node in tree.body:
                if isinstance(node,(ast.Import,ast.ImportFrom)):
                    for entry in node.names:
                        bound=entry.asname or (entry.name.split('.')[0] if isinstance(node,ast.Import) else entry.name)
                        if bound in imported:self.assertIs(node,imports[0])
                        self.assertNotIn(bound,protected)
                if isinstance(node,(ast.AnnAssign,ast.AugAssign)):
                    self.assertFalse(any(isinstance(x,ast.Name) and x.id in protected|set(imported) for x in ast.walk(node.target)))
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    self.assertNotIn(node.name,protected)
            for n in tree.body:
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):self.assertNotIn(n.name,imported)
                if isinstance(n,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
                    for target in n.targets if isinstance(n,ast.Assign) else [n.target]:
                        self.assertFalse(any(isinstance(x,ast.Name) and x.id in imported for x in ast.walk(target)))
        check(source)
        for mutation in ('standards','models','runtime','alias','shadow','wrong-import','annotated-owner','annotated-runtime','augmented-owner'):
            tree=ast.parse(source)
            graph=next(n.value for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=='_text_comparisons' for t in n.targets))
            if mutation in ('standards','models','runtime'):
                next(k for k in graph.keywords if k.arg==mutation).value=ast.parse('None',mode='eval').body
            elif mutation=='alias':
                node=next(n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='_prepared_comparison_runtime' for t in n.targets))
                node.value=ast.parse('_text_comparisons.extraction_runtime',mode='eval').body
            elif mutation=='shadow':tree.body.append(ast.parse('TextComparisonWorkflows = None').body[0])
            elif mutation=='wrong-import':tree.body.append(ast.parse('from local_inspection_service.text_inspection.history import register as TextComparisonWorkflows').body[0])
            elif mutation=='annotated-owner':tree.body.append(ast.parse('_text_comparisons: object = None').body[0])
            elif mutation=='annotated-runtime':tree.body.append(ast.parse('_prepared_comparison_runtime: object = None').body[0])
            else:tree.body.append(ast.parse('_text_comparisons += None').body[0])
            ast.fix_missing_locations(tree)
            with self.assertRaises(AssertionError):check(ast.unparse(tree))

    def test_saved_owned_wrapper_selects_standard_owner_after_argument_effect(self):
        def check(eager):
            f=compose(self.root/('eager' if eager else 'owned'),'alice')
            other=assemble(self.root/'late','bob');old,late=Mock(return_value=None),Mock(return_value=None)
            try:
                with patch.object(f.standard.graph,'owned',old),patch.object(other.graph,'owned',late):
                    if eager:
                        f.graph.inspection_records=replace(f.graph.inspection_records,owned=lambda:f.graph.standards.owned)
                    selected=f.graph.inspection_records.owned()
                    def argument():f.graph.standards=other.graph;return 'same'
                    self.assertIsNone(selected('records',argument(),'bob'))
                    late.assert_called_once_with('records','same','bob');old.assert_not_called()
            finally:
                self.close(f);self.assertTrue(other.graph.documents.close(1));self.assertTrue(other.graph.preparation.close(1))
        check(False)
        with self.assertRaises(AssertionError):check(True)

    def test_actual_constructor_performs_no_store_model_identity_or_media_calls(self):
        standard=assemble(self.root,'alice').graph
        poison=Mock(side_effect=AssertionError('constructor used capability'))
        with patch.object(standard,'load',poison),patch.object(standard,'owned',poison), \
                patch.object(standard,'save',poison),patch.object(standard,'media_path',poison):
            graph=TextComparisonWorkflows(standards=standard,access=ports(InspectionAccess),
                images=ports(ComparisonImages),models=ports(SubmissionModels),policy=ports(SubmissionPolicy),
                diagnostics=ports(SubmissionDiagnostics),extraction=ports(ExtractionModels),
                prepared_models=poison,digest=poison,environment=poison,prepared_cleanup=poison,audit=ports(ComparisonAudit),
                runtime=StandardThreadScope(poison,poison),files=poison)
            poison.assert_not_called()
        app=FastAPI();before=len(app.routes)
        with self.assertRaisesRegex(RuntimeError,'assembled before admission'):graph.register_inspections(app)
        self.assertEqual(len(app.routes),before)
        self.assertTrue(graph.comparison_runtime.close(1));self.assertTrue(graph.extraction_runtime.close(1))
        self.assertTrue(standard.documents.close(1));self.assertTrue(standard.preparation.close(1))

    def test_native_extraction_persists_before_unknown_provider_and_never_retries(self):
        calls=[];holder={}
        class Provider:
            def generate_image(provider,prompt,images,*,model):
                f=holder['f'];rows=f.standard.storage.records.load('extractions')
                self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'attempting')
                self.assertTrue(Path(rows[0]['source_path']).is_file())
                calls.append(threading.get_ident());raise TimeoutError('synthetic unknown')
        f=compose(self.root,'alice',provider=lambda settings:Provider(),enabled=True);holder['f']=f
        image,unused=fixture();blob=engine.png(image)
        request={'data':{'target':'[0.1,0.1,0.8,0.8]','request_id':'same_request','method':'ai'},
                 'files':{'file':('fixture.png',blob,'image/png')}}
        try:
            with patch.dict(os.environ,{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice'}),TestClient(f.app) as client:
                first=client.post('/api/text-inspection/extractions',**request)
                self.assertEqual(first.status_code,200,first.text)
                # Wait for the actual worker without closing admission before the duplicate check.
                self.assertTrue(f.done.wait(3))
                again=client.post('/api/text-inspection/extractions',**request)
                self.assertEqual(again.status_code,200,again.text)
            self.assertTrue(f.graph.extraction_runtime.close(3))
            saved=f.standard.storage.records.load('extractions')[0]
            self.assertEqual(saved['status'],'uncertain')
            self.assertEqual(saved['error_code'],'TimeoutError');self.assertEqual(len(calls),1)
            thread=calls[0];self.assertNotEqual(thread,threading.get_ident())
            self.assertEqual(f.events,[('enter',thread),('clear',thread),('exit',thread)])
        finally:self.close(f)

    def test_inert_graph_and_explicit_unassembled_extraction_failure(self):
        f=compose(self.root,'alice')
        self.assertEqual(f.events,[])
        self.assertIs(f.graph.submission.records,f.graph.reviews.records)
        self.assertIsNot(f.graph.comparison_runtime.threads,f.graph.extraction_runtime)
        resolver=f.graph._extraction_resolver;f.graph._extraction_resolver=None
        with self.assertRaisesRegex(RuntimeError,'assembled before admission'):
            f.graph.resolve_extraction('id','alice','asset',{})
        f.graph._extraction_resolver=resolver;self.close(f)

    def test_two_registered_domain_histories_evidence_reviews_and_manual_extractions(self):
        a,b=compose(self.root/'a','alice'),compose(self.root/'b','bob')
        for f in (a,b):
            blob=seed(f.standard);path=f.standard.graph.media_path(f.standard.owner,'order','captured.png')
            f.standard.graph.write(path,blob)
            f.standard.storage.records.save('records',{'id':'same','owner_user_id':f.standard.owner,
                'standard_id':'order','created_at':1,'status':'completed','source_path':str(path),
                'source_sha256':digest(blob),'decision':'REVIEW_REQUIRED'})
        with TestClient(a.app) as ca,TestClient(b.app) as cb, \
                patch.dict(os.environ,{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice,bob'}):
            with ThreadPoolExecutor(2) as pool:
                responses=[pool.submit(client.get,'/api/text-inspection/history/same') for client in (ca,cb)]
                for response in responses:self.assertEqual(response.result().status_code,200)
            images=[client.get('/api/text-inspection/inspections/same/evidence/source').content for client in (ca,cb)]
            self.assertNotEqual(*images)
            self.assertEqual(ca.get('/api/text-inspection/history/same',headers={'x-owner':'bob'}).status_code,404)
            self.assertEqual(ca.get('/api/text-inspection/history',headers={'x-owner':'denied'}).status_code,403)
            response=ca.post('/api/text-inspection/inspections/same/review',json={'decision':'PASS','reason':'fixture'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(a.audit),1);self.assertEqual(b.audit,[])
            self.assertNotIn('final_decision',b.standard.storage.records.owned('records','same','bob'))
            for client,blob in zip((ca,cb),images):
                output=io.BytesIO()
                with Image.open(io.BytesIO(blob)) as image:image.resize((200,120)).save(output,'PNG')
                blob=output.getvalue()
                response=client.post('/api/text-inspection/extractions',
                    data={'target':'[0.1,0.1,0.8,0.8]','request_id':'same_request','method':'manual'},
                    files={'file':('source.png',blob,'image/png')})
                self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(a.standard.storage.records.load('extractions')),1)
            self.assertEqual(len(b.standard.storage.records.load('extractions')),1)
            self.close(a)
            self.assertEqual(cb.get('/api/text-inspection/history/same').status_code,200)
        self.close(b)

    def test_native_comparison_failure_drains_one_owner_while_the_other_completes(self):
        a,b=compose(self.root/'a','alice'),compose(self.root/'b','bob')
        data_a,data_b=prepared(a),prepared(b)
        entered,release=threading.Event(),threading.Event();calls=[]
        def fail(*args,**kwargs):
            calls.append('a');entered.set();self.assertTrue(release.wait(3))
            raise TimeoutError('synthetic OCR timeout')
        def succeed(*args,**kwargs):calls.append('b');return copy.deepcopy(data_b[-1])
        try:
            with patch.object(a.standard.graph.preparation,'observe',side_effect=fail), \
                    patch.object(b.standard.graph.preparation,'observe',side_effect=succeed), \
                    patch.dict(os.environ,{'VANTALINE_QWEN_OCR_ACCOUNTS':''}):
                standard,asset,snapshot,blob,_=data_a
                ra=a.graph.submit_prepared('alice','alice',standard,asset,snapshot,blob,'same_request',None)
                self.assertTrue(entered.wait(2));self.assertFalse(a.graph.comparison_runtime.close(0))
                standard,asset,snapshot,blob,_=data_b
                rb=b.graph.submit_prepared('bob','bob',standard,asset,snapshot,blob,'same_request',None)
                self.assertTrue(b.graph.comparison_runtime.close(3))
                self.assertEqual(b.standard.storage.records.owned('records',rb['id'],'bob')['status'],'completed')
                release.set();self.assertTrue(a.graph.comparison_runtime.close(3))
            failed=a.standard.storage.records.owned('records',ra['id'],'alice')
            self.assertEqual(failed['status'],'review_required')
            self.assertEqual(failed['diagnostics']['error_type'],'TimeoutError')
            self.assertEqual(calls,['a','b'])
            self.assertEqual(len(a.standard.storage.records.load('records')),1)
            self.assertEqual(len(b.standard.storage.records.load('records')),1)
        finally:release.set();self.close(a);self.close(b)

    def test_actual_prepared_native_job_persists_before_ocr_and_owns_revision_media(self):
        f=compose(self.root,'alice');standard,asset,snapshot,blob,elements=prepared(f);calls=[]
        def observe(image,**kw):
            rows=f.standard.storage.records.load('records')
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'attempting')
            calls.append(threading.get_ident());return copy.deepcopy(elements)
        with patch.object(f.standard.graph.preparation,'observe',side_effect=observe), \
                patch.dict(os.environ,{'VANTALINE_QWEN_OCR_ACCOUNTS':''}):
            result=f.graph.submit_prepared('alice','alice',standard,asset,snapshot,blob,'same_request',None)
            self.assertTrue(f.graph.comparison_runtime.close(3))
        saved=f.standard.storage.records.owned('records',result['id'],'alice')
        self.assertEqual(saved['status'],'completed');self.assertEqual(saved['decision'],'REVIEW_REQUIRED')
        self.assertEqual(len(calls),1);thread=calls[0]
        self.assertNotEqual(thread,threading.get_ident())
        self.assertEqual(f.events,[('enter',thread),('clear',thread),('exit',thread)])
        self.assertTrue(Path(saved['reference_overlay_path']).is_file())
        with self.assertRaises(TrainingRuntimeClosed):
            f.graph.submit_prepared('alice','alice',standard,asset,snapshot,blob,'another_request',None)
        self.assertEqual(len(f.standard.storage.records.load('records')),1)
        self.close(f)


if __name__=='__main__':unittest.main()
