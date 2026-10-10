"""Task mutation contracts with in-memory repositories and lock/error traces."""
import ast
from contextlib import contextmanager
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_PIPELINE_TASK_MUTATIONS_BASELINE_SOURCE')
NAMES=('save_pipeline_task_batch_changes','mark_pipeline_ai_task_deleted','mark_pipeline_task_advancing','persist_pipeline_task_progress')
ORIGINAL_DOCSTRINGS={'mark_pipeline_task_advancing': 'Flag a task (in memory) as queued for the async advance runner. The caller\n    persists it and then schedules the worker after releasing _pipeline_tasks_lock.', 'persist_pipeline_task_progress': 'Write live sub-step progress to the stored task record so the UI reflects\n    an in-flight advance immediately. Safe to call from the advance worker thread\n    (it briefly takes _pipeline_tasks_lock); never call while already holding it.'}

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
        ns=dict(bindings,Any=Any,time=time);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.pipeline.task_mutations import PipelineTaskMutations
    from local_inspection_service.pipeline.task_mutations_ports import MutationStorage,MutationAccess
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineTaskMutations(ports(MutationStorage),ports(MutationAccess));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class MutationsContract(unittest.TestCase):
    def fixture(self):
        events=[];holder={'locked':False};tasks=[{'id':'p','ai_task_id':'a','owner_user_id':'u'},{'id':'other','ai_task_id':'a','owner_user_id':'other'}]
        @contextmanager
        def lock():
            self.assertFalse(holder['locked']);holder['locked']=True;events.append('lock')
            try:yield
            finally:holder['locked']=False;events.append('unlock')
        b={'runtime_postgres_repository_or_none':lambda:object(),'save_pipeline_task':lambda t:events.append(('save',t)),
           'save_pipeline_tasks':lambda ts:events.append(('save_all',ts)),'_pipeline_tasks_lock':lock(),'load_pipeline_tasks':lambda:tasks,'load_pipeline_task':lambda i:tasks[0] if i=='p' else None,
           'sanitize_ai_detection_task_id':lambda i:str(i or '').strip(),'record_mutable_by_user':lambda t,u:t['owner_user_id']==u['id']}
        service,b=create(b);return SimpleNamespace(s=service,b=b,events=events,holder=holder,tasks=tasks)

    def test_batch_empty_postgres_identity_and_file_fallback(self):
        f=self.fixture();f.b['runtime_postgres_repository_or_none']=Mock(side_effect=AssertionError('unexpected'));f.s.save_pipeline_task_batch_changes(f.tasks,[]);f.b['runtime_postgres_repository_or_none'].assert_not_called()
        for pg in (False,True):
            f=self.fixture();f.b['runtime_postgres_repository_or_none']=lambda:object() if pg else None;f.s.save_pipeline_task_batch_changes(f.tasks,[f.tasks[1],f.tasks[0]])
            if pg:self.assertEqual([e[1] for e in f.events],[f.tasks[1],f.tasks[0]])
            else:self.assertEqual(f.events,[('save_all',f.tasks)]);self.assertIs(f.events[0][1],f.tasks)

    def test_batch_second_save_failure_no_full_fallback(self):
        f=self.fixture();saved=[]
        def save(t):
            if saved:raise RuntimeError('second')
            saved.append(t)
        f.b['save_pipeline_task']=save;f.b['save_pipeline_tasks']=Mock(side_effect=AssertionError('unexpected'))
        with self.assertRaisesRegex(RuntimeError,'second'):f.s.save_pipeline_task_batch_changes(f.tasks,f.tasks)
        self.assertIs(saved[0],f.tasks[0]);f.b['save_pipeline_tasks'].assert_not_called()

    def test_delete_permissions_matching_and_clock_before_lock(self):
        f=self.fixture();f.tasks.append({'id':'unrelated','ai_task_id':'z'});permission=Mock(side_effect=lambda t,u:t.get('owner_user_id')==u['id']);f.b['record_mutable_by_user']=permission
        with patch.object(time,'time',return_value=19):self.assertEqual(f.s.mark_pipeline_ai_task_deleted(' a ',{'id':'u'}),1)
        self.assertEqual(permission.call_count,2);self.assertEqual(f.tasks[0]['model_deleted_at'],19);self.assertFalse(f.tasks[0]['model_exists']);self.assertEqual(f.tasks[0]['model_status'],'deleted');self.assertNotIn('model_status',f.tasks[1]);self.assertEqual(f.events[0],'lock');self.assertEqual(f.events[-1],'unlock')
        f=self.fixture()
        with patch.object(time,'time',side_effect=RuntimeError('clock')):
            self.assertEqual(f.s.mark_pipeline_ai_task_deleted('',{'id':'u'}),0)
            with self.assertRaisesRegex(RuntimeError,'clock'):f.s.mark_pipeline_ai_task_deleted('a',{'id':'u'})
        self.assertEqual(f.events,[])

    def test_delete_permission_failure_keeps_prior_in_memory_change(self):
        f=self.fixture();f.b['record_mutable_by_user']=Mock(side_effect=[True,RuntimeError('permission')])
        with patch.object(time,'time',return_value=5):
            with self.assertRaisesRegex(RuntimeError,'permission'):f.s.mark_pipeline_ai_task_deleted('a',{'id':'u'})
        self.assertEqual(f.tasks[0]['model_status'],'deleted');self.assertEqual(f.events,['lock','unlock']);self.assertFalse(f.holder['locked'])

    def test_advancing_two_clocks_partial_order(self):
        f=self.fixture();task={}
        with patch.object(time,'time',side_effect=[4.9,8.1]):f.s.mark_pipeline_task_advancing(task)
        self.assertEqual(task,{'advancing':True,'advance_started_at':4,'last_error':'','job_note':'正在推进…','updated_at':8})
        for readings,expected in [([RuntimeError('first')],{'advancing':True}),([4,RuntimeError('second')],{'advancing':True,'advance_started_at':4,'last_error':'','job_note':'正在推进…'})]:
            task={}
            with patch.object(time,'time',side_effect=readings):
                with self.assertRaises(RuntimeError):f.s.mark_pipeline_task_advancing(task)
            self.assertEqual(task,expected)

    def test_progress_noop_falsey_values_errors_and_lock_release(self):
        f=self.fixture();f.s.persist_pipeline_task_progress('');self.assertEqual(f.events,[]);f.s.persist_pipeline_task_progress('missing');self.assertEqual(f.events,['lock','unlock'])
        f=self.fixture()
        with patch.object(time,'time',return_value=8):f.s.persist_pipeline_task_progress('p',job_note='',progress=0,status='')
        self.assertEqual((f.tasks[0]['job_note'],f.tasks[0]['progress'],f.tasks[0]['status'],f.tasks[0]['updated_at']),('',0,'',8));self.assertIs(f.events[1][1],f.tasks[0]);self.assertEqual(f.events[-1],'unlock')
        f=self.fixture()
        with self.assertRaises(ValueError):f.s.persist_pipeline_task_progress('p',job_note='first',progress='bad',status='later')
        self.assertEqual(f.tasks[0]['job_note'],'first');self.assertNotIn('status',f.tasks[0]);self.assertEqual(f.events,['lock','unlock'])

    def test_late_saver_and_batch_binding(self):
        f=self.fixture()
        def load(i):f.b['save_pipeline_task']=lambda t:f.events.append(('new_save',t));return f.tasks[0]
        f.b['load_pipeline_task']=load
        with patch.object(time,'time',return_value=8):f.s.persist_pipeline_task_progress('p')
        self.assertEqual(f.events[1][0],'new_save')
        f=self.fixture()
        def permission(t,u):f.b['save_pipeline_task_batch_changes']=lambda ts,changed:f.events.append(('new_batch',changed));return True
        f.b['record_mutable_by_user']=permission
        with patch.object(time,'time',return_value=8):self.assertEqual(f.s.mark_pipeline_ai_task_deleted('a',{}),2)
        self.assertEqual(f.events[1][0],'new_batch');self.assertFalse(f.holder['locked'])

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_light_import(self):
        from application_integration_source_contract import restore_plc_domain_root
        tree=ast.parse(restore_plc_domain_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pipeline_task_mutations' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,9)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);body=node.body[1:] if ast.get_docstring(node,clean=False) is not None else node.body;self.assertEqual(len(body),1);self.assertIsInstance(body[0],ast.Return);self.assertEqual(body[0].value.func.attr,name)
            self.assertEqual(ast.get_docstring(node,clean=False),ORIGINAL_DOCSTRINGS.get(name))
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.pipeline.task_mutations; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
