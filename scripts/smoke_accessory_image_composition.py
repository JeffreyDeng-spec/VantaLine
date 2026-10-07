"""Independent image owners exercise the actual queue, storage and native drain."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.accessories import image_composition as composition
from local_inspection_service.accessories.image_job_metadata import ProvenanceDependencies
from local_inspection_service.accessories.image_worker_diagnostic_ports import ImageDiagnosticPolicy


def poison(*args,**kwargs):raise AssertionError('constructor contacted an external capability')


def ports(cls,**overrides):
    return cls(**{field.name:overrides.get(field.name,poison) for field in fields(cls)})


def inert(**overrides):
    values=dict(provenance=ports(ProvenanceDependencies),resolver=poison,files=object(),
        threads=poison,scope=poison,candidates=ports(composition.CandidateFiles),
        storage=ports(composition.QueueStorage),metadata=ports(composition.QueueMetadata),
        limits=ports(composition.QueueLimits),diagnostic_media=ports(composition.DiagnosticMedia),
        diagnostic_policy=ports(ImageDiagnosticPolicy),execution_files=ports(composition.ExecutionFiles),
        evidence=ports(composition.ExecutionEvidence),providers=ports(composition.ExecutionProviders))
    values.update(overrides)
    return composition.ImageJobs(**values)


class Resolver:
    def __init__(self):self.binding=ContextVar('synthetic_image_binding',default=None)
    def current_snapshot(self):return self.binding.get()
    def snapshot_for_record(self,record):return {'version':'synthetic-current'}
    @contextmanager
    def scope(self,snapshot):
        token=self.binding.set(snapshot)
        try:yield
        finally:self.binding.reset(token)


def fixture(root):
    root.mkdir();scopes=[];resolver=Resolver()
    @contextmanager
    def scope():
        identity=threading.get_ident();scopes.append(('enter',identity))
        try:yield
        finally:scopes.append(('exit',identity))
    files=SimpleNamespace(exists=lambda path:path.exists(),read_text=lambda path,**kw:path.read_text(**kw),stat=lambda path:path.stat())
    owner=inert(provenance=ports(ProvenanceDependencies,guide_images=lambda:{}),resolver=lambda:resolver,files=files,threads=lambda:threading.Thread,scope=scope,
        candidates=ports(composition.CandidateFiles,runtime_repository=lambda:None,directory=lambda:root,
            safe_id=lambda value:str(value),created_at=lambda record,path:0,updated_at=lambda record,path:0),
        storage=ports(composition.QueueStorage,CONFIG_PATH=lambda:root/'config.json',load_config=lambda:lambda:{'accessories':[]},
            runtime_postgres_repository_or_none=lambda:lambda:None,_business_files=lambda:files),
        metadata=ports(composition.QueueMetadata,public_output_url=lambda:lambda path:'/synthetic/'+path.name,
            resolve_service_path=lambda:lambda value,**kwargs:Path(value)),
        limits=ports(composition.QueueLimits,IMAGE_JOB_QUEUED_STATUSES=lambda:{'queued'},MAX_PARALLEL_IMAGE_WORKERS=lambda:2),
        diagnostic_media=ports(composition.DiagnosticMedia,resolve_service_path=lambda:lambda value,**kwargs:Path(value)),
        providers=ports(composition.ExecutionProviders,LOCAL_CODEX_IMAGE_PROVIDER=lambda:'codex',
            CURSOR_IMAGE2_PROVIDER=lambda:'cursor',CURSOR_IMAGE2_QUEUE_STATUS=lambda:'cursor_queued',
            CODEX_IMAGE_WORKER_QUEUE_STATUS=lambda:'codex_queued'))
    path=root/'candidate.json'
    job={'job_id':'same-job','task_id':'same-task','candidate_id':'same-candidate','status':'queued',
         'output_path':str(root/'output.png'),'model_profiles':{'version':root.name}}
    candidate={'id':'same-candidate','codex_image_jobs':[job],'codex_image_job':job}
    owner.candidates.save_accessory_candidate(path,candidate)
    return owner,resolver,path,scopes


class ImageComposition(unittest.TestCase):
    def test_constructor_inert_and_internal_edges_owned(self):
        a,b=inert(),inert()
        self.assertIsNot(a.lock,b.lock);self.assertIsNot(a.worker.processes,b.worker.processes)
        self.assertIs(a.worker.target().__self__,a.queue)
        self.assertIs(a.queue.execution.next_queued_image_job().__self__,a.queue)
        self.assertIs(a.queue.storage.load_accessory_candidate().__self__,a.candidates)
        self.assertIs(a.queue.metadata.store_candidate_image_job().__self__,a.metadata)
        self.assertIs(a.execution.providers.run_codex_image_job().__self__,a.execution)
        self.assertIs(a.diagnostics.runtime._image_worker_processes(),a.worker.processes)

    def test_missing_resolver_fails_before_execution(self):
        owner=inert(resolver=lambda:None);called=Mock();object.__setattr__(owner.execution.providers,'run_codex_image_job',lambda:called)
        with self.assertRaises(RuntimeError):owner.run_image_generation_job(Path('synthetic'),{}, {})
        called.assert_not_called()

    def test_native_thread_constructor_failure_never_looks_up_queue(self):
        def failed_factory(**kwargs):raise RuntimeError('synthetic thread construction failure')
        owner=inert(threads=lambda:failed_factory)
        with self.assertRaisesRegex(RuntimeError,'thread construction'):owner.worker.start()
        self.assertTrue(owner.worker.close(0))
        self.assertFalse(owner.worker.start())

    def test_final_save_failure_releases_scopes_and_does_not_repeat_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            owner,resolver,path,scopes=fixture(Path(temp)/'alice')
            reached=threading.Event();errors=[];calls=[]
            save=owner.candidates.save_accessory_candidate
            def failed_save(target,candidate):
                if candidate['codex_image_job']['status']=='completed':raise RuntimeError('synthetic final save failure')
                return save(target,candidate)
            owner.candidates.save_accessory_candidate=failed_save
            def run(target,candidate,job):
                calls.append(resolver.current_snapshot())
                try:owner.queue.update_image_worker_status(target,candidate,job,status='completed')
                finally:reached.set()
            object.__setattr__(owner.execution.providers,'run_codex_image_job',lambda:run)
            with patch.object(threading,'excepthook',lambda args:errors.append(args.exc_value)):
                self.assertTrue(owner.worker.start());self.assertTrue(reached.wait(3))
                self.assertTrue(owner.worker.close(3))
            self.assertEqual(calls,[{'version':'alice'}])
            self.assertEqual([str(error) for error in errors],['synthetic final save failure'])
            self.assertEqual(json.loads(path.read_text())['codex_image_job']['status'],'running')
            self.assertEqual(sorted(t for op,t in scopes if op=='enter'),sorted(t for op,t in scopes if op=='exit'))
            self.assertIsNone(resolver.current_snapshot())
            self.assertFalse(owner.worker.start())

    def test_native_fanout_model_binding_and_close_leave_other_owner_operational(self):
        with tempfile.TemporaryDirectory() as temp:
            a,ar,ap,ascopes=fixture(Path(temp)/'alice')
            b,br,bp,bscopes=fixture(Path(temp)/'bob')
            reached=threading.Event();release=threading.Event();seen=[]
            def run_a(path,candidate,job):
                seen.append(('alice',ar.current_snapshot(),threading.get_ident()))
                reached.set();self.assertTrue(release.wait(3))
                a.queue.update_image_worker_status(path,candidate,job,status='completed')
            object.__setattr__(a.execution.providers,'run_codex_image_job',lambda:run_a)
            self.assertTrue(a.worker.start());self.assertTrue(reached.wait(3))
            self.assertFalse(a.worker.close(0));self.assertFalse(a.worker.start())
            release.set();self.assertTrue(a.worker.close(3))
            self.assertFalse(b.worker.closing)
            bob_reached=threading.Event()
            def run_b(path,candidate,job):
                seen.append(('bob',br.current_snapshot(),threading.get_ident()))
                b.queue.update_image_worker_status(path,candidate,job,status='completed')
                bob_reached.set()
            object.__setattr__(b.execution.providers,'run_codex_image_job',lambda:run_b)
            self.assertTrue(b.worker.start());self.assertTrue(bob_reached.wait(3));self.assertTrue(b.worker.close(3))
            self.assertEqual([row[:2] for row in seen],[('alice',{'version':'alice'}),('bob',{'version':'bob'})])
            self.assertTrue(all(row[2]!=threading.get_ident() for row in seen))
            self.assertEqual(json.loads(ap.read_text())['codex_image_job']['status'],'completed')
            self.assertEqual(json.loads(bp.read_text())['codex_image_job']['status'],'completed')
            for scopes in [ascopes,bscopes]:
                self.assertEqual(sorted(t for op,t in scopes if op=='enter'),sorted(t for op,t in scopes if op=='exit'))
            self.assertIsNone(ar.current_snapshot());self.assertIsNone(br.current_snapshot())


if __name__=='__main__':unittest.main()
