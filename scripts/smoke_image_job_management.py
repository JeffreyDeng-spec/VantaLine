"""Image job state, authorization and persistence contracts without provider calls."""
import ast
import asyncio
from contextvars import ContextVar
from dataclasses import fields
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_IMAGE_JOB_MANAGEMENT_BASELINE_SOURCE')
NAMES = ('refresh_codex_image_job', 'public_image_job', 'refreshed_public_codex_jobs_for_record',
         'list_codex_image_jobs', 'apply_codex_image_job_action', 'update_codex_image_job',
         'stop_candidate_image_task', 'update_codex_image_candidate')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 8
        bindings.update(Any=Any, Path=Path, json=json, os=os, signal=signal, time=time,
                        HTTPException=HTTPException, __package__='local_inspection_service')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{n: bindings[n] for n in NAMES})
    from local_inspection_service.accessories.image_job_management import ImageJobManagement
    from local_inspection_service.accessories.image_job_management_ports import (
        ImageJobStorage, ImageJobAccess, ImageJobMetadata, ImageJobActions)
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = ImageJobManagement(ports(ImageJobStorage), ports(ImageJobAccess),
                                 ports(ImageJobMetadata), ports(ImageJobActions))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service


class ManagementContract(unittest.TestCase):
    def fixture(self):
        rows, events, existing = [], [], set()
        config = {'accessories': []}
        user = ContextVar('synthetic-image-user', default=None)
        files = SimpleNamespace(exists=lambda p: str(p) in existing,
            stat=lambda p: SimpleNamespace(st_mtime=42.8), unlink=Mock(),
            glob=Mock(return_value=[]), read_text=Mock())
        def identify(record, job):
            changed = not job.get('task_id')
            job.setdefault('task_id', 'task-' + str(job.get('job_id', 'j')))
            return changed
        def store(record, job):
            jobs = record.setdefault('codex_image_jobs', [])
            for index, old in enumerate(jobs):
                if old.get('job_id') == job.get('job_id'):
                    jobs[index] = job
                    break
            else:
                jobs.append(job)
            events.append(('store', record['id'], dict(job)))
        b = dict(_business_files=files, _candidate_store_lock=threading.RLock(),
            ACCESSORY_CANDIDATES_DIR=Path('/candidate'), _request_user=user,
            list_accessory_candidate_records=Mock(side_effect=lambda **kw: list(rows)),
            load_accessory_candidate=Mock(side_effect=HTTPException(404)),
            save_accessory_candidate=lambda p,c: events.append(('save', c['id'])),
            delete_accessory_candidate=Mock(return_value=True),
            cleanup_accessory_candidate_artifacts=Mock(return_value=['artifact']),
            runtime_postgres_repository_or_none=lambda: None,
            load_config=lambda: config, save_config=lambda c: events.append(('save_config',)),
            record_visible_to_user=lambda c,u,t: c.get('owner') == (t or u['id']),
            record_mutable_by_user=lambda c,u: c.get('owner') == u['id'],
            require_record_access=Mock(), IMAGE_JOB_ACTIVE_STATUSES={'running','queued'},
            LOCAL_CODEX_IMAGE_PROVIDER='local', WINDOWS_WORKER_IMAGE_PROVIDER='retired',
            CODEX_IMAGE_JOB_PERSISTED_KEYS=('status','progress','task_id','provider','output_path'),
            CODEX_IMAGE_WORKER_QUEUE_STATUS='queued',
            image_job_output_path=lambda j,**kw: Path('/output') / (j.get('job_id','j')+'.png'),
            image_job_log_path=lambda j: Path('/log'), public_output_url=lambda p: '/public/'+p.name,
            public_output_url_for_existing=lambda p: '/existing/'+p.name,
            classify_image_worker_failure=Mock(return_value='synthetic error'),
            running_image_job_is_stale=Mock(return_value=False), public_text=lambda v: str(v).replace('ImageWorker','worker'),
            accessory_uid=lambda c:c.get('id',''), accessory_material_type=lambda c:c.get('kind','object'),
            candidate_image_jobs=lambda c:c.get('codex_image_jobs',[]),
            deterministic_task_id=lambda c,j:'task-'+c['id'],
            ensure_candidate_image_job_task_ids=lambda c:False, ensure_image_job_task_id=identify,
            ensure_pose_collection_image_jobs=Mock(return_value=False), store_candidate_image_job=store,
            image_job_matches=lambda c,j,k:k in (j.get('job_id'),j.get('task_id')),
            record_created_at=lambda c,p:c.get('created_at'), record_updated_at=lambda c,p:c.get('updated_at'),
            record_owner_id=lambda c:c.get('owner'), record_owner_username=lambda c:c.get('username'),
            enrich_record_audit_fields=lambda c,p:c, _image_worker_processes={},
            start_image_worker=lambda:events.append(('start',)))
        return create(b), b, rows, config, events, existing

    def test_refresh_terminal_and_missing_error_classification(self):
        s,b,_,_,_,existing=self.fixture(); job={'job_id':'j','status':'stopped','progress':'8'}
        existing.add(str(Path('/output/j.png')))
        result=s.refresh_codex_image_job(job)
        self.assertEqual(result['status'],'stopped');self.assertEqual(result['progress'],8)
        self.assertNotIn('output_url',job);b['classify_image_worker_failure'].assert_not_called()
        existing.clear();job['status']='failed';job['error']='old'
        b['classify_image_worker_failure'].return_value='FORBIDDEN limited'
        result=s.refresh_codex_image_job(job)
        self.assertEqual(result['error'],'FORBIDDEN limited');self.assertEqual(result['log_path'],str(Path('/log')))

    def test_refresh_completed_stale_and_progress(self):
        s,b,_,_,_,existing=self.fixture();job={'job_id':'j','status':'running','started_at':1,'generation_method':'codex_exec_image_worker','provider':'retired'}
        with patch.object(time,'time',return_value=1000):
            result=s.refresh_codex_image_job(job)
            self.assertEqual(result['progress'],95);self.assertEqual(result['provider'],'local')
            b['running_image_job_is_stale'].return_value=True
            result=s.refresh_codex_image_job(job)
            self.assertEqual((result['status'],result['failed_at']),('failed',1000))
            existing.add(str(Path('/output/j.png')))
            result=s.refresh_codex_image_job(job)
            self.assertEqual((result['status'],result['completed_at']),('completed',42))
        self.assertEqual(job['status'],'running')

    def test_public_snapshot_and_text_projection(self):
        s,*_=self.fixture()
        from local_inspection_service.model_profiles.snapshots import public_record
        job={'note':'Generated by local provider','label':'ImageWorker','status':'queued'}
        result=s.public_image_job(job)
        self.assertEqual(result['note'],'本地生成任务已完成。');self.assertEqual(result['label'],'worker')
        self.assertEqual(job['note'],'Generated by local provider')
        expected=public_record(job);expected.update(note='本地生成任务已完成。',label='worker')
        self.assertEqual(result,expected)

    def test_list_order_visibility_and_persistence(self):
        s,b,rows,config,events,_=self.fixture()
        def record(i,owner):return {'id':i,'owner':owner,'codex_image_jobs':[{'job_id':i,'status':'queued'}]}
        rows.extend([(Path('/a'),record('a','u')),(Path('/b'),record('b','v'))])
        config['accessories']=[None,record('c','u'),record('d','v')]
        result=s.list_codex_image_jobs({'id':'u'})
        self.assertEqual([j['candidate_id'] for j in result],['a','c'])
        self.assertEqual([j['job_store'] for j in result],['candidate','config'])
        self.assertEqual([e[0] for e in events],['store','save','store','save_config'])
        b['list_accessory_candidate_records'].assert_called_once_with(reverse=True)

    def test_retry_active_refusal_and_explicit_failed_requeue(self):
        s,b,_,_,events,existing=self.fixture();j={'job_id':'j','status':'running'};r={'id':'a','codex_image_jobs':[j]}
        with self.assertRaises(HTTPException) as error:s.apply_codex_image_job_action(r,j,'j','retry')
        self.assertEqual(error.exception.status_code,409);self.assertEqual(events,[])
        j.update(status='failed',failed_at=3,completed_at=4,return_code=9,error='old')
        existing.add(str(Path('/output/j.png')));b['_business_files'].unlink.side_effect=OSError('synthetic')
        result=s.apply_codex_image_job_action(r,j,'j','retry')
        self.assertEqual(result['status'],'retry');self.assertEqual(j['status'],'queued')
        self.assertEqual(j['provider'],'local');self.assertNotIn('failed_at',j);self.assertNotIn('error',j)
        self.assertEqual(events[-1][0],'store')

    def test_stop_and_delete_keep_existing_process_semantics(self):
        s,b,_,_,events,_=self.fixture();j={'job_id':'j','status':'queued'};r={'id':'a','codex_image_jobs':[j]}
        process=SimpleNamespace(pid=8,poll=lambda:None);b['_image_worker_processes']['j']=process
        with patch.object(os,'killpg',create=True) as kill:
            s.apply_codex_image_job_action(r,j,'j','stop');kill.assert_called_once_with(8,signal.SIGTERM)
        self.assertEqual(j['status'],'stopped')
        with patch.object(os,'killpg',create=True) as kill:
            s.apply_codex_image_job_action(r,j,'j','delete');kill.assert_not_called()
        self.assertEqual(r['codex_image_jobs'],[]);self.assertFalse(r['ai_generation_required'])

    def test_candidate_stop_counts_process_and_state_separately(self):
        s,b,_,_,_,_=self.fixture();j={'job_id':'j','status':'running'};r={'id':'a','codex_image_jobs':[j]}
        b['_image_worker_processes']['j']=SimpleNamespace(pid=9,poll=lambda:None)
        with patch.object(os,'killpg',create=True):self.assertEqual(s.stop_candidate_image_task(r),2)
        self.assertEqual(j['status'],'stopped')
        with patch.object(os,'killpg',side_effect=ProcessLookupError,create=True):self.assertEqual(s.stop_candidate_image_task(r),0)

    def test_update_saves_before_start_and_save_failure_prevents_start(self):
        s,b,rows,_,events,_=self.fixture();j={'job_id':'j','status':'failed'};r={'id':'a','codex_image_jobs':[j]};rows.append((Path('/a'),r))
        s.update_codex_image_job('j','retry');self.assertEqual([e[0] for e in events],['store','save','start'])
        j['status']='failed';events.clear();b['save_accessory_candidate']=Mock(side_effect=OSError('store failed'))
        with self.assertRaises(OSError):s.update_codex_image_job('j','retry')
        self.assertEqual([e[0] for e in events],['store'])

    def test_request_identity_follows_async_thread_context(self):
        s,b,rows,_,events,_=self.fixture()
        for owner in ('u','v'):
            rows.append((Path('/'+owner),{'id':owner,'owner':owner,'codex_image_jobs':[{'job_id':owner,'status':'queued'}]}))
        async def request(owner):
            token=b['_request_user'].set({'id':owner})
            try:
                with self.assertRaises(HTTPException) as error:
                    await asyncio.to_thread(s.update_codex_image_job,'v' if owner=='u' else 'u','stop')
                self.assertEqual(error.exception.status_code,404)
                return await asyncio.to_thread(s.update_codex_image_job,owner,'stop')
            finally:b['_request_user'].reset(token)
        async def concurrent():return await asyncio.gather(request('u'),request('v'))
        self.assertEqual([r['candidate_id'] for r in asyncio.run(concurrent())],['u','v'])
        self.assertIsNone(b['_request_user'].get())

    def test_falsey_postgres_authority_never_reads_json(self):
        s,b,_,_,_,_=self.fixture();b['runtime_postgres_repository_or_none']=lambda:False
        with self.assertRaises(HTTPException) as error:s.update_codex_image_candidate('a','delete')
        self.assertEqual(error.exception.status_code,404);b['_business_files'].glob.assert_not_called()
        b['load_accessory_candidate'].side_effect=HTTPException(503)
        with self.assertRaises(HTTPException) as error:s.update_codex_image_candidate('a','delete')
        self.assertEqual(error.exception.status_code,503)

    def test_candidate_permission_and_partial_cleanup_evidence(self):
        s,b,_,_,_,_=self.fixture();b['runtime_postgres_repository_or_none']=lambda:False
        candidate={'id':'a','codex_image_jobs':[]};b['load_accessory_candidate']=lambda i:candidate
        b['_request_user'].set({'id':'u'});denial=HTTPException(403)
        b['require_record_access'].side_effect=denial
        with self.assertRaises(HTTPException) as error:s.update_codex_image_candidate('a','delete')
        self.assertIs(error.exception,denial);b['delete_accessory_candidate'].assert_not_called()
        b['require_record_access'].side_effect=None;b['cleanup_accessory_candidate_artifacts'].side_effect=OSError('partial')
        result=s.update_codex_image_candidate('a','delete')
        self.assertEqual(result['artifact_cleanup_error'],'partial');self.assertEqual(result['deleted_artifacts'],[])
        b['require_record_access'].assert_called_with(candidate,{'id':'u'},write=True)

    def test_json_decode_skip_delete_error_and_config_fallback(self):
        s,b,_,config,events,_=self.fixture();b['_business_files'].glob.return_value=[Path('/bad'),Path('/a')]
        b['_business_files'].read_text.side_effect=['{bad',json.dumps({'id':'a'})]
        b['delete_accessory_candidate'].side_effect=OSError('failure')
        with self.assertRaises(HTTPException) as error:s.update_codex_image_candidate('a','delete')
        self.assertEqual(error.exception.status_code,500)
        b['_business_files'].glob.return_value=[];item={'id':'c','ai_generation_required':True};config['accessories']=[item]
        result=s.update_codex_image_candidate('c','delete')
        self.assertEqual(result,{'status':'deleted','candidate_id':'c','stopped':0})
        self.assertFalse(item['ai_generation_required']);self.assertEqual(events,[('save_config',)])
        b['cleanup_accessory_candidate_artifacts'].assert_not_called()

    @unittest.skipIf(BASELINE,'Original entry has no extracted assembly')
    def test_root_forwarding_and_all_late_getters(self):
        tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'))
        assembly=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_image_job_management' for t in n.targets))
        for group in assembly.value.keywords:
            for field in group.value.keywords:
                self.assertIsInstance(field.value,ast.Lambda);self.assertEqual(field.value.body.id,field.arg)
        from local_inspection_service.accessories.image_job_management import ImageJobManagement
        s,b,*_=self.fixture();other,c,*_=self.fixture()
        self.assertIsNot(s.access._request_user(),other.access._request_user())
        for name in NAMES:
            function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.unparse(function.body[0].value.func),'_image_job_management.'+name)
        self.assertIsInstance(s,ImageJobManagement)


if __name__=='__main__':unittest.main(verbosity=2)
