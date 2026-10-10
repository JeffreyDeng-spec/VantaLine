"""Synthetic queue persistence and thread scheduling; never runs image providers."""
import ast
from dataclasses import fields
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_IMAGE_JOB_QUEUE_BASELINE_SOURCE')
NAMES=('mutate_candidate_image_job','next_queued_image_job','image_worker_loop')


def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
        assert len(nodes)==3
        bindings.update(Any=Any,Path=Path,json=json,threading=threading,time=time)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),bindings)
        return SimpleNamespace(**{n:bindings[n] for n in NAMES})
    from local_inspection_service.accessories.image_job_queue import ImageJobQueue
    from local_inspection_service.accessories.image_job_queue_ports import ImageQueueStorage,ImageQueueMetadata,ImageQueueExecution
    from local_inspection_service.runtime.image_worker import ImageWorkerRuntime
    bindings['_image_worker_runtime'] = ImageWorkerRuntime(target=lambda: lambda: None, threads=lambda: threading.Thread)
    # Preserve the existing deterministic sleep seam; no real worker is launched.
    bindings['_image_worker_runtime'].wait = lambda seconds: time.sleep(seconds)
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=ImageJobQueue(ports(ImageQueueStorage),ports(ImageQueueMetadata),ports(ImageQueueExecution))
    bindings.update({name:getattr(service,name) for name in NAMES})
    return service


class QueueContract(unittest.TestCase):
    def fixture(self):
        config={'accessories':[]};records=[];existing=set();events=[]
        files=SimpleNamespace(exists=lambda p:str(p) in existing,read_text=Mock(return_value='{}'),stat=lambda p:SimpleNamespace(st_mtime=101.7))
        def identify(candidate,job):
            changed=not job.get('task_id')
            job['task_id']=job.get('task_id') or 'task'
            return changed
        b=dict(_candidate_store_lock=threading.RLock(),CONFIG_PATH=Path('/config.json'),load_config=Mock(return_value=config),
            save_config=lambda c:events.append(('save_config',c)),runtime_postgres_repository_or_none=lambda:None,
            load_accessory_candidate=Mock(),save_accessory_candidate=lambda p,c:events.append(('save',p,c)),
            list_accessory_candidate_records=Mock(side_effect=lambda **kw:list(records)),_business_files=files,HTTPException=HTTPException,
            ensure_image_job_task_id=identify,ensure_candidate_image_job_task_ids=lambda c:None,
            candidate_image_jobs=lambda c:c.get('jobs',[]),store_candidate_image_job=lambda c,j:events.append(('store',c,j)),
            accessory_uid=lambda c:c['id'],file_stem_identifier=lambda p:p.stem,accessory_material_type=lambda c:c.get('kind','object'),
            ensure_pose_collection_image_jobs=Mock(return_value=False),image_job_output_path=lambda j,**kw:Path('/out/'+j['job_id']+'.png'),
            public_output_url=lambda p:'/public'+str(p),resolve_service_path=Path,
            preprocess_object_clean_sprites=lambda c,**kw:events.append(('preprocess',c,kw)),
            IMAGE_JOB_QUEUED_STATUSES={'queued'},MAX_PARALLEL_IMAGE_WORKERS=2,update_image_worker_status=Mock(),
            run_image_generation_job=Mock(side_effect=AssertionError('Provider must not run')))
        return create(b),b,config,records,existing,events

    def test_config_stopped_job_cannot_be_overwritten(self):
        q,b,config,_,_,events=self.fixture();job={'job_id':'j','status':'stopped'};latest={'id':'a','jobs':[job]};config['accessories']=[latest]
        caller={'job_id':'j','status':'queued'}
        result=q.mutate_candidate_image_job(b['CONFIG_PATH'],{'id':'a'},caller,{'status':'completed'},preprocess_clean_sprites=True)
        self.assertIs(result,job);self.assertEqual(job['status'],'stopped');self.assertEqual(events,[])
        result=q.mutate_candidate_image_job(b['CONFIG_PATH'],{'id':'a'},caller,{'status':'stopped','note':'kept'})
        self.assertIs(result,job);self.assertEqual([e[0] for e in events],['store','save_config'])

    def test_falsey_repository_404_fallback_and_other_error(self):
        q,b,_,_,_,events=self.fixture()
        class Repository:
            def __bool__(self):return False
        b['runtime_postgres_repository_or_none']=lambda:Repository()
        candidate={'id':'a','jobs':[]};job={'job_id':'j'}
        b['load_accessory_candidate'].side_effect=HTTPException(404)
        result=q.mutate_candidate_image_job(Path('/a.json'),candidate,job,{'status':'running'},preprocess_clean_sprites=True)
        self.assertIsNot(result,job);self.assertEqual(result['status'],'running')
        self.assertEqual([e[0] for e in events],['store','preprocess','save'])
        b['_business_files'].read_text.assert_not_called()
        failure=HTTPException(403);b['load_accessory_candidate'].side_effect=failure
        with self.assertRaises(HTTPException) as raised:q.mutate_candidate_image_job(Path('/a.json'),candidate,job,{})
        self.assertIs(raised.exception,failure);self.assertEqual(len(events),3)

    def test_json_missing_and_decode_fallback(self):
        q,b,_,_,existing,events=self.fixture();job={'job_id':'j'};candidate={'id':'a','jobs':[]};path=Path('/a.json')
        self.assertIs(q.mutate_candidate_image_job(path,candidate,job,{'status':'running'}),job)
        self.assertEqual(events,[])
        existing.add(str(path));b['_business_files'].read_text.return_value='{bad'
        result=q.mutate_candidate_image_job(path,candidate,job,{'status':'running'})
        self.assertEqual(result['status'],'running');self.assertIs(events[-1][2],candidate)

    def test_candidate_order_dependencies_and_existing_output(self):
        q,b,_,records,existing,events=self.fixture()
        waiting={'job_id':'waiting','status':'queued','depends_on_output_path':'/missing'}
        complete={'job_id':'complete','status':'queued'};selected={'job_id':'selected','status':'queued'}
        first={'id':'first','jobs':[waiting,complete]};second={'id':'second','jobs':[selected]}
        records.extend([(Path('/first.json'),first),(Path('/second.json'),second)]);existing.add(str(Path('/out/complete.png')))
        path,candidate,job=q.next_queued_image_job()
        self.assertEqual(path,Path('/second.json'));self.assertIs(candidate,second);self.assertIs(job,selected)
        self.assertEqual(complete['status'],'completed');self.assertEqual(complete['completed_at'],101)
        self.assertEqual(complete['progress'],100);self.assertEqual(waiting['status'],'queued')
        b['list_accessory_candidate_records'].assert_called_once_with(reverse=False);b['load_config'].assert_not_called()
        self.assertEqual([e[0] for e in events],['store','save','store','store','preprocess','save','store','save'])

    def test_config_queue_skips_text_and_saves_before_return(self):
        q,b,config,_,_,events=self.fixture();job={'job_id':'j','status':'queued'};candidate={'id':'a','jobs':[job]}
        config['accessories']=[None,{'id':'text','kind':'text','jobs':[{'job_id':'text','status':'queued'}]},candidate]
        result=q.next_queued_image_job();self.assertEqual(result[0],b['CONFIG_PATH']);self.assertIs(result[1],candidate);self.assertIs(result[2],job)
        b['ensure_pose_collection_image_jobs'].assert_called_once_with(candidate)
        self.assertEqual(events[-1][0],'save_config');self.assertEqual(job['output_url'],'/public'+str(Path('/out/j.png')))

    def test_worker_persists_running_before_bounded_launch(self):
        q,b,_,_,_,_=self.fixture();trace=[];threads=[]
        jobs=[(Path('/a'),{'id':'a'},{'job_id':str(i),'progress':i}) for i in range(3)]
        pending=list(jobs)
        b['next_queued_image_job']=lambda:pending.pop(0) if pending else None
        b['update_image_worker_status']=lambda *args,**kw:trace.append(('status',args,kw))
        class Thread:
            def __init__(self,**kw):self.kw=kw;self.alive=False;threads.append(self);trace.append(('construct',kw))
            def start(self):self.alive=True;trace.append(('start',(self.kw['args'][2]['job_id'] if BASELINE else self.kw['name'].removeprefix('image-generation-worker-'))))
            def is_alive(self):return self.alive
        def sleep(seconds):
            self.assertEqual(seconds,2);self.assertLessEqual(sum(t.alive for t in threads),2)
            trace.append(('sleep',))
            for t in threads:t.alive=False
        with patch.object(threading,'Thread',Thread),patch.object(time,'time',return_value=100),patch.object(time,'sleep',sleep):q.image_worker_loop()
        self.assertEqual([e[0] for e in trace],['status','construct','start','status','construct','start','sleep','status','construct','start','sleep'])
        for index,t in enumerate(threads):
            self.assertTrue(t.kw['daemon'])
            if BASELINE:
                self.assertIs(t.kw['target'],b['run_image_generation_job']);self.assertEqual(t.kw['args'],jobs[index])
            else:
                self.assertTrue(callable(t.kw['target']))
                b['run_image_generation_job'].side_effect=None
                t.kw['target']()
                b['run_image_generation_job'].assert_called_once_with(*jobs[index])
                b['run_image_generation_job'].reset_mock()
        self.assertEqual([e[2]['progress'] for e in trace if e[0]=='status'],[12,12,12])
        b['run_image_generation_job'].assert_not_called()

    def test_status_failure_prevents_thread_creation(self):
        q,b,_,_,_,_=self.fixture();b['next_queued_image_job']=lambda:(Path('/a'),{}, {'job_id':'j'})
        error=RuntimeError('synthetic');b['update_image_worker_status'].side_effect=error
        with patch.object(threading,'Thread') as thread:
            with self.assertRaises(RuntimeError) as raised:q.image_worker_loop()
            self.assertIs(raised.exception,error);thread.assert_not_called()

    @unittest.skipIf(BASELINE,'Original entry has no extracted queue assembly')
    def test_root_ports_and_forwarding(self):
        with tempfile.TemporaryDirectory(prefix='vantaline-image-queue-') as tmp:
            (Path(tmp)/'local_inspection_service/static').mkdir(parents=True)
            with patch.dict(os.environ,{'LOCAL_INSPECTION_ROOT':tmp,'VANTALINE_DATA_STORE':'json','VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0','INSPECTION_WORKER_WATCHER':'0','VANTALINE_YOLO_PREWARM':'0'}):
                from local_inspection_service import server
                from accessory_image_test_ports import queue_target, replace_queue_port, assert_queue_relay
                service=server._image_job_queue
                for group in ('storage','metadata','execution'):
                    ports=getattr(service,group)
                    for f in fields(ports):
                        getter=getattr(ports,f.name)
                        if assert_queue_relay(self,server,f.name,getter):continue
                        target,attribute=queue_target(server,f.name);original=getattr(target,attribute);self.assertEqual(getter(),original)
                        with replace_queue_port(server,f.name,object()) as replacement:self.assertIs(getter(),replacement)
                        self.assertEqual(getter(),original)
                for name in NAMES:
                    args=(Path('/a'),{},{},{}) if name.startswith('mutate') else ()
                    kwargs={'preprocess_clean_sprites':True} if args else {}
                    with patch.object(type(service),name,autospec=True) as callback:
                        callback.return_value=object()
                        self.assertIs(getattr(server,name)(*args,**kwargs),callback.return_value);callback.assert_called_once_with(service,*args,**kwargs)
                        self.assertIs(callback.call_args.args[0],service)


if __name__=='__main__':unittest.main()
