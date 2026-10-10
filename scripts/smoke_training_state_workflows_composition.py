"""Training state ownership and parent-derived assembly contracts; synthetic only."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import typing
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from smoke_training_record_store import Fixture, task
from local_inspection_service.runtime.training_tasks import TrainingTaskRuntime, TrainingRuntimeClosed
from local_inspection_service.training.record_store import TrainingRows
from local_inspection_service.training.task_lifecycle import TrainingTaskWrites
from local_inspection_service.training.task_views import TrainingViewAccess
from local_inspection_service.training import state_composition as module
FIXTURE=json.loads((ROOT/'tests/backend_contract/training_state_workflows_ports.json').read_text())

def canonical_ast(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, [[name, canonical_ast(value)] for name, value in ast.iter_fields(node) if name != 'type_params']]
    if isinstance(node, list):
        return [canonical_ast(value) for value in node]
    if node is Ellipsis:
        return ['constant', 'Ellipsis']
    if isinstance(node, (bytes, complex)):
        return ['constant', repr(node)]
    return node

def verify_composition(source):
    # Protect the actual constructor edges, wrapper argument order and imported classes.
    assert hashlib.sha256(json.dumps(canonical_ast(ast.parse(source)),ensure_ascii=False).encode()).hexdigest()==FIXTURE['composition_ast_sha256']

def verify_root(source):
    from training_task_source_contract import restore_training_task_root
    source=restore_training_task_root(source)
    tree=ast.parse(source)
    protected={'TrainingStateWorkflows','TrainingRecordAccess','TrainingTaskWrites','TrainingViewAccess',
               'TrainingRows','_training_task_runtime','_training_state_workflows',
               '_training_records','_training_lifecycle','_training_views'}
    imports=[ast.unparse(n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)) and any((a.asname or a.name) in protected for a in n.names)]
    assert not any(isinstance(n,ast.ImportFrom) and any(a.name=='*' for a in n.names) for n in tree.body)
    assert imports==FIXTURE['protected_imports']
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            assert node.name not in protected
        elif isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            assert not any(isinstance(n,ast.Name) and n.id in (protected-{'_training_task_runtime','_training_state_workflows','_training_records','_training_lifecycle','_training_views'}) for target in targets for n in ast.walk(target))
    restored=[]
    counts={}
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            continue
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            counts[name]=counts.get(name,0)+1
            if name=='_training_state_workflows':
                assert ast.dump(node,include_attributes=False)==ast.dump(ast.parse(FIXTURE['owner_constructor']).body[0],include_attributes=False)
                continue
            if name in FIXTURE['constructors']:
                field={'_training_records':'records','_training_lifecycle':'lifecycle','_training_views':'views'}[name]
                assert ast.unparse(node.value)=='_training_state_workflows.'+field
                restored.append(ast.parse(FIXTURE['constructors'][name]).body[0]);continue
        if isinstance(node,ast.FunctionDef) and node.name in FIXTURE['wrappers']:
            old=FIXTURE['wrappers'][node.name]
            expected=old
            for alias in FIXTURE['constructors']:
                expected=expected.replace(alias+'.','_training_state_workflows.')
            assert ast.dump(node,include_attributes=False)==ast.dump(ast.parse(expected).body[0],include_attributes=False)
            restored.append(ast.parse(old).body[0]);continue
        restored.append(node)
    assert counts.get('_training_state_workflows')==1
    digest=hashlib.sha256(json.dumps(canonical_ast(ast.Module(body=restored,type_ignores=[])),ensure_ascii=False).encode()).hexdigest()
    assert digest==FIXTURE['parent_nonimport_ast_sha256']

class TrainingStateCompositionContracts(unittest.TestCase):
    def test_parent_assembly_and_business_sources(self):
        verify_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        source=(ROOT/'local_inspection_service/training/state_composition.py').read_text()
        verify_composition(source)
        for name,digest in FIXTURE['business_sha256'].items():
            data=(ROOT/'local_inspection_service/training'/name).read_bytes().replace(b'\r\n',b'\n')
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest)

    def test_actual_constructor_and_owner_guard_counterexamples(self):
        source=(ROOT/'local_inspection_service/training/state_composition.py').read_text()
        for before,after in (
            ('find=lambda job_id: self.find_training_task(job_id)','find=lambda job_id: self.training_task_path(job_id)'),
            ('guard=lambda: self.runtime.lock','guard=lambda: self.runtime.threads'),
            ('resolver=storage.resolver','resolver=storage.resolver()'),
            ('import TrainingTaskLifecycle,','import TrainingTaskRecords as TrainingTaskLifecycle,'),
        ):
            self.assertIn(before,source)
            with self.assertRaises(AssertionError):verify_composition(source.replace(before,after,1))
        with self.assertRaises(AssertionError):verify_composition(source+'\nclass TrainingStateWorkflows: pass\n')
        root_source=read_checked_application_source(ROOT / 'local_inspection_service/server.py')
        for name in ('TrainingStateWorkflows','_training_state_workflows','_training_records','_training_task_runtime','TrainingRows'):
            with self.subTest(import_shadow=name),self.assertRaises(AssertionError):
                verify_root(root_source+'\nimport os as '+name+'\n')
        with self.assertRaises(AssertionError):
            verify_root(root_source+'\nfrom .training.record_store import TrainingRecordStore as TrainingRows\n')

    def test_poisoned_constructor_and_failure_do_not_touch_supplied_runtime(self):
        from unittest.mock import patch
        poison=Mock(side_effect=AssertionError('constructor selected external dependency'))
        runtime=TrainingTaskRuntime()
        storage=module.TrainingRecordAccess(poison,poison,poison,poison,poison)
        kwargs=dict(runtime=runtime,storage=storage,
                    rows=TrainingRows(poison,poison,poison),
                    writes=TrainingTaskWrites(poison,poison,poison),
                    require_access=poison,view_access=TrainingViewAccess(poison,poison,poison))
        graph=module.TrainingStateWorkflows(**kwargs)
        poison.assert_not_called()
        self.assertIs(graph.runtime,runtime)
        self.assertEqual(runtime.threads,{})
        error=RuntimeError('lifecycle constructor failed')
        with patch.object(module,'TrainingTaskLifecycle',side_effect=error):
            with self.assertRaises(RuntimeError) as caught:module.TrainingStateWorkflows(**kwargs)
        self.assertIs(caught.exception,error)
        poison.assert_not_called()
        self.assertEqual(runtime.tombstones,{})
        self.assertEqual(runtime.submit(lambda launch:'still admits'),'still admits')
        self.assertTrue(runtime.close(1))

    def test_saved_callbacks_select_actual_owner_after_arguments(self):
        poison=Mock(side_effect=AssertionError('external service selected'))
        graph=module.TrainingStateWorkflows(
            runtime=TrainingTaskRuntime(),storage=module.TrainingRecordAccess(poison,poison,poison,poison,poison),
            rows=TrainingRows(poison,poison,poison),writes=TrainingTaskWrites(poison,poison,poison),
            require_access=poison,view_access=TrainingViewAccess(poison,poison,poison))
        callbacks=((graph.lifecycle.records.path,'records','training_task_path'),
                   (graph.lifecycle.records.load,'records','load_training_task'),
                   (graph.lifecycle.records.save,'records','save_training_task'),
                   (graph.lifecycle.records.find,'records','find_training_task'),
                   (graph.views.refresh,'lifecycle','refresh_interrupted_local_training_task'))
        for callback,field,method in callbacks:
            with self.subTest(method=method):
                old=Mock();new=Mock();getattr(new,method).return_value='new-owner'
                setattr(graph,field,old)
                class Arguments:
                    def __iter__(self):
                        setattr(graph,field,new)
                        yield 'synthetic-input'
                self.assertEqual(callback(*Arguments()),'new-owner')
                getattr(new,method).assert_called_once_with('synthetic-input')
                self.assertEqual(old.mock_calls,[])
        callback=graph.views.records
        new=Mock();new.load_training_task_records.return_value=[];graph.records=new
        self.assertEqual(callback(),[])
        new.load_training_task_records.assert_called_once_with()
        poison.assert_not_called()

    def test_two_actual_graphs_models_visibility_delete_and_native_drain(self):
        typing.get_type_hints(module.TrainingRecordAccess)
        typing.get_type_hints(module.TrainingStateWorkflows.__init__)
        with tempfile.TemporaryDirectory(prefix='training-state-private-') as directory:
            graphs = []
            for account in ('A', 'B'):
                root = Path(directory) / account
                root.mkdir()
                f = Fixture(root)
                runtime = TrainingTaskRuntime()
                runtime.lock = f.guard
                events = []
                def require(record, user, *, write=False):
                    if record['account'] != user['id']:
                        from fastapi import HTTPException
                        raise HTTPException(403, 'denied')
                def visible(record, user, target, events=events):
                    events.append(('visible', record['account']))
                    return record['account'] == user['id']
                graph = module.TrainingStateWorkflows(
                    runtime=runtime,
                    storage=module.TrainingRecordAccess(f.repository, lambda f=f: f.directory,
                                                       lambda f=f: f.provider, f.invalidate, f.enrich),
                    rows=TrainingRows(lambda: lambda record, **kw: record,
                                      lambda: lambda rows: rows, lambda path: path.stem),
                    writes=TrainingTaskWrites(f.repository, lambda record, **kw: record, f.invalidate),
                    require_access=require,
                    view_access=TrainingViewAccess(lambda record: dict(record),
                                                   lambda: lambda record: dict(record), visible))
                assert not f.events, 'construction selected external services'
                assert graph.records.guard() is runtime.lock is graph.lifecycle.state.guard()
                assert graph.lifecycle.state.threads() is runtime.threads
                assert graph.lifecycle.state.tombstones() is runtime.tombstones
                graphs.append((graph, f, events))
                graph.save_training_task(task('same', account=account, status='queued'))
                assert f.events[:4] == ['resolver', 'scope', ('freeze', True),
                                        ('invalidate', 'training_task_pairs', True)]
                f.resolver.version = 99
                updated = graph.update_training_task('same', label=account)
                assert updated['model_profiles']['pipeline']['version'] == 1
                f.seed('foreign', task('foreign', account='other', status='queued', model_profiles={}))
                listed = graph.list_training_tasks({'id': account})
                assert len(listed) == 1 and listed[0]['status'] == 'stopped'
                assert json.loads((f.directory / 'foreign.json').read_text())['status'] == 'queued'
            a, fa, _ = graphs[0]
            b, fb, _ = graphs[1]
            assert a.runtime is not b.runtime and fa.directory != fb.directory
            from fastapi import HTTPException
            try:
                a.delete_training_task_record('same', {'id': 'B'})
                raise AssertionError('unauthorized deletion succeeded')
            except HTTPException as exc:
                assert exc.status_code == 403
            assert not a.runtime.tombstones
            a.delete_training_task_record('same', {'id': 'A'})
            assert not a.training_task_path('same').exists()
            assert a.runtime.tombstones['same']['delete_tombstone']
            assert b.training_task_path('same').exists() and not b.runtime.tombstones
            entered, release, completed = threading.Event(), threading.Event(), threading.Event()
            def prepare(launch):
                launch(lambda wrap: threading.Thread(target=wrap(lambda: (entered.set(), release.wait(5)))),
                       lambda thread: a.runtime.threads.update(blocked=thread))
            a.runtime.submit(prepare)
            assert entered.wait(3)
            assert a.runtime.close(0) is False
            b.runtime.submit(lambda launch: launch(lambda wrap: threading.Thread(target=wrap(completed.set)),
                                                  lambda thread: b.runtime.threads.update(done=thread)))
            assert completed.wait(3) and b.runtime.close(3)
            try:
                a.runtime.submit(lambda launch: None)
                raise AssertionError('closed runtime accepted new work')
            except TrainingRuntimeClosed:
                pass
            release.set()
            assert a.runtime.close(3)

if __name__=="__main__": unittest.main()
